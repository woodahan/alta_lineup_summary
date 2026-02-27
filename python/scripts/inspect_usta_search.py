from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
import os
import re
from pathlib import Path
from typing import Any
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
        "--uaid",
        default="",
        help="Optional explicit USTA UAID for profile probe stage",
    )
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
    parser.add_argument(
        "--max-profile-attempts",
        type=int,
        default=11,
        help="Maximum number of profile probe attempts (default: 11)",
    )
    return parser


def _walk_json(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk_json(child)
        return
    if isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _extract_uaids(payload: Any) -> list[str]:
    uaids: list[str] = []
    if not isinstance(payload, (dict, list)):
        return uaids
    for key, value in _walk_json(payload):
        if key.lower() == "uaid":
            text = str(value).strip()
            if text and text not in uaids:
                uaids.append(text)
    return uaids


def _extract_ntrp_candidates(payload: Any) -> list[str]:
    ntrp_re = re.compile(r"\b([1-7](?:\.[05])(?:[A-Za-z])?)\b")
    hits: list[str] = []
    if not isinstance(payload, (dict, list)):
        return hits
    for key, value in _walk_json(payload):
        key_l = key.lower()
        if "ntrp" in key_l or "rating" in key_l:
            text = str(value)
            match = ntrp_re.search(text)
            if not match:
                continue
            candidate = match.group(1).upper()
            if candidate not in hits:
                hits.append(candidate)
    return hits


def _extract_last_played_candidates(payload: Any) -> list[str]:
    date_re = re.compile(
        r"\b("
        r"(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|"
        r"Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2},\s+\d{4}"
        r"|\d{4}-\d{2}-\d{2}"
        r"|\d{1,2}/\d{1,2}/\d{4}"
        r")\b",
        flags=re.IGNORECASE,
    )
    hits: list[str] = []
    if not isinstance(payload, (dict, list)):
        return hits
    for key, value in _walk_json(payload):
        key_l = key.lower()
        if "last" not in key_l and "play" not in key_l and key_l not in {"playdate", "date"}:
            continue
        text = str(value)
        match = date_re.search(text)
        if not match:
            continue
        candidate = match.group(1)
        if candidate not in hits:
            hits.append(candidate)
    return hits


def _to_year(value: str) -> int | None:
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).year
        except ValueError:
            continue
    year_match = re.search(r"\b(19|20)\d{2}\b", value)
    if not year_match:
        return None
    return int(year_match.group(0))


