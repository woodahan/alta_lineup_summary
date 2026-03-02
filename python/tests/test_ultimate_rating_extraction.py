from alta_tool.sources.ultimate import UltimateAdapter


class FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, html: str):
        self.html = html

    def get(self, profile_url: str, timeout: int):
        _ = profile_url, timeout
        return FakeResponse(self.html)


def _adapter_with_html(html: str) -> UltimateAdapter:
    adapter = UltimateAdapter(
        username="u",
        password="p",
        login_url="https://ultimate.example/sign_in",
        search_url="https://ultimate.example/search",
        cache_dir=".cache/alta_tool",
    )
    adapter.session = FakeSession(html)  # type: ignore[assignment]
    return adapter


def test_fetch_history_ratings_parses_division_and_league_rankings() -> None:
    html = """
    <html><body>
      <table>
        <tr><th>Year</th><th>Level</th><th>Division Rank</th><th>League Rank</th></tr>
        <tr><td>2024</td><td>4.0</td><td>3</td><td>11</td></tr>
      </table>
    </body></html>
    """

    ratings = _adapter_with_html(html)._fetch_history_ratings("https://ultimate.example/p/1")
    assert len(ratings) == 1
    assert ratings[0].value == "4.0"
    assert ratings[0].year == 2024
    assert ratings[0].division_ranking == 3
    assert ratings[0].league_ranking == 11


def test_fetch_history_ratings_maps_generic_rank_to_division_ranking() -> None:
    html = """
    <html><body>
      <table>
        <tr><th>Year</th><th>Level</th><th>Rank</th></tr>
        <tr><td>2023</td><td>3.5</td><td>#7</td></tr>
      </table>
    </body></html>
    """

    ratings = _adapter_with_html(html)._fetch_history_ratings("https://ultimate.example/p/2")
    assert len(ratings) == 1
    assert ratings[0].value == "3.5"
    assert ratings[0].year == 2023
    assert ratings[0].division_ranking == 7
    assert ratings[0].league_ranking is None


def test_fetch_history_ratings_parses_abbreviated_rank_headers() -> None:
    html = """
    <html><body>
      <table>
        <tr><th>League</th><th>Division</th><th>Level</th><th>Div. Rank</th><th>Leag. Rank</th></tr>
        <tr><td>Fall</td><td>2015</td><td>3.0-</td><td>7</td><td>100</td></tr>
      </table>
    </body></html>
    """

    ratings = _adapter_with_html(html)._fetch_history_ratings("https://ultimate.example/p/3")
    assert len(ratings) == 1
    assert ratings[0].value == "3.0-"
    assert ratings[0].year == 2015
    assert ratings[0].division_ranking == 7
    assert ratings[0].league_ranking == 100


def test_fetch_history_ratings_parses_rank_from_non_th_header_table() -> None:
    html = """
    <html><body>
      <table>
        <tr><td>league division level div. rank leag. rank points</td></tr>
        <tr><td>Fall 2015 61617 3.0- 7 100 52 2 5 29%</td></tr>
      </table>
    </body></html>
    """

    ratings = _adapter_with_html(html)._fetch_history_ratings("https://ultimate.example/p/4")
    assert len(ratings) == 1
    assert ratings[0].value == "3.0-"
    assert ratings[0].year == 2015
    assert ratings[0].division_ranking == 7
    assert ratings[0].league_ranking == 100
