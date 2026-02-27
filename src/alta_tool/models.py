from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Status = Literal["ok", "not_found", "ambiguous", "error"]
Confidence = Literal["high", "medium", "low"]
SourceStatus = Literal["ok", "not_found", "ambiguous", "error"]


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
class SourceResult:
    highest_rating: str | None
    highest_year: int | None
    profile_url: str | None
    status: SourceStatus
    note: str | None = None


@dataclass(frozen=True)
class AggregatedRating:
    winning_rating: str
    winning_play_year: int
    winning_source: str
    profile_url: str
    player_city: str | None


@dataclass(frozen=True)
class OutputRow:
    first_name: str
    last_name: str
    player_city: str | None
    highest_rating_t2: str | None
    highest_year_t2: int | None
    profile_url_t2: str | None
    highest_rating_ultimate: str | None
    highest_year_ultimate: int | None
    profile_url_ultimate: str | None
    highest_rating_usta: str | None
    highest_year_usta: int | None
    profile_url_usta: str | None
    winning_rating: str | None
    winning_play_year: int | None
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
            "highest_rating_t2",
            "highest_year_t2",
            "profile_url_t2",
            "highest_rating_ultimate",
            "highest_year_ultimate",
            "profile_url_ultimate",
            "highest_rating_usta",
            "highest_year_usta",
            "profile_url_usta",
            "winning_rating",
            "winning_play_year",
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
            self.highest_rating_t2 or "",
            str(self.highest_year_t2 or ""),
            self.profile_url_t2 or "",
            self.highest_rating_ultimate or "",
            str(self.highest_year_ultimate or ""),
            self.profile_url_ultimate or "",
            self.highest_rating_usta or "",
            str(self.highest_year_usta or ""),
            self.profile_url_usta or "",
            self.winning_rating or "",
            str(self.winning_play_year or ""),
            self.winning_source or "",
            self.profile_url or "",
            self.match_confidence,
            self.status,
            self.notes,
        ]
