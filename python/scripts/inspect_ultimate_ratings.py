from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from alta_tool.config import load_settings
from alta_tool.models import PlayerQuery
from alta_tool.rating_normalize import normalize_rating
from alta_tool.sources.ultimate import UltimateAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect Ultimate season-history rows and extracted ratings/rankings for one selected player"
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
        "--output",
        default=".cache/ultimate_profile_response.html",
        help="Path to save selected profile HTML",
    )
    parser.add_argument(
        "--show-all-rows",
        action="store_true",
        help="Print all table rows (including ones without extracted rating/year)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = load_settings()

    adapter = UltimateAdapter(
        username=settings.ultimate.username,
        password=settings.ultimate.password,
        login_url=settings.ultimate.login_url,
        search_url=settings.ultimate.search_url,
        cache_dir=settings.cache_dir,
    )

    print("[1/5] Loading cached cookies...")
    adapter.load_cached_cookies()

    print("[2/5] Authenticating to Ultimate...")
    ok, msg = adapter.authenticate()
    print(f"auth_ok={ok} message={msg}")
    if not ok:
        return 1

    query = PlayerQuery(
        first_name=args.first_name.strip(),
        last_name=args.last_name.strip(),
        state_hint=args.state.strip().upper() or "GA",
    )

    print("[3/5] Submitting Ultimate search...")
    search_page = adapter.session.get(adapter.search_url, timeout=20)
    search_page.raise_for_status()
    soup = BeautifulSoup(search_page.text, "html.parser")
    token_input = soup.select_one("form#new_search input[name='authenticity_token']")
    token = token_input.get("value", "").strip() if token_input else ""
    payload = {
        "authenticity_token": token,
        "search[first_name_begins_with]": query.first_name,
        "search[last_name_begins_with]": query.last_name,
        "commit": "Find player",
    }
    response = adapter.session.post(adapter.search_url, data=payload, timeout=20, allow_redirects=True)
    response.raise_for_status()

    results_soup = BeautifulSoup(response.text, "html.parser")
    rows = results_soup.select("table#player_directory tbody tr.player")
    if not rows:
        print("no player rows found")
        return 0

    options: list[tuple[str, str]] = []
    for row in rows:
        link = row.select_one("td.first a[href]")
        if not link:
            continue
        href = link.get("href", "").strip()
        if not href:
            continue
        profile_url = urljoin(response.url, href)
        label = " ".join(link.get_text(" ", strip=True).split())
        if not label:
            label = profile_url
        options.append((label, profile_url))

    if not options:
        print("search table found but no selectable profile links")
        return 0

    print(f"found_options={len(options)}")
    for i, (label, _) in enumerate(options):
        print(f"  [{i}] {label}")

    if args.option_index < 0 or args.option_index >= len(options):
        print(f"error=option-index out of range: {args.option_index}")
        return 1

    selected_label, selected_url = options[args.option_index]
    print(f"[4/5] Loading profile for option_index={args.option_index}")
    print(f"selected_option={selected_label}")
    print(f"selected_profile_url={selected_url}")

    detail = adapter.session.get(selected_url, timeout=20)
    detail.raise_for_status()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(detail.text, encoding="utf-8")
    print(f"saved_profile_html={out_path}")

    detail_soup = BeautifulSoup(detail.text, "html.parser")
    print("[5/5] Parsing history rows...")
    extracted = 0
    for row in detail_soup.select("tr"):
        row_text = " ".join(row.get_text(" ", strip=True).split())
        if not row_text:
            continue

        year_match = adapter.YEAR_RE.search(row_text)
        rating_match = adapter.RATING_RE.search(row_text)
        year = int(year_match.group(0)) if year_match else None
        rating = rating_match.group(1) if rating_match else None
        normalized = normalize_rating(rating) if rating else None
        division_ranking, league_ranking = adapter._extract_rankings(row)

        if args.show_all_rows or (year and rating):
            print(
                f"row={row_text}\n"
                f"  year={year} rating={rating} normalized={normalized} "
                f"division_ranking={division_ranking} league_ranking={league_ranking}"
            )

        if year and rating:
            extracted += 1

    print(f"extracted_rows={extracted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
