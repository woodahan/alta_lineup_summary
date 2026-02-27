from alta_tool.matching import resolve_candidate
from alta_tool.models import CandidateProfile, PlayerQuery, RawRating


def _candidate(first: str, last: str, city: str, state: str, url: str) -> CandidateProfile:
    return CandidateProfile(
        first_name=first,
        last_name=last,
        city=city,
        state=state,
        profile_url=url,
        ratings=[RawRating(value="4.0", year=2024)],
    )


def test_resolve_candidate_prefers_georgia_and_city() -> None:
    query = PlayerQuery(first_name="Jane", last_name="Doe", city_hint="Atlanta", state_hint="GA")
    candidates = [
        _candidate("Jane", "Doe", "Atlanta", "GA", "https://a"),
        _candidate("Jane", "Doe", "Austin", "TX", "https://b"),
    ]

    result = resolve_candidate(query, candidates)

    assert result.selected is not None
    assert result.selected.profile_url == "https://a"
    assert result.ambiguous_urls == []


def test_resolve_candidate_marks_ambiguous_when_same_name_same_city() -> None:
    query = PlayerQuery(first_name="Sam", last_name="Lee", city_hint="Atlanta", state_hint="GA")
    candidates = [
        _candidate("Sam", "Lee", "Atlanta", "GA", "https://one"),
        _candidate("Sam", "Lee", "Atlanta", "GA", "https://two"),
    ]

    result = resolve_candidate(query, candidates)

    assert result.selected is None
    assert result.ambiguous_urls == ["https://one", "https://two"]
