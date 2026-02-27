from alta_tool.sources.usta import UstaAdapter


def _adapter() -> UstaAdapter:
    return UstaAdapter(
        username=None,
        password=None,
        login_url=None,
        search_url="https://www.usta.com/en/home/play/player-search.html",
        cache_dir=".cache",
    )


def test_extract_ratings_from_json_parses_ntrp_and_last_played() -> None:
    adapter = _adapter()
    payload = {
        "data": {
            "ratings": {"ntrpRating": "3.5C"},
            "activity": {"lastPlayedDate": "2025-10-13"},
        }
    }

    ratings = adapter._extract_ratings_from_json(payload)  # noqa: SLF001
    assert len(ratings) == 1
    assert ratings[0].value == "3.5C"
    assert ratings[0].year == 2025


def test_extract_ratings_from_html_parses_profile_snippet() -> None:
    adapter = _adapter()
    html = """
    <html>
      <body>
        <div>NTRP Rating: 4.0S</div>
        <div>Last Played: Feb 21, 2026</div>
      </body>
    </html>
    """

    ratings = adapter._extract_ratings_from_html(html)  # noqa: SLF001
    assert len(ratings) == 1
    assert ratings[0].value == "4.0S"
    assert ratings[0].year == 2026
