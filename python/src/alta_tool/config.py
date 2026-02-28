from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class SourceSettings:
    name: str
    username: str | None
    password: str | None
    login_url: str | None
    search_url: str | None
    required_auth: bool


@dataclass(frozen=True)
class Settings:
    google_service_account_json: str
    google_sheet_id: str
    local_workbook_path: str | None
    ultimate: SourceSettings
    t2: SourceSettings
    usta: SourceSettings
    cache_dir: str


def _source(prefix: str, *, required_auth: bool) -> SourceSettings:
    return SourceSettings(
        name=prefix.lower(),
        username=os.getenv(f"{prefix}_USERNAME"),
        password=os.getenv(f"{prefix}_PASSWORD"),
        login_url=os.getenv(f"{prefix}_LOGIN_URL"),
        search_url=os.getenv(f"{prefix}_SEARCH_URL"),
        required_auth=required_auth,
    )


def load_settings() -> Settings:
    load_dotenv()

    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    local_workbook_path = os.getenv("LOCAL_WORKBOOK_PATH", "").strip() or None
    cache_dir = os.getenv("ALTA_CACHE_DIR", ".cache/alta_tool").strip()

    settings = Settings(
        google_service_account_json=service_account_json,
        google_sheet_id=sheet_id,
        local_workbook_path=local_workbook_path,
        ultimate=_source("ULTIMATE", required_auth=True),
        t2=_source("T2", required_auth=True),
        usta=_source("USTA", required_auth=False),
        cache_dir=cache_dir,
    )
    validate_settings(settings)
    return settings


def validate_settings(settings: Settings) -> None:
    missing: list[str] = []

    for source in (settings.t2, settings.ultimate):
        if not source.username:
            missing.append(f"{source.name.upper()}_USERNAME")
        if not source.password:
            missing.append(f"{source.name.upper()}_PASSWORD")
        if not source.login_url:
            missing.append(f"{source.name.upper()}_LOGIN_URL")
        if not source.search_url:
            missing.append(f"{source.name.upper()}_SEARCH_URL")

    if missing:
        joined = ", ".join(sorted(set(missing)))
        raise ValueError(f"Missing required configuration: {joined}")
