from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from alta_tool.config import load_settings
from alta_tool.models import PlayerQuery
from alta_tool.sources.t2 import T2Adapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect raw T2 player search HTTP response after login"
    )
    parser.add_argument("--first-name", required=True, help="Player first name")
    parser.add_argument("--last-name", required=True, help="Player last name")
    parser.add_argument("--state", default="GA", help="State filter (default: GA)")
    parser.add_argument(
        "--output",
        default=".cache/t2_search_response.txt",
        help="Path to save full response body",
    )
    parser.add_argument(
        "--show-chars",
        type=int,
        default=500,
        help="How many response-body characters to print to console",
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

    print("[1/4] Loading cached cookies...")
    adapter.load_cached_cookies()

    print("[2/4] Authenticating to T2...")
    ok, msg = adapter.authenticate()
    print(f"auth_ok={ok} message={msg}")
    if not ok:
        return 1
    cookie_names = sorted(c.name for c in adapter.session.cookies)
    print(f"session_cookies={cookie_names}")

    verify = adapter.session.get(adapter.search_url, timeout=20, allow_redirects=True)
    print(f"verify_url={verify.url}")
    print(f"verify_status={verify.status_code}")
    print(f"verify_is_login_page={'login.aspx' in verify.url.lower()}")

    query = PlayerQuery(
        first_name=args.first_name.strip(),
        last_name=args.last_name.strip(),
        state_hint=args.state.strip().upper() or "GA",
    )

    print("[3/4] Loading search page + submitting search form...")
    search_page = adapter.session.get(adapter.search_url, timeout=20, allow_redirects=True)
    search_page.raise_for_status()
    soup = BeautifulSoup(search_page.text, "html.parser")
    form = soup.select_one("form#aspnetForm")
    if not form:
        print("error=no aspnet form found on search page")
        return 1

    payload = {}
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
