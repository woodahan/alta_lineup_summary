from alta_tool.sources.t2 import T2Adapter


class FakeResponse:
    def __init__(self, text: str, url: str = "https://t2.example/player-history"):
        self.text = text
        self.url = url

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, detail_html: str):
        self._detail_html = detail_html
        self.last_post_data: dict[str, str] | None = None

    def post(self, url: str, data: dict[str, str], timeout: int, allow_redirects: bool, headers: dict[str, str]):
        _ = url, timeout, allow_redirects, headers
        self.last_post_data = data
        return FakeResponse(self._detail_html)


def test_fetch_player_history_ratings_extracts_minus_and_quarter_values() -> None:
    search_html = """
    <html><body>
      <form id=\"aspnetForm\" action=\"/search\">
        <input type=\"hidden\" name=\"__VIEWSTATE\" value=\"abc\" />
      </form>
    </body></html>
    """

    detail_html = """
    <html><body>
      <div id=\"ctl00_PageBody_PlayerHistory\">
        <table>
          <tr><td>Spring 2024</td><td>4.0-</td></tr>
          <tr><td>Fall 2023</td><td>3.75</td></tr>
          <tr><td>Summer 2022</td><td>4.0C</td></tr>
          <tr><td>Summer 2022</td><td>4.0C</td></tr>
        </table>
      </div>
    </body></html>
    """

    adapter = T2Adapter(
        username="u",
        password="p",
        login_url="https://t2.example/login",
        search_url="https://t2.example/search",
        cache_dir=".cache/alta_tool",
    )
    fake_session = FakeSession(detail_html)
    adapter.session = fake_session  # type: ignore[assignment]

    ratings = adapter._fetch_player_history_ratings(FakeResponse(search_html), player_id="123")

    assert [(r.value, r.year) for r in ratings] == [
        ("4.0-", 2024),
        ("3.75", 2023),
        ("4.0", 2022),
    ]
    assert fake_session.last_post_data is not None
    assert fake_session.last_post_data["__EVENTTARGET"] == "ctl00$PageBody$lbPlayers"
    assert fake_session.last_post_data["ctl00$PageBody$lbPlayers"] == "123"


def test_fetch_player_history_ratings_parses_two_digit_season_year() -> None:
    search_html = """
    <html><body>
      <form id=\"aspnetForm\" action=\"/search\">
        <input type=\"hidden\" name=\"__VIEWSTATE\" value=\"abc\" />
      </form>
    </body></html>
    """

    detail_html = """
    <html><body>
      <div id=\"ctl00_PageBody_PlayerHistory\">
        <table>
          <tr><td>Bus. Women's Doubles - Fall '06</td><td>3.5</td></tr>
        </table>
      </div>
    </body></html>
    """

    adapter = T2Adapter(
        username="u",
        password="p",
        login_url="https://t2.example/login",
        search_url="https://t2.example/search",
        cache_dir=".cache/alta_tool",
    )
    adapter.session = FakeSession(detail_html)  # type: ignore[assignment]

    ratings = adapter._fetch_player_history_ratings(FakeResponse(search_html), player_id="30760")
    assert [(r.value, r.year) for r in ratings] == [("3.5", 2006)]
