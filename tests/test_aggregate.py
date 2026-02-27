from alta_tool.aggregate import process_player, select_highest
from alta_tool.models import CandidateProfile, PlayerQuery, RatingRecord, RawRating
from alta_tool.sources.base import SourceAdapter


class FakeAdapter(SourceAdapter):
    source_name = "fake"
    required_auth = False

    def __init__(self, candidates):
        super().__init__(username=None, password=None, login_url=None, search_url="http://fake", cache_dir=".cache")
        self._candidates = candidates

    def search_player(self, query: PlayerQuery):  # type: ignore[override]
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
    assert result.play_year == 2024
    assert result.winning_source == "t2"


def test_process_player_outputs_ambiguous_urls() -> None:
    query = PlayerQuery(first_name="Sam", last_name="Lee", city_hint="Atlanta")
    candidates = [
        CandidateProfile("Sam", "Lee", "Atlanta", "GA", "https://one", [RawRating("3.5", 2024)]),
        CandidateProfile("Sam", "Lee", "Atlanta", "GA", "https://two", [RawRating("4.0", 2023)]),
    ]
    adapter = FakeAdapter(candidates)

    row = process_player(query, [adapter])

    assert row.status == "ambiguous"
    assert "candidate_urls=https://one | https://two" in row.notes
    assert row.profile_url is None
