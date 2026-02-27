from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import CandidateProfile, PlayerQuery, RawRating


class SourceAdapter(ABC):
    source_name: str
    required_auth: bool

    def __init__(self, *, username: str | None, password: str | None, login_url: str | None, search_url: str | None, cache_dir: str):
        self.username = username
        self.password = password
        self.login_url = login_url
        self.search_url = search_url
        self.cache_path = Path(cache_dir) / f"{self.source_name}_cookies.json"
        self.session = requests.Session()

    def validate_configuration(self) -> None:
        if not self.search_url:
            raise ValueError(f"{self.source_name} SEARCH_URL is required")
        if self.required_auth:
            if not self.username or not self.password:
                raise ValueError(f"{self.source_name} credentials are required")
            if not self.login_url:
                raise ValueError(f"{self.source_name} LOGIN_URL is required")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=3), reraise=True)
    def authenticate(self) -> tuple[bool, str]:
        self.validate_configuration()
        if not self.required_auth:
            return True, "auth not required"
        payload = {
            "username": self.username,
            "password": self.password,
        }
        response = self.session.post(self.login_url, json=payload, timeout=20)
        if response.status_code >= 400:
            return False, f"login failed ({response.status_code})"
        self._save_cookies()
        return True, "ok"

    def _save_cookies(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        cookie_dict = requests.utils.dict_from_cookiejar(self.session.cookies)
        self.cache_path.write_text(json.dumps(cookie_dict), encoding="utf-8")

    def load_cached_cookies(self) -> None:
        if not self.cache_path.exists():
            return
        raw = self.cache_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        jar = requests.utils.cookiejar_from_dict(data)
        self.session.cookies.update(jar)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=3), reraise=True)
    def search_player(self, query: PlayerQuery) -> list[CandidateProfile]:
        self.validate_configuration()
        params = {
            "q": query.full_name,
            "state": query.state_hint,
        }
        response = self.session.get(self.search_url, params=params, timeout=20)
        response.raise_for_status()
        return self._parse_candidates(response)

    def _parse_candidates(self, response: requests.Response) -> list[CandidateProfile]:
        data = response.json()
        profiles = data.get("profiles", []) if isinstance(data, dict) else []
        candidates: list[CandidateProfile] = []

        for item in profiles:
            ratings: list[RawRating] = []
            for rating in item.get("ratings", []) or []:
                value = str(rating.get("rating", "")).strip()
                year = int(rating.get("year", 0) or 0)
                if value and year:
                    ratings.append(RawRating(value=value, year=year))

            candidates.append(
                CandidateProfile(
                    first_name=str(item.get("first_name", "")).strip(),
                    last_name=str(item.get("last_name", "")).strip(),
                    city=str(item.get("city", "")).strip() or None,
                    state=str(item.get("state", "")).strip() or None,
                    profile_url=str(item.get("profile_url", "")).strip(),
                    ratings=ratings,
                )
            )
        return [c for c in candidates if c.first_name and c.last_name and c.profile_url]

    @abstractmethod
    def is_required(self) -> bool:
        raise NotImplementedError
