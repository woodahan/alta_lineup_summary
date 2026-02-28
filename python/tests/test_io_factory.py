from pathlib import Path

import pytest

from alta_tool.config import Settings, SourceSettings
from alta_tool.io.factory import build_sheet_backend


def _source(name: str) -> SourceSettings:
    return SourceSettings(
        name=name,
        username="u",
        password="p",
        login_url="https://login",
        search_url="https://search",
        required_auth=True,
    )


def _settings(*, service_account_json: str = "/tmp/sa.json", sheet_id: str = "sheet-id", local_path: str | None = None) -> Settings:
    return Settings(
        google_service_account_json=service_account_json,
        google_sheet_id=sheet_id,
        local_workbook_path=local_path,
        ultimate=_source("ultimate"),
        t2=_source("t2"),
        usta=_source("usta"),
        cache_dir=".cache/alta_tool",
    )


def test_build_google_backend_requires_google_settings() -> None:
    settings = _settings(service_account_json="", sheet_id="")
    with pytest.raises(ValueError, match="google backend"):
        build_sheet_backend(settings, io_backend="google")


def test_build_local_backend_requires_workbook_path() -> None:
    settings = _settings(local_path=None)
    with pytest.raises(ValueError, match="LOCAL_WORKBOOK_PATH"):
        build_sheet_backend(settings, io_backend="local")


def test_build_local_backend_uses_override_path(tmp_path: Path) -> None:
    workbook = tmp_path / "players.xlsx"
    workbook.write_bytes(b"")
    settings = _settings(local_path=None)

    backend = build_sheet_backend(
        settings,
        io_backend="local",
        local_workbook_override=str(workbook),
    )

    assert backend.__class__.__name__ == "LocalExcelClient"
