from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import CandidateProfile, PlayerQuery
from .base import SourceAdapter


class UstaAdapter(SourceAdapter):
    source_name = "usta"
    required_auth = False
    CITY_STATE_RE = re.compile(r"([A-Za-z .'-]+),\s*([A-Z]{2})\b")
    SEARCH_API_URL = "https://services.usta.com/v1/dataexchange/profile/search/public"

    def search_player(self, query: PlayerQuery) -> list[CandidateProfile]:
        self.validate_configuration()
        api_exc: Exception | None = None
        try:
            api_candidates = self._search_via_api(query)
            if api_candidates:
                return api_candidates
        except Exception as exc:  # noqa: BLE001
            api_exc = exc

        params = {
            "q": query.full_name,
            "state": query.state_hint,
        }
        response = self.session.get(self.search_url, params=params, timeout=20, allow_redirects=True)
        response.raise_for_status()
        html_candidates = self._parse_candidates(response)
        if html_candidates:
            return html_candidates
        if api_exc:
            raise api_exc
        return []

    def _search_via_api(self, query: PlayerQuery) -> list[CandidateProfile]:
        payload = {
            "pagination": {"pageSize": "51", "currentPage": "1"},
            "selection": {"name": {"fname": query.first_name, "lname": query.last_name}},
        }
        response = self.session.post(
            self.SEARCH_API_URL,
            json=payload,
            timeout=20,
            allow_redirects=True,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": "https://www.usta.com",
                "Referer": "https://www.usta.com/",
            },
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return []
        if data.get("errors"):
            raise ValueError(f"usta api errors={data.get('errors')}")

        items = data.get("data")
        if not isinstance(items, list):
            return []

        candidates: list[CandidateProfile] = []
        seen_urls: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue

            full_name = str(item.get("name") or item.get("fullName") or "").strip()
            parts = full_name.split()
            if len(parts) < 2:
                continue

            city = str(item.get("city") or "").strip() or None
            state = str(item.get("state") or "").strip() or None
            uaid = str(item.get("uaid") or item.get("playerId") or "").strip()
            profile_url = (
                f"https://www.usta.com/en/home/play/player-search/profile.html#uaid={uaid}"
                if uaid
                else self.search_url
            )
            if profile_url in seen_urls:
                continue
            seen_urls.add(profile_url)

            candidates.append(
                CandidateProfile(
                    first_name=parts[0],
                    last_name=" ".join(parts[1:]),
                    city=city,
                    state=state,
                    profile_url=profile_url,
                    ratings=[],
                )
            )

        return candidates

    def _parse_candidates(self, response):  # type: ignore[override]
        soup = BeautifulSoup(response.text, "html.parser")
        candidates: list[CandidateProfile] = []
        seen_urls: set[str] = set()

        for anchor in soup.select("a[href*='player-search/profile.html#uaid=']"):
            href = anchor.get("href", "").strip()
            if not href:
                continue
            profile_url = urljoin(response.url, href)
            if profile_url in seen_urls:
                continue
            seen_urls.add(profile_url)

            name_text = " ".join(anchor.get_text(" ", strip=True).split())
            parts = name_text.split()
            if len(parts) < 2:
                continue

            row_text = " ".join(anchor.parent.get_text(" ", strip=True).split())
            city = None
            state = None
            city_state = self.CITY_STATE_RE.search(row_text)
            if city_state:
                city = city_state.group(1).strip()
                state = city_state.group(2).strip()

            candidates.append(
                CandidateProfile(
                    first_name=parts[0],
                    last_name=" ".join(parts[1:]),
                    city=city,
                    state=state,
                    profile_url=profile_url,
                    ratings=[],
                )
            )

        return candidates

    def is_required(self) -> bool:
        return False
