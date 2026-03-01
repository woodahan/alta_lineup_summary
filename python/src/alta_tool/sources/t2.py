from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import CandidateProfile, PlayerQuery, RawRating
from .base import SourceAdapter


class T2Adapter(SourceAdapter):
    source_name = "t2"
    required_auth = True
    RATING_RE = re.compile(r"(?<!\d)([2-7](?:\.(?:0|25|5|75))?-?)(?!\d)")
    YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
    TWO_DIGIT_YEAR_RE = re.compile(r"'(\d{2})\b")

    def _looks_like_login_page(self, html: str, url: str | None = None) -> bool:
        haystack = (html or "").lower()
        current_url = (url or "").lower()
        return (
            "player login" in haystack
            or "ctl00_pagebody_pnllogin" in haystack
            or "login.aspx" in current_url
        )

    def authenticate(self) -> tuple[bool, str]:
        self.validate_configuration()

        login_page = self.session.get(self.login_url, timeout=20, allow_redirects=True)
        login_page.raise_for_status()
        soup = BeautifulSoup(login_page.text, "html.parser")

        form = soup.select_one("form#aspnetForm")
        if not form:
            return False, "unable to find login form on T2 login page"

        payload: dict[str, str] = {}
        for hidden in form.select("input[type='hidden'][name]"):
            name = hidden.get("name", "").strip()
            if not name:
                continue
            payload[name] = hidden.get("value", "")

        # ASP.NET WebForms login controls used by T2.
        payload["ctl00$PageBody$txtLoginName"] = self.username or ""
        payload["ctl00$PageBody$txtPassword"] = self.password or ""
        payload["ctl00$PageBody$cbRememberLogin"] = "on"
        payload["ctl00$PageBody$btnLogin"] = "Login"

        action = form.get("action", "").strip()
        post_url = urljoin(login_page.url, action) if action else login_page.url
        response = self.session.post(
            post_url,
            data=payload,
            timeout=20,
            allow_redirects=True,
            headers={"Referer": login_page.url},
        )
        response.raise_for_status()

        if self._looks_like_login_page(response.text, response.url):
            return False, "login appears unsuccessful (still on login page)"

        # Validate session by visiting a protected page directly.
        verify = self.session.get(self.search_url, timeout=20, allow_redirects=True)
        verify.raise_for_status()
        if self._looks_like_login_page(verify.text, verify.url):
            return False, "login did not persist session for protected pages"

        self._save_cookies()
        return True, "ok"

    def search_player(self, query: PlayerQuery) -> list[CandidateProfile]:
        self.validate_configuration()
        search_page = self.session.get(self.search_url, timeout=20, allow_redirects=True)
        search_page.raise_for_status()
        if self._looks_like_login_page(search_page.text, search_page.url):
            raise ValueError("t2 search page requires login; session not authenticated")

        soup = BeautifulSoup(search_page.text, "html.parser")
        form = soup.select_one("form#aspnetForm")
        if not form:
            raise ValueError("t2 search page missing aspnet form")

        payload: dict[str, str] = {}
        for hidden in form.select("input[type='hidden'][name]"):
            name = hidden.get("name", "").strip()
            if name:
                payload[name] = hidden.get("value", "")

        # T2 player history search is an ASP.NET postback form.
        payload["ctl00$PageBody$txtLastName"] = query.last_name
        payload["ctl00$PageBody$txtFirstName"] = query.first_name
        payload["ctl00$PageBody$btnPlayerSearch"] = "Search"

        action = form.get("action", "").strip()
        post_url = urljoin(search_page.url, action) if action else search_page.url
        response = self.session.post(
            post_url,
            data=payload,
            timeout=20,
            allow_redirects=True,
            headers={"Referer": search_page.url},
        )
        response.raise_for_status()
        if self._looks_like_login_page(response.text, response.url):
            raise ValueError("t2 search redirected to login page; authentication not established")

        return self._parse_candidates(response)

    def _parse_candidates(self, response):  # type: ignore[override]
        soup = BeautifulSoup(response.text, "html.parser")
        players_select = soup.select_one("select#ctl00_PageBody_lbPlayers")
        if not players_select:
            return []

        options = players_select.select("option[value]")
        candidates: list[CandidateProfile] = []
        for option in options:
            player_id = option.get("value", "").strip()
            option_text = " ".join(option.get_text(" ", strip=True).split())
            if not player_id or not option_text:
                continue

            first_name, last_name, city = self._parse_option_text(option_text)
            profile_url = f"{response.url}?player_id={player_id}"
            ratings = self._fetch_player_history_ratings(response, player_id)

            candidates.append(
                CandidateProfile(
                    first_name=first_name,
                    last_name=last_name,
                    city=city,
                    state="GA" if city else None,
                    profile_url=profile_url,
                    ratings=ratings,
                )
            )

        return candidates

    def _parse_option_text(self, text: str) -> tuple[str, str, str | None]:
        # Example: "Doe, Jane Doe (x3687) Suwanee"
        cleaned = re.sub(r"\(x\d*\)", "", text, flags=re.IGNORECASE).strip()
        parts = [p.strip() for p in cleaned.split(",", maxsplit=1)]
        if len(parts) == 2:
            last_name = parts[0]
            rhs = parts[1]
            rhs_tokens = rhs.split()
            if len(rhs_tokens) >= 2:
                first_name = rhs_tokens[0]
                city = " ".join(rhs_tokens[1:]).strip() or None
            else:
                first_name = rhs_tokens[0] if rhs_tokens else ""
                city = None
        else:
            tokens = cleaned.split()
            first_name = tokens[0] if tokens else ""
            last_name = tokens[1] if len(tokens) > 1 else ""
            city = " ".join(tokens[2:]).strip() or None

        return first_name, last_name, city

    def _fetch_player_history_ratings(self, response, player_id: str) -> list[RawRating]:
        soup = BeautifulSoup(response.text, "html.parser")
        form = soup.select_one("form#aspnetForm")
        if not form:
            return []

        payload: dict[str, str] = {}
        for hidden in form.select("input[type='hidden'][name]"):
            name = hidden.get("name", "").strip()
            if name:
                payload[name] = hidden.get("value", "")

        payload["__EVENTTARGET"] = "ctl00$PageBody$lbPlayers"
        payload["__EVENTARGUMENT"] = ""
        payload["ctl00$PageBody$lbPlayers"] = player_id

        action = form.get("action", "").strip()
        post_url = urljoin(response.url, action) if action else response.url
        try:
            detail = self.session.post(
                post_url,
                data=payload,
                timeout=20,
                allow_redirects=True,
                headers={"Referer": response.url},
            )
            detail.raise_for_status()
        except Exception:  # noqa: BLE001
            return []

        detail_soup = BeautifulSoup(detail.text, "html.parser")
        history_block = detail_soup.select_one("div#ctl00_PageBody_PlayerHistory") or detail_soup
        ratings: list[RawRating] = []
        seen: set[tuple[str, int]] = set()
        for row in history_block.select("tr"):
            row_text = " ".join(row.get_text(" ", strip=True).split())
            if not row_text:
                continue
            year = self._extract_year(row_text)
            rating_match = self.RATING_RE.search(row_text)
            if year is None or not rating_match:
                continue
            rating = rating_match.group(1)
            key = (rating, year)
            if key in seen:
                continue
            seen.add(key)
            ratings.append(RawRating(value=rating, year=year))
        return ratings

    def _extract_year(self, row_text: str) -> int | None:
        four_digit = self.YEAR_RE.search(row_text)
        if four_digit:
            return int(four_digit.group(0))

        two_digit = self.TWO_DIGIT_YEAR_RE.search(row_text)
        if not two_digit:
            return None

        yy = int(two_digit.group(1))
        # Pivot at 70: '70-'99 => 1970-1999, otherwise 2000-2069.
        return 1900 + yy if yy >= 70 else 2000 + yy

    def is_required(self) -> bool:
        return True
