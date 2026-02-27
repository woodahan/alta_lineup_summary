from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from urllib.parse import urljoin

from alta_tool.config import load_settings
from alta_tool.models import PlayerQuery
from alta_tool.sources.usta import UstaAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect raw USTA player search HTTP response"
    )
    parser.add_argument("--first-name", required=True, help="Player first name")
    parser.add_argument("--last-name", required=True, help="Player last name")
    parser.add_argument("--state", default="GA", help="State filter (default: GA)")
    parser.add_argument(
        "--output",
        default=".cache/usta_search_response.txt",
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

    if not settings.usta.search_url:
        print("error=USTA_SEARCH_URL is not set in environment")
        return 1

    adapter = UstaAdapter(
        username=settings.usta.username,
        password=settings.usta.password,
        login_url=settings.usta.login_url,
        search_url=settings.usta.search_url,
        cache_dir=settings.cache_dir,
    )

    print("[1/4] Loading cached cookies...")
    adapter.load_cached_cookies()

    print("[2/4] Checking optional USTA auth...")
    ok, msg = adapter.authenticate()
    print(f"auth_ok={ok} message={msg}")

    query = PlayerQuery(
        first_name=args.first_name.strip(),
        last_name=args.last_name.strip(),
        state_hint=args.state.strip().upper() or "GA",
    )

    print("[3/4] Sending raw USTA search request...")
    params = {"q": query.full_name, "state": query.state_hint}
    response = adapter.session.get(adapter.search_url, params=params, timeout=20, allow_redirects=True)

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

    # Stage 2: Probe USTA internal API used by the page's Vue container.
    # The page embeds: <v-api-container api-endpoint="/dataexchange/profile/search/public" endpoint-method="POST" ...>
    endpoint_match = re.search(r'api-endpoint="([^"]+)"', response.text)
    if not endpoint_match:
        print("api_probe=skipped (no api-endpoint found in page)")
        return 0

    endpoint_path = html.unescape(endpoint_match.group(1))
    base_candidates: list[str] = []

    # The page often includes services API base in inline config.
    services_match = re.search(r'"apiEndpoint":"([^"]+)"', response.text)
    if services_match:
        base_candidates.append(html.unescape(services_match.group(1)))

    # Prefer service hosts first to avoid repeated 404s on page host.
    base_candidates.extend(
        [
            "https://services.usta.com/v1",
            "https://services.usta.com",
            "https://api-ustaconnect.usta.com",
            "https://api-ustaconnect.usta.com/v1",
            "https://www.usta.com",
            response.url,
        ]
    )

    # Preserve order, remove duplicates.
    seen_bases: set[str] = set()
    unique_bases: list[str] = []
    for base in base_candidates:
        if base in seen_bases:
            continue
        seen_bases.add(base)
        unique_bases.append(base)

    endpoint_urls = [urljoin(base if base.endswith("/") else f"{base}/", endpoint_path.lstrip("/")) for base in unique_bases]
    # If endpoint path starts with /dataexchange..., also try under /v1 explicitly.
    if endpoint_path.startswith("/dataexchange/"):
        endpoint_urls.extend(
            [
                f"{base.rstrip('/')}/v1{endpoint_path}"
                for base in unique_bases
                if not base.rstrip("/").endswith("/v1")
            ]
        )
    endpoint_urls = list(dict.fromkeys(endpoint_urls))
    print("api_probe_endpoints=")
    for endpoint_url in endpoint_urls:
        print(f"  - {endpoint_url}")

    candidate_payloads = [
        {
            "pagination": {"pageSize": "51", "currentPage": "1"},
            "selection": {"name": {"fname": query.first_name, "lname": query.last_name}},
        },
        {
            "name": query.full_name,
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "q": query.full_name,
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "searchTerm": query.full_name,
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "nameOrUaid": query.full_name,
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "firstName": query.first_name,
            "lastName": query.last_name,
            "state": query.state_hint,
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "filters": {"name": query.full_name, "state": query.state_hint},
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "selection": {"query": query.full_name},
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "selection": {
                "searchText": query.full_name,
                "state": query.state_hint,
            },
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "selection": {
                "fullName": query.full_name,
                "filters": {"state": query.state_hint},
            },
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "selection": {
                "firstName": query.first_name,
                "lastName": query.last_name,
                "state": query.state_hint,
            },
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "selection": [
                {"id": "searchText", "value": query.full_name},
            ],
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "selection": [
                {"name": "searchText", "value": query.full_name},
            ],
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "selection": [
                {"field": "fullName", "value": query.full_name},
                {"field": "state", "value": query.state_hint},
            ],
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "selection": [
                {
                    "firstName": query.first_name,
                    "lastName": query.last_name,
                    "state": query.state_hint,
                }
            ],
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
        {
            "selection": [
                {"uaid": ""},
                {"name": query.full_name},
            ],
            "pagination": {"pageSize": 51, "currentPage": 1},
        },
    ]

    attempt_idx = 0
    for endpoint_url in endpoint_urls:
        for post_body in candidate_payloads:
            attempt_idx += 1
            probe = adapter.session.post(
                endpoint_url,
                json=post_body,
                timeout=20,
                allow_redirects=True,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "Origin": "https://www.usta.com",
                    "Referer": response.url,
                },
            )
            print(
                f"api_probe_attempt_{attempt_idx}=endpoint:{endpoint_url} "
                f"status:{probe.status_code} content_type:{probe.headers.get('content-type', '')}"
            )
            print(f"api_probe_attempt_{attempt_idx}_payload={post_body}")
            try:
                payload = probe.json()
            except ValueError:
                snippet = probe.text[:180].replace("\n", " ").strip()
                print(f"api_probe_attempt_{attempt_idx}_json=failed body_startswith={snippet!r}")
                continue

            # Save parseable JSON probe for reverse engineering.
            probe_path = out_path.with_name(f"{out_path.stem}.api_attempt_{attempt_idx}.json")
            probe_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            if isinstance(payload, dict):
                keys = list(payload.keys())[:20]
                count = len(payload.get("data", [])) if isinstance(payload.get("data"), list) else "n/a"
                print(
                    f"api_probe_attempt_{attempt_idx}_json=ok "
                    f"keys={keys} data_count={count} saved={probe_path}"
                )
            else:
                print(
                    f"api_probe_attempt_{attempt_idx}_json=ok "
                    f"type={type(payload).__name__} saved={probe_path}"
                )

            # Keep probing if this is an error-only response.
            if isinstance(payload, dict) and payload.get("errors"):
                print(
                    f"api_probe_attempt_{attempt_idx}_has_errors="
                    f"{payload.get('errors')}"
                )
                continue

            # Stop after first non-error JSON payload.
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
