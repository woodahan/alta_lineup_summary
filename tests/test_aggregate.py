from alta_tool.aggregate import process_player, select_highest
from alta_tool.models import CandidateProfile, PlayerQuery, RatingRecord, RawRating
from alta_tool.sources.base import SourceAdapter


class FakeAdapter(SourceAdapter):
    required_auth = False

    def __init__(self, source_name: str, candidates=None, should_raise: bool = False):
        self.source_name = source_name
        self._candidates = candidates or []
        self._raise = should_raise
        super().__init__(username=None, password=None, login_url=None, search_url="http://fake", cache_dir=".cache")

    def search_player(self, query: PlayerQuery):  # type: ignore[override]
        _ = query
        if self._raise:
            raise RuntimeError("boom")
        return self._candidates

    def is_required(self) -> bool:
        return False


def test_select_highest_tiebreaker_uses_most_recent_year() -> None:
    records = [
        RatingRecord(
            source="usta",
            rating_original="4.0",
            normalized_value=4.0,
            year=2022,
            profile_url="u1",
            city="Atlanta",
        ),
        RatingRecord(
            source="t2",
            rating_original="4.0",
            normalized_value=4.0,
            year=2024,
            profile_url="u2",
            city="Atlanta",
        ),
    ]

    result = select_highest(records)
    assert result is not None
    assert result.winning_play_year == 2024
    assert result.winning_source == "t2"


def test_process_player_outputs_ambiguous_urls() -> None:
    query = PlayerQuery(first_name="Sam", last_name="Lee", city_hint="Atlanta")
    ambiguous_candidates = [
        CandidateProfile("Sam", "Lee", "Atlanta", "GA", "https://one", [RawRating("3.5", 2024)]),
        CandidateProfile("Sam", "Lee", "Atlanta", "GA", "https://two", [RawRating("4.0", 2023)]),
    ]

    row = process_player(
        query,
        [
            FakeAdapter("t2", ambiguous_candidates),
            FakeAdapter("ultimate", []),
            FakeAdapter("usta", []),
        ],
    )

    assert row.status == "ambiguous"
    assert "candidate_urls=https://one | https://two" in row.notes
    assert row.profile_url is None


def test_process_player_populates_per_source_and_winner() -> None:
    query = PlayerQuery(first_name="Jane", last_name="Doe", city_hint="Atlanta")
    t2_candidates = [
        CandidateProfile("Jane", "Doe", "Atlanta", "GA", "https://t2/jane", [RawRating("3.5-", 2024)])
    ]
    ultimate_candidates = [
        CandidateProfile("Jane", "Doe", "Atlanta", "GA", "https://ultimate/jane", [RawRating("4.0", 2023)])
    ]

    row = process_player(
        query,
        [
            FakeAdapter("t2", t2_candidates),
            FakeAdapter("ultimate", ultimate_candidates),
            FakeAdapter("usta", []),
        ],
    )

    assert row.status == "ok"
    assert row.highest_rating_t2 == "3.5-"
    assert row.highest_year_t2 == 2024
    assert row.highest_rating_ultimate == "4.0"
    assert row.highest_year_ultimate == 2023
    assert row.highest_rating_usta is None
    assert row.winning_rating == "4.0"
    assert row.winning_play_year == 2023
    assert row.winning_source == "ultimate"
    assert row.profile_url == "https://ultimate/jane"


def test_process_player_all_errors_sets_error_status() -> None:
    query = PlayerQuery(first_name="Jane", last_name="Doe", city_hint="Atlanta")
    row = process_player(
        query,
        [
            FakeAdapter("t2", should_raise=True),
            FakeAdapter("ultimate", should_raise=True),
            FakeAdapter("usta", should_raise=True),
        ],
    )

    assert row.status == "error"
    assert "t2_error=" in row.notes
    assert "ultimate_error=" in row.notes
    assert "usta_error=" in row.notes
