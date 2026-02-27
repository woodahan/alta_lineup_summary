from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import CandidateProfile, PlayerQuery, RawRating
from .base import SourceAdapter


class UltimateAdapter(SourceAdapter):
    source_name = "ultimate"
    required_auth = True

    def _looks_like_sign_in_page(self, html: str, url: str | None = None) -> bool:
        haystack = (html or "").lower()
        url_value = (url or "").lower()
        return "sessions - ultimate tennis" in haystack or "/sign_in" in url_value

    def authenticate(self) -> tuple[bool, str]:
        self.validate_configuration()

        # Ultimate uses form-based sign-in (not JSON credentials).
        login_page = self.session.get(self.login_url, timeout=20)
        login_page.raise_for_status()

        soup = BeautifulSoup(login_page.text, "html.parser")
        token_input = soup.select_one("input[name='authenticity_token']")
        authenticity_token = token_input.get("value", "").strip() if token_input else ""

        payload_variants = [
            {
                "authenticity_token": authenticity_token,
                "player[email]": self.username or "",
                "player[password]": self.password or "",
                "commit": "Sign In",
            },
            {
                "authenticity_token": authenticity_token,
                "user[email]": self.username or "",
                "user[password]": self.password or "",
                "commit": "Sign In",
            },
        ]

        for payload in payload_variants:
            response = self.session.post(self.login_url, data=payload, timeout=20, allow_redirects=True)
            if response.status_code >= 400:
                continue
            if not self._looks_like_sign_in_page(response.text, response.url):
                self._save_cookies()
                return True, "ok"

        return False, "login appears unsuccessful (still on sign-in page)"

    def search_player(self, query: PlayerQuery) -> list[CandidateProfile]:
        self.validate_configuration()

        # Ultimate member search is form POST with separate first/last fields.
        search_page = self.session.get(self.search_url, timeout=20)
        search_page.raise_for_status()
        if self._looks_like_sign_in_page(search_page.text, search_page.url):
            raise ValueError("ultimate search page requires login; session not authenticated")

        soup = BeautifulSoup(search_page.text, "html.parser")
        token_input = soup.select_one("form#new_search input[name='authenticity_token']")
        token = token_input.get("value", "").strip() if token_input else ""
        payload = {
            "authenticity_token": token,
            "search[first_name_begins_with]": query.first_name,
            "search[last_name_begins_with]": query.last_name,
            "commit": "Find player",
        }

        response = self.session.post(self.search_url, data=payload, timeout=20, allow_redirects=True)
        response.raise_for_status()
        if self._looks_like_sign_in_page(response.text, response.url):
            raise ValueError("ultimate search redirected to sign-in page; authentication is not established")

        return self._parse_candidates(response)

    def _parse_candidates(self, response):  # type: ignore[override]
        soup = BeautifulSoup(response.text, "html.parser")
        results_container = soup.select_one("div.search_results")
        if not results_container:
            title_match = re.search(r"<title>(.*?)</title>", response.text, flags=re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else "unknown"
            raise ValueError(
                f"ultimate search page missing results container (status={response.status_code}, title={title!r})"
            )

        candidates: list[CandidateProfile] = []
        rows = results_container.select("table#player_directory tbody tr.player")
        for row in rows:
            link = row.select_one("td.first a[href]")
            if not link:
                continue

            href = link.get("href", "").strip()
            if not href:
                continue
            absolute = urljoin(response.url, href)

            raw_name = " ".join(link.get_text(" ", strip=True).split())
            if not raw_name:
                continue
            parts = raw_name.split()
            if len(parts) < 2:
                continue
            first_name = parts[0]
            last_name = " ".join(parts[1:])

            location_cell = row.select_one("td.location")
            block_text = " ".join((location_cell or row).get_text(" ", strip=True).split())
            city = None
            state = None
            city_state = re.search(r"([A-Za-z .'-]+),\s*([A-Z]{2})\b", block_text)
            if city_state:
                city = city_state.group(1).strip()
                state = city_state.group(2).strip()

            ratings = self._fetch_history_ratings(absolute)
            if not ratings:
                # Fallback to current displayed level in search table when history parsing is unavailable.
                level_text = " ".join((row.select_one("td.last") or row).get_text(" ", strip=True).split())
                level_match = self.RATING_RE.search(level_text)
                if level_match:
                    ratings = [RawRating(value=level_match.group(1), year=datetime.utcnow().year)]

            candidates.append(
                CandidateProfile(
                    first_name=first_name,
                    last_name=last_name,
                    city=city,
                    state=state,
                    profile_url=absolute,
                    ratings=ratings,
                )
            )

        return candidates

    def _fetch_history_ratings(self, profile_url: str) -> list[RawRating]:
        ratings: list[RawRating] = []
        seen: set[tuple[str, int]] = set()
        try:
            history_response = self.session.get(profile_url, timeout=20)
            history_response.raise_for_status()
        except Exception:  # noqa: BLE001
            return ratings

        soup = BeautifulSoup(history_response.text, "html.parser")
        for row in soup.select("tr"):
            row_text = " ".join(row.get_text(" ", strip=True).split())
            if not row_text:
                continue
            year_match = self.YEAR_RE.search(row_text)
            rating_match = self.RATING_RE.search(row_text)
            if not year_match or not rating_match:
                continue
            year = int(year_match.group(0))
            value = rating_match.group(1)
            key = (value, year)
            if key in seen:
                continue
            seen.add(key)
            ratings.append(RawRating(value=value, year=year))
        return ratings

    def is_required(self) -> bool:
        return True
    YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
    RATING_RE = re.compile(r"\b([2-6](?:\.0|\.5)?)\b")
