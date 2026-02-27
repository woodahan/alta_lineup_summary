from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .models import CandidateProfile, PlayerQuery

STATE_GA = "GA"


@dataclass(frozen=True)
class MatchResult:
    selected: CandidateProfile | None
    confidence: str
    ambiguous_urls: list[str]


def _normalize_token(value: str) -> str:
    lowered = value.lower().strip()
    return re.sub(r"[^a-z0-9]", "", lowered)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(a=a, b=b).ratio() * 100


def _is_georgia(candidate: CandidateProfile, state_hint: str) -> bool:
    state = (candidate.state or "").strip().upper()
    return state == (state_hint or STATE_GA).upper()


def _city_match(city_hint: str | None, candidate_city: str | None) -> bool:
    if not city_hint:
        return True
    if not candidate_city:
        return False
    return _normalize_token(city_hint) == _normalize_token(candidate_city)


def resolve_candidate(query: PlayerQuery, candidates: list[CandidateProfile]) -> MatchResult:
    if not candidates:
        return MatchResult(selected=None, confidence="low", ambiguous_urls=[])

    expected_first = _normalize_token(query.first_name)
    expected_last = _normalize_token(query.last_name)

    scored: list[tuple[CandidateProfile, float]] = []
    for candidate in candidates:
        first = _normalize_token(candidate.first_name)
        last = _normalize_token(candidate.last_name)
        first_score = _similarity(expected_first, first)
        last_score = _similarity(expected_last, last)
        total = (first_score + last_score) / 2
        scored.append((candidate, total))

    conservative = [item for item in scored if item[1] >= 90]
    conservative.sort(key=lambda it: it[1], reverse=True)

    ga_only = [item for item in conservative if _is_georgia(item[0], query.state_hint)]
    georgia_pool = ga_only if ga_only else conservative

    city_pool = [item for item in georgia_pool if _city_match(query.city_hint, item[0].city)]
    filtered = city_pool if city_pool else georgia_pool

    if not filtered:
        return MatchResult(selected=None, confidence="low", ambiguous_urls=[])

    if len(filtered) == 1:
        confidence = "high" if filtered[0][1] >= 97 else "medium"
        return MatchResult(selected=filtered[0][0], confidence=confidence, ambiguous_urls=[])

    urls = [candidate.profile_url for candidate, _ in filtered]
    return MatchResult(selected=None, confidence="low", ambiguous_urls=urls)
