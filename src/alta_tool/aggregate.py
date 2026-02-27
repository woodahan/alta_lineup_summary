from __future__ import annotations

from dataclasses import dataclass

from .matching import resolve_candidate
from .models import AggregatedRating, OutputRow, PlayerQuery, RatingRecord, SourceResult
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
        winning_rating=winner.rating_original,
        winning_play_year=winner.year,
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


def _source_highest(source: str, records: list[RatingRecord]) -> SourceResult:
    source_records = [record for record in records if record.source == source]
    if not source_records:
        return SourceResult(highest_rating=None, highest_year=None, profile_url=None, status="not_found")
    winner = sorted(source_records, key=lambda r: (r.normalized_value, r.year), reverse=True)[0]
    return SourceResult(
        highest_rating=winner.rating_original,
        highest_year=winner.year,
        profile_url=winner.profile_url,
        status="ok",
    )


def _source_name(adapter: SourceAdapter) -> str:
    return adapter.source_name.lower()


def process_player(query: PlayerQuery, adapters: list[SourceAdapter]) -> OutputRow:
    rating_records: list[RatingRecord] = []
    ambiguous_urls: list[str] = []
    extra_notes: list[str] = []
    source_results: dict[str, SourceResult] = {}
    has_medium_confidence = False
    has_high_confidence = False

    for adapter in adapters:
        source = _source_name(adapter)
        try:
            candidates = adapter.search_player(query)
        except Exception as exc:  # noqa: BLE001
            note = f"{source}_error={exc}"
            extra_notes.append(note)
            source_results[source] = SourceResult(
                highest_rating=None,
                highest_year=None,
                profile_url=None,
                status="error",
                note=note,
            )
            continue

        resolution = resolve_candidate(query, candidates)
        if resolution.ambiguous_urls:
            ambiguous_urls.extend(resolution.ambiguous_urls)
            urls = " | ".join(resolution.ambiguous_urls)
            note = f"{source}_ambiguous_urls={urls}"
            extra_notes.append(note)
            source_results[source] = SourceResult(
                highest_rating=None,
                highest_year=None,
                profile_url=None,
                status="ambiguous",
                note=note,
            )
            continue

        if not resolution.selected:
            source_results[source] = SourceResult(
                highest_rating=None,
                highest_year=None,
                profile_url=None,
                status="not_found",
            )
            continue

        if resolution.confidence == "high":
            has_high_confidence = True
        elif resolution.confidence == "medium":
            has_medium_confidence = True

        selected = resolution.selected
        source_has_ratings = False
        for raw_rating in selected.ratings:
            numeric = normalize_rating(raw_rating.value)
            if numeric is None:
                continue
            source_has_ratings = True
            rating_records.append(
                RatingRecord(
                    source=source,
                    rating_original=raw_rating.value,
                    normalized_value=numeric,
                    year=raw_rating.year,
                    profile_url=selected.profile_url,
                    city=selected.city,
                )
            )

        if source_has_ratings:
            source_results[source] = _source_highest(source, rating_records)
        else:
            if source == "usta":
                source_results[source] = SourceResult(
                    highest_rating=None,
                    highest_year=None,
                    profile_url=selected.profile_url,
                    status="ok",
                )
            else:
                note = f"{source}_no_ratings"
                extra_notes.append(note)
                source_results[source] = SourceResult(
                    highest_rating=None,
                    highest_year=None,
                    profile_url=selected.profile_url,
                    status="not_found",
                    note=note,
                )

    for required_source in ("t2", "ultimate", "usta"):
        source_results.setdefault(
            required_source,
            SourceResult(highest_rating=None, highest_year=None, profile_url=None, status="not_found"),
        )

    aggregated = select_highest(rating_records)
    notes = _notes_with_urls(ambiguous_urls, extra_notes)

    if has_high_confidence:
        confidence = "high"
    elif has_medium_confidence:
        confidence = "medium"
    else:
        confidence = "low"

    if aggregated:
        status = "ok"
    else:
        statuses = [source_results[name].status for name in ("t2", "ultimate", "usta")]
        if all(s == "error" for s in statuses):
            status = "error"
        elif any(s == "ambiguous" for s in statuses):
            status = "ambiguous"
        else:
            status = "not_found"

    t2_result = source_results["t2"]
    ultimate_result = source_results["ultimate"]
    usta_result = source_results["usta"]

    return OutputRow(
        first_name=query.first_name,
        last_name=query.last_name,
        player_city=aggregated.player_city if aggregated else None,
        highest_rating_t2=t2_result.highest_rating,
        highest_year_t2=t2_result.highest_year,
        profile_url_t2=t2_result.profile_url,
        highest_rating_ultimate=ultimate_result.highest_rating,
        highest_year_ultimate=ultimate_result.highest_year,
        profile_url_ultimate=ultimate_result.profile_url,
        profile_url_usta=usta_result.profile_url,
        winning_rating=aggregated.winning_rating if aggregated else None,
        winning_play_year=aggregated.winning_play_year if aggregated else None,
        winning_source=aggregated.winning_source if aggregated else None,
        profile_url=aggregated.profile_url if aggregated else None,
        match_confidence=confidence,
        status=status,
        notes=notes,
    )
