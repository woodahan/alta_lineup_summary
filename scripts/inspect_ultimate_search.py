from __future__ import annotations

import argparse
from pathlib import Path

from bs4 import BeautifulSoup

from alta_tool.config import load_settings
from alta_tool.models import PlayerQuery
from alta_tool.sources.ultimate import UltimateAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect raw Ultimate player search HTTP response after login"
    )
    parser.add_argument("--first-name", required=True, help="Player first name")
    parser.add_argument("--last-name", required=True, help="Player last name")
    parser.add_argument("--state", default="GA", help="State filter (default: GA)")
    parser.add_argument(
        "--output",
        default=".cache/ultimate_search_response.txt",
        help="Path to save full response body",
    )
    parser.add_argument(
        "--show-chars",
        type=int,
        default=400,
        help="How many response-body characters to print to console",
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

    print("[1/4] Loading cached cookies...")
    adapter.load_cached_cookies()

    print("[2/4] Authenticating to Ultimate...")
    ok, msg = adapter.authenticate()
    print(f"auth_ok={ok} message={msg}")
    if not ok:
        return 1

    query = PlayerQuery(
        first_name=args.first_name.strip(),
        last_name=args.last_name.strip(),
        state_hint=args.state.strip().upper() or "GA",
    )

    print("[3/4] Loading search page + submitting search form...")
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

    print(f"status={response.status_code}")
    print(f"final_url={response.url}")
    print(f"content_type={response.headers.get('content-type', '')}")
    print(f"redirected={len(response.history) > 0}")
    if response.history:
        print("redirect_chain=")
        for hop in response.history:
            print(f"  - {hop.status_code} {hop.url}")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(response.text, encoding="utf-8")

    print(f"[4/4] Saved full body to: {out_path}")
    snippet = response.text[: max(args.show_chars, 0)]
    print("body_preview=")
    print(snippet)

    try:
        payload = response.json()
        top_keys = list(payload.keys())[:20] if isinstance(payload, dict) else []
        print(f"json_parse=ok type={type(payload).__name__} top_keys={top_keys}")
    except ValueError:
        print("json_parse=failed (response is not valid JSON)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
