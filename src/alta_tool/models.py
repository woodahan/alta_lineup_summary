from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Status = Literal["ok", "not_found", "ambiguous", "error"]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class PlayerQuery:
    first_name: str
    last_name: str
    city_hint: str | None = None
    state_hint: str = "GA"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


@dataclass(frozen=True)
class RawRating:
    value: str
    year: int


@dataclass(frozen=True)
class CandidateProfile:
    first_name: str
    last_name: str
    city: str | None
    state: str | None
    profile_url: str
    ratings: list[RawRating] = field(default_factory=list)


@dataclass(frozen=True)
class RatingRecord:
    source: str
    rating_original: str
    normalized_value: float
    year: int
    profile_url: str
    city: str | None


@dataclass(frozen=True)
class AggregatedRating:
    highest_rating: str
    play_year: int
    winning_source: str
    profile_url: str
    player_city: str | None


@dataclass(frozen=True)
class OutputRow:
    first_name: str
    last_name: str
    player_city: str | None
    highest_rating: str | None
    play_year: int | None
    winning_source: str | None
    profile_url: str | None
    match_confidence: Confidence
    status: Status
    notes: str

    @staticmethod
    def headers() -> list[str]:
        return [
            "first_name",
            "last_name",
            "player_city",
            "highest_rating",
            "play_year",
            "winning_source",
            "profile_url",
            "match_confidence",
            "status",
            "notes",
        ]

    def to_sheet_row(self) -> list[str]:
        return [
            self.first_name,
            self.last_name,
            self.player_city or "",
            self.highest_rating or "",
            str(self.play_year or ""),
            self.winning_source or "",
            self.profile_url or "",
            self.match_confidence,
            self.status,
            self.notes,
        ]
