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
    RANK_NUMBER_RE = re.compile(r"(\d+)")

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
        by_key: dict[tuple[str, int], int] = {}
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
            division_ranking, league_ranking = self._extract_rankings(row)
            key = (value, year)
            if key in by_key:
                existing = ratings[by_key[key]]
                if existing.division_ranking is not None or existing.league_ranking is not None:
                    continue
                ratings[by_key[key]] = RawRating(
                    value=value,
                    year=year,
                    division_ranking=division_ranking,
                    league_ranking=league_ranking,
                )
                continue
            by_key[key] = len(ratings)
            ratings.append(
                RawRating(
                    value=value,
                    year=year,
                    division_ranking=division_ranking,
                    league_ranking=league_ranking,
                )
            )
        return ratings

    def _extract_rankings(self, row) -> tuple[int | None, int | None]:
        table = row.find_parent("table")
        header_map: dict[str, int] = {}
        if table:
            header_cells = table.select("tr th")
            if not header_cells:
                first_row = table.select_one("tr")
                if first_row:
                    header_cells = first_row.select("td, th")
            # Some pages collapse all labels into one header-like cell; index
            # mapping is unreliable in that shape, so use textual fallback only.
            if len(header_cells) > 1:
                header_map = {
                    self._normalize_header(cell.get_text(" ", strip=True)): idx
                    for idx, cell in enumerate(header_cells)
                }

        cells = row.find_all(["td", "th"])
        values = [cell.get_text(" ", strip=True) for cell in cells]
        row_text = " ".join(values)

        division_ranking = self._extract_rank_by_header(values, header_map, "division")
        league_ranking = self._extract_rank_by_header(values, header_map, "league")

        if division_ranking is None and league_ranking is None:
            division_ranking = self._extract_rank_by_header(values, header_map, "generic")
        if division_ranking is None and league_ranking is None:
            rating_match = self.RATING_RE.search(row_text)
            if rating_match:
                division_ranking, league_ranking = self._extract_ranks_after_rating(row_text, rating_match.group(1))

        return division_ranking, league_ranking

    def _extract_rank_by_header(
        self, values: list[str], header_map: dict[str, int], rank_type: str
    ) -> int | None:
        for header, idx in header_map.items():
            if idx >= len(values):
                continue
            if rank_type == "division" and self._is_division_rank_header(header):
                return self._parse_rank_number(values[idx])
            if rank_type == "league" and self._is_league_rank_header(header):
                return self._parse_rank_number(values[idx])
            if rank_type == "generic" and header == "rank":
                return self._parse_rank_number(values[idx])
        return None

    def _parse_rank_number(self, value: str) -> int | None:
        cleaned = value.strip()
        if not cleaned or cleaned in {"-", "N/A", "n/a"}:
            return None
        match = self.RANK_NUMBER_RE.search(cleaned)
        if not match:
            return None
        return int(match.group(1))

    def _normalize_header(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    def _is_division_rank_header(self, header: str) -> bool:
        return "rank" in header and ("division" in header or re.search(r"\bdiv\.?\b", header) is not None)

    def _is_league_rank_header(self, header: str) -> bool:
        return "rank" in header and ("league" in header or re.search(r"\bleag\.?\b", header) is not None)

    def _extract_ranks_after_rating(self, row_text: str, rating: str) -> tuple[int | None, int | None]:
        # Ultimate season rows are often rendered as:
        # "... <level/rating> <div_rank> <league_rank> <points> ..."
        token_pattern = re.compile(
            rf"(?<![\d.]){re.escape(rating)}(?![\d.])\s+(\d+)\s+(\d+)\b"
        )
        match = token_pattern.search(row_text)
        if not match:
            return None, None
        return int(match.group(1)), int(match.group(2))

    def is_required(self) -> bool:
        return True
    YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
    RATING_RE = re.compile(r"(?<![\d.])([2-7](?:\.(?:0|25|5|75))?-?)(?![\d.])")
