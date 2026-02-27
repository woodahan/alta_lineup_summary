from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import CandidateProfile, PlayerQuery, RawRating
from .base import SourceAdapter


class UstaAdapter(SourceAdapter):
    source_name = "usta"
    required_auth = False
    CITY_STATE_RE = re.compile(r"([A-Za-z .'-]+),\s*([A-Z]{2})\b")
    SEARCH_API_URL = "https://services.usta.com/v1/dataexchange/profile/search/public"
    PROFILE_PAGE_URL = "https://www.usta.com/en/home/play/player-search/profile.html"
    PROFILE_API_CANDIDATES = (
        "https://services.usta.com/v1/dataexchange/profile/public",
        "https://services.usta.com/v1/dataexchange/profile/search/details/public",
        "https://services.usta.com/v1/dataexchange/profile/details/public",
    )
    NTRP_RE = re.compile(r"\b([1-7](?:\.[05])(?:[A-Za-z])?)\b")
    DATE_RE = re.compile(
        r"\b("
        r"(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|"
        r"Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2},\s+\d{4}"
        r"|\d{4}-\d{2}-\d{2}"
        r"|\d{1,2}/\d{1,2}/\d{4}"
        r")\b",
        flags=re.IGNORECASE,
    )

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

            name_obj = item.get("name") if isinstance(item.get("name"), dict) else {}
            first_name = str(
                name_obj.get("fname")
                or name_obj.get("firstName")
                or item.get("firstName")
                or ""
            ).strip()
            last_name = str(
                name_obj.get("lname")
                or name_obj.get("lastName")
                or item.get("lastName")
                or ""
            ).strip()
            if not first_name or not last_name:
                full_name = str(item.get("name") or item.get("fullName") or "").strip()
                parts = full_name.split()
                if len(parts) >= 2:
                    first_name = parts[0]
                    last_name = " ".join(parts[1:])
            if not first_name or not last_name:
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
            ratings = self._fetch_profile_ratings(uaid=uaid, profile_url=profile_url)

            candidates.append(
                CandidateProfile(
                    first_name=first_name,
                    last_name=last_name,
                    city=city,
                    state=state,
                    profile_url=profile_url,
                    ratings=ratings,
                )
            )

        return candidates

    def _fetch_profile_ratings(self, *, uaid: str, profile_url: str) -> list[RawRating]:
        if not uaid:
            return []

        payloads = (
            {"selection": {"uaid": uaid}},
            {"selection": {"playerUaid": uaid}},
            {"selection": {"playerId": uaid}},
            {"uaid": uaid},
        )
        for endpoint in self.PROFILE_API_CANDIDATES:
            for payload in payloads:
                try:
                    response = self.session.post(
                        endpoint,
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
                    if response.status_code >= 400:
                        continue
                    data = response.json()
                except Exception:  # noqa: BLE001
                    continue
                ratings = self._extract_ratings_from_json(data)
                if ratings:
                    return ratings

        try:
            response = self.session.get(
                self.PROFILE_PAGE_URL,
                params={"uaid": uaid},
                timeout=20,
                allow_redirects=True,
                headers={"Referer": self.search_url or "https://www.usta.com/"},
            )
            if response.status_code < 400:
                ratings = self._extract_ratings_from_html(response.text)
                if ratings:
                    return ratings
        except Exception:  # noqa: BLE001
            pass

        try:
            response_hash = self.session.get(
                profile_url,
                timeout=20,
                allow_redirects=True,
                headers={"Referer": self.search_url or "https://www.usta.com/"},
            )
            if response_hash.status_code < 400:
                ratings = self._extract_ratings_from_html(response_hash.text)
                if ratings:
                    return ratings
        except Exception:  # noqa: BLE001
            pass

        return []

    def _extract_ratings_from_json(self, payload: object) -> list[RawRating]:
        if not isinstance(payload, (dict, list)):
            return []

        ntrp_value = self._find_first_ntrp(payload)
        if not ntrp_value:
            return []

        last_played = self._find_last_played(payload)
        if not last_played:
            return []
        year = self._year_from_date(last_played)
        if not year:
            return []
        return [RawRating(value=ntrp_value, year=year)]

    def _extract_ratings_from_html(self, html_text: str) -> list[RawRating]:
        if not html_text:
            return []
        soup = BeautifulSoup(html_text, "html.parser")
        text = " ".join(soup.get_text(" ", strip=True).split())

        ntrp_value = None
        ntrp_label = re.search(r"NTRP(?:\s+Rating)?\s*[:\-]?\s*([1-7](?:\.[05])(?:[A-Za-z])?)", text, flags=re.IGNORECASE)
        if ntrp_label:
            ntrp_value = ntrp_label.group(1)
        else:
            ntrp_value = self._find_ntrp_in_text(text)
        if not ntrp_value:
            return []

        date_match = re.search(r"Last\s+Played\s*[:\-]?\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})", text, flags=re.IGNORECASE)
        if date_match:
            last_played = date_match.group(1)
        else:
            last_played = self._find_date_in_text(text)
        if not last_played:
            return []

        year = self._year_from_date(last_played)
        if not year:
            return []

        return [RawRating(value=ntrp_value, year=year)]

    def _find_first_ntrp(self, value: object) -> str | None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_l = key.lower()
                if "ntrp" in key_l or key_l in {"rating", "currentrating"}:
                    candidate = self._find_ntrp_in_text(str(child))
                    if candidate:
                        return candidate
                nested = self._find_first_ntrp(child)
                if nested:
                    return nested
            return None
        if isinstance(value, list):
            for child in value:
                nested = self._find_first_ntrp(child)
                if nested:
                    return nested
            return None
        return self._find_ntrp_in_text(str(value))

    def _find_last_played(self, value: object) -> str | None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_l = key.lower()
                if "lastplayed" in key_l or (("last" in key_l and "play" in key_l) or key_l == "playdate"):
                    candidate = self._find_date_in_text(str(child))
                    if candidate:
                        return candidate
                nested = self._find_last_played(child)
                if nested:
                    return nested
            return None
        if isinstance(value, list):
            for child in value:
                nested = self._find_last_played(child)
                if nested:
                    return nested
            return None
        return self._find_date_in_text(str(value))

    def _find_ntrp_in_text(self, text: str) -> str | None:
        if not text:
            return None
        match = self.NTRP_RE.search(text)
        if not match:
            return None
        return match.group(1).upper()

    def _find_date_in_text(self, text: str) -> str | None:
        if not text:
            return None
        match = self.DATE_RE.search(text)
        if not match:
            return None
        return match.group(1)

    def _year_from_date(self, value: str) -> int | None:
        value = value.strip()
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(value, fmt).year
            except ValueError:
                continue
        year_match = re.search(r"\b(19|20)\d{2}\b", value)
        if not year_match:
            return None
        return int(year_match.group(0))

    def _parse_candidates(self, response):  # type: ignore[override]
        soup = BeautifulSoup(response.text, "html.parser")
        candidates: list[CandidateProfile] = []
        seen_urls: set[str] = set()

        # Best-effort HTML parsing: pull profile links if server-rendered.
        for anchor in soup.select("a[href*='player-search/profile.html#uaid=']"):
            href = anchor.get("href", "").strip()
            if not href:
                continue
            profile_url = urljoin(response.url, href)
            if profile_url in seen_urls:
                continue
            seen_urls.add(profile_url)

            name_text = " ".join(anchor.get_text(" ", strip=True).split())
            if not name_text:
                continue
            parts = name_text.split()
            if len(parts) < 2:
                continue
            first_name = parts[0]
            last_name = " ".join(parts[1:])

            row_text = " ".join(anchor.parent.get_text(" ", strip=True).split())
            city = None
            state = None
            city_state = self.CITY_STATE_RE.search(row_text)
            if city_state:
                city = city_state.group(1).strip()
                state = city_state.group(2).strip()

            candidates.append(
                CandidateProfile(
                    first_name=first_name,
                    last_name=last_name,
                    city=city,
                    state=state,
                    profile_url=profile_url,
                    ratings=[],
                )
            )

        return candidates

    def is_required(self) -> bool:
        return False