def _post_json(adapter: UstaAdapter, endpoint_url: str, body: dict[str, Any], referer: str):
    token = (os.getenv("USTA_ACCESS_TOKEN") or os.getenv("USTA_BEARER_TOKEN") or "").strip()
    auth = token if token.lower().startswith("bearer ") else (f"Bearer {token}" if token else "")
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.usta.com",
        "Referer": referer,
    }
    if auth:
        headers["Authorization"] = auth
    return adapter.session.post(
        endpoint_url,
        json=body,
        timeout=20,
        allow_redirects=True,
        headers=headers,
    )


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

    print("[1/6] Loading cached cookies...")
    adapter.load_cached_cookies()

    print("[2/6] Checking optional USTA auth...")
    ok, msg = adapter.authenticate()
    print(f"auth_ok={ok} message={msg}")
    token_configured = bool((os.getenv("USTA_ACCESS_TOKEN") or os.getenv("USTA_BEARER_TOKEN") or "").strip())
    print(f"bearer_token_configured={token_configured}")

    query = PlayerQuery(
        first_name=args.first_name.strip(),
        last_name=args.last_name.strip(),
        state_hint=args.state.strip().upper() or "GA",
    )

    print("[3/6] Sending raw USTA search request...")
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

    print(f"[4/6] Saved full body to: {out_path}")
    snippet = response.text[: max(args.show_chars, 0)]
    print("body_preview=")
    print(snippet)

    try:
        payload = response.json()
        top_keys = list(payload.keys())[:20] if isinstance(payload, dict) else []
        print(f"json_parse=ok type={type(payload).__name__} top_keys={top_keys}")
    except ValueError:
        print("json_parse=failed (response is not valid JSON)")

    print("[5/6] Probing search API endpoint + payload variants...")
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
    search_success_payload: Any | None = None
    for endpoint_url in endpoint_urls:
        for post_body in candidate_payloads:
            attempt_idx += 1
            probe = _post_json(adapter, endpoint_url, post_body, response.url)
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

            search_success_payload = payload
            break
        if search_success_payload is not None:
            break

    if search_success_payload is None:
        print("profile_probe=skipped (no successful search JSON payload)")
        return 0

    uaids = _extract_uaids(search_success_payload)
    if args.uaid.strip():
        explicit = args.uaid.strip()
        if explicit not in uaids:
            uaids.insert(0, explicit)
    uaids = uaids[:5]
    print(f"search_uaids={uaids}")
    if not uaids:
        print("profile_probe=skipped (no uaid found in search response)")
        return 0

    print("[6/6] Probing profile-detail endpoints...")
    profile_endpoint_candidates = [
        "https://services.usta.com/v1/dataexchange/profile/search/public",
        "https://services.usta.com/v1/dataexchange/profile/public",
    ]
    profile_payload_variants = [
        lambda uaid: {"selection": {"uaid": uaid}},
        lambda uaid: {"selection": {"nameOrUaid": uaid}},
        lambda uaid: {"selection": {"playerUaid": uaid}},
        lambda uaid: {"selection": {"playerId": uaid}},
        lambda uaid: {"selection": {"nameOrUaid": uaid}, "pagination": {"pageSize": "1", "currentPage": "1"}},
    ]

    profile_attempt = 0
    forbidden_count = 0
    for uaid in uaids:
        print(f"profile_target_uaid={uaid}")
        for endpoint_url in profile_endpoint_candidates:
            for build_payload in profile_payload_variants:
                if profile_attempt >= max(args.max_profile_attempts, 1):
                    print(
                        f"profile_probe_stop=max_attempts_reached({max(args.max_profile_attempts, 1)})"
                    )
                    print("profile_probe_done=no_attempt_found_both_ntrp_and_last_played")
                    return 0
                profile_attempt += 1
                body = build_payload(uaid)
                probe = _post_json(adapter, endpoint_url, body, response.url)
                print(
                    f"profile_probe_attempt_{profile_attempt}=uaid:{uaid} endpoint:{endpoint_url} "
                    f"status:{probe.status_code} content_type:{probe.headers.get('content-type', '')}"
                )
                print(f"profile_probe_attempt_{profile_attempt}_payload={body}")
                try:
                    profile_payload = probe.json()
                except ValueError:
                    snippet = probe.text[:180].replace("\n", " ").strip()
                    print(
                        f"profile_probe_attempt_{profile_attempt}_json=failed "
                        f"body_startswith={snippet!r}"
                    )
                    continue

                profile_path = out_path.with_name(
                    f"{out_path.stem}.profile_attempt_{profile_attempt}.json"
                )
                profile_path.write_text(json.dumps(profile_payload, indent=2), encoding="utf-8")
                if isinstance(profile_payload, dict):
                    keys = list(profile_payload.keys())[:20]
                    print(
                        f"profile_probe_attempt_{profile_attempt}_json=ok keys={keys} saved={profile_path}"
                    )
                else:
                    print(
                        f"profile_probe_attempt_{profile_attempt}_json=ok type={type(profile_payload).__name__} saved={profile_path}"
                    )

                ntrp_candidates = _extract_ntrp_candidates(profile_payload)
                last_played_candidates = _extract_last_played_candidates(profile_payload)
                print(f"profile_probe_attempt_{profile_attempt}_ntrp_candidates={ntrp_candidates}")
                print(f"profile_probe_attempt_{profile_attempt}_last_played_candidates={last_played_candidates}")
                years = [year for year in (_to_year(value) for value in last_played_candidates) if year]
                print(f"profile_probe_attempt_{profile_attempt}_years={years}")
                if isinstance(profile_payload, dict) and "error_description" in profile_payload:
                    print(
                        f"profile_probe_attempt_{profile_attempt}_auth_error="
                        f"{profile_payload.get('error_description')}"
                    )
                if isinstance(profile_payload, dict) and profile_payload.get("message") == "Forbidden":
                    print(f"profile_probe_attempt_{profile_attempt}_auth_error=Forbidden")
                    forbidden_count += 1
                    if forbidden_count >= 2:
                        print("profile_probe_stop=forbidden_threshold_reached(2)")
                        print("profile_probe_done=no_attempt_found_both_ntrp_and_last_played")
                        return 0

                if ntrp_candidates and years:
                    print("profile_probe_success=found_ntrp_and_last_played")
                    return 0

    print("profile_probe_done=no_attempt_found_both_ntrp_and_last_played")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
