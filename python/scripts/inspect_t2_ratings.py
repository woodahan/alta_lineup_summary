from __future__ import annotations

import argparse
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from alta_tool.config import load_settings
from alta_tool.models import PlayerQuery
from alta_tool.rating_normalize import normalize_rating
from alta_tool.sources.t2 import T2Adapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect T2 player-history rows and extracted ratings for one selected player"
    )
    parser.add_argument("--first-name", required=True, help="Player first name")
    parser.add_argument("--last-name", required=True, help="Player last name")
    parser.add_argument("--state", default="GA", help="State filter (default: GA)")
    parser.add_argument(
        "--option-index",
        type=int,
        default=0,
        help="Which search result option to inspect (0-based, default: 0)",
    )
    parser.add_argument(
        "--show-all-rows",
        action="store_true",
        help="Print all history table rows (including ones without extracted rating/year)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = load_settings()

    adapter = T2Adapter(
        username=settings.t2.username,
        password=settings.t2.password,
        login_url=settings.t2.login_url,
        search_url=settings.t2.search_url,
        cache_dir=settings.cache_dir,
    )

    print("[1/5] Loading cached cookies...")
    adapter.load_cached_cookies()

    print("[2/5] Authenticating to T2...")
    ok, msg = adapter.authenticate()
    print(f"auth_ok={ok} message={msg}")
    if not ok:
        return 1

    query = PlayerQuery(
        first_name=args.first_name.strip(),
        last_name=args.last_name.strip(),
        state_hint=args.state.strip().upper() or "GA",
    )

    print("[3/5] Submitting T2 search...")
    search_page = adapter.session.get(adapter.search_url, timeout=20, allow_redirects=True)
    search_page.raise_for_status()
    soup = BeautifulSoup(search_page.text, "html.parser")
    form = soup.select_one("form#aspnetForm")
    if not form:
        print("error=no aspnet form found on search page")
        return 1

    payload: dict[str, str] = {}
    for hidden in form.select("input[type='hidden'][name]"):
        name = hidden.get("name", "").strip()
        if name:
            payload[name] = hidden.get("value", "")
    payload["ctl00$PageBody$txtLastName"] = query.last_name
    payload["ctl00$PageBody$txtFirstName"] = query.first_name
    payload["ctl00$PageBody$btnPlayerSearch"] = "Search"

    action = form.get("action", "").strip()
    post_url = urljoin(search_page.url, action) if action else search_page.url
    response = adapter.session.post(
        post_url,
        data=payload,
        timeout=20,
        allow_redirects=True,
        headers={"Referer": search_page.url},
    )
    response.raise_for_status()

    result_soup = BeautifulSoup(response.text, "html.parser")
    players_select = result_soup.select_one("select#ctl00_PageBody_lbPlayers")
    if not players_select:
        print("no player options found")
        return 0

    options = players_select.select("option[value]")
    if not options:
        print("player list exists but has no selectable options")
        return 0

    print(f"found_options={len(options)}")
    for i, option in enumerate(options):
        label = " ".join(option.get_text(" ", strip=True).split())
        print(f"  [{i}] {label}")

    if args.option_index < 0 or args.option_index >= len(options):
        print(f"error=option-index out of range: {args.option_index}")
        return 1

    option = options[args.option_index]
    player_id = option.get("value", "").strip()
    option_label = " ".join(option.get_text(" ", strip=True).split())

    print(f"[4/5] Loading history for option_index={args.option_index} player_id={player_id}")
    print(f"selected_option={option_label}")

    form = result_soup.select_one("form#aspnetForm")
    if not form:
        print("error=no aspnet form found on search results page")
        return 1

    history_payload: dict[str, str] = {}
    for hidden in form.select("input[type='hidden'][name]"):
        name = hidden.get("name", "").strip()
        if name:
            history_payload[name] = hidden.get("value", "")
    history_payload["__EVENTTARGET"] = "ctl00$PageBody$lbPlayers"
    history_payload["__EVENTARGUMENT"] = ""
    history_payload["ctl00$PageBody$lbPlayers"] = player_id

    action = form.get("action", "").strip()
    detail_post_url = urljoin(response.url, action) if action else response.url
    detail = adapter.session.post(
        detail_post_url,
        data=history_payload,
        timeout=20,
        allow_redirects=True,
        headers={"Referer": response.url},
    )
    detail.raise_for_status()

    detail_soup = BeautifulSoup(detail.text, "html.parser")
    history_block = detail_soup.select_one("div#ctl00_PageBody_PlayerHistory") or detail_soup

    print("[5/5] Parsing history rows...")
    extracted = 0
    for row in history_block.select("tr"):
        row_text = " ".join(row.get_text(" ", strip=True).split())
        if not row_text:
            continue

        year = adapter._extract_year(row_text)
        rating_match = adapter.RATING_RE.search(row_text)
        rating = rating_match.group(1) if rating_match else None
        normalized = normalize_rating(rating) if rating else None

        if args.show_all_rows or (year and rating):
            print(
                f"row={row_text}\n"
                f"  year={year} rating={rating} normalized={normalized}"
            )

        if year and rating:
            extracted += 1

    print(f"extracted_rows={extracted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
