from __future__ import annotations

from dataclasses import dataclass

from .matching import resolve_candidate
from .models import AggregatedRating, OutputRow, PlayerQuery, RatingRecord
from .rating_normalize import normalize_rating
from .sources.base import SourceAdapter


@dataclass(frozen=True)
class RunSummary:
    ok: int = 0
    not_found: int = 0
    ambiguous: int = 0
    error: int = 0


def select_highest(records: list[RatingRecord]) -> AggregatedRating | None:
    if not records:
        return None

    winner = sorted(records, key=lambda r: (r.normalized_value, r.year), reverse=True)[0]
    return AggregatedRating(
        highest_rating=winner.rating_original,
        play_year=winner.year,
        winning_source=winner.source,
        profile_url=winner.profile_url,
        player_city=winner.city,
    )


def _notes_with_urls(urls: list[str], extra_notes: list[str] | None = None) -> str:
    notes: list[str] = []
    if urls:
        notes.append(f"candidate_urls={' | '.join(urls)}")
    if extra_notes:
        notes.extend(extra_notes)
    return "; ".join(notes)


def process_player(query: PlayerQuery, adapters: list[SourceAdapter]) -> OutputRow:
    rating_records: list[RatingRecord] = []
    ambiguous_urls: list[str] = []
    extra_notes: list[str] = []
    confidence = "low"

    for adapter in adapters:
        try:
            candidates = adapter.search_player(query)
        except Exception as exc:  # noqa: BLE001
            extra_notes.append(f"{adapter.source_name}_error={exc}")
            continue

        resolution = resolve_candidate(query, candidates)
        if resolution.ambiguous_urls:
            ambiguous_urls.extend(resolution.ambiguous_urls)
            continue

        if not resolution.selected:
            continue

        confidence = "high" if confidence != "high" and resolution.confidence == "high" else confidence
        selected = resolution.selected
        for raw_rating in selected.ratings:
            numeric = normalize_rating(raw_rating.value)
            if numeric is None:
                continue
            rating_records.append(
                RatingRecord(
                    source=adapter.source_name,
                    rating_original=raw_rating.value,
                    normalized_value=numeric,
                    year=raw_rating.year,
                    profile_url=selected.profile_url,
                    city=selected.city,
                )
            )

    aggregated = select_highest(rating_records)
    notes = _notes_with_urls(ambiguous_urls, extra_notes)

    if aggregated:
        return OutputRow(
            first_name=query.first_name,
            last_name=query.last_name,
            player_city=aggregated.player_city,
            highest_rating=aggregated.highest_rating,
            play_year=aggregated.play_year,
            winning_source=aggregated.winning_source,
            profile_url=aggregated.profile_url,
            match_confidence=confidence,
            status="ok",
            notes=notes,
        )

    if ambiguous_urls:
        return OutputRow(
            first_name=query.first_name,
            last_name=query.last_name,
            player_city=None,
            highest_rating=None,
            play_year=None,
            winning_source=None,
            profile_url=None,
            match_confidence="low",
            status="ambiguous",
            notes=notes,
        )

    status = "error" if extra_notes else "not_found"
    return OutputRow(
        first_name=query.first_name,
        last_name=query.last_name,
        player_city=None,
        highest_rating=None,
        play_year=None,
        winning_source=None,
        profile_url=None,
        match_confidence="low",
        status=status,
        notes=notes,
    )
