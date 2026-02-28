from __future__ import annotations

from typing import Literal

from ..config import Settings
from .base import SheetBackend
from .google import GoogleSheetsClient
from .local_excel import LocalExcelClient

IoBackend = Literal["google", "local"]


def build_sheet_backend(
    settings: Settings,
    *,
    io_backend: IoBackend,
    sheet_id_override: str | None = None,
    local_workbook_override: str | None = None,
) -> SheetBackend:
    if io_backend == "google":
        sheet_id = (sheet_id_override or settings.google_sheet_id).strip()
        service_account_json = settings.google_service_account_json.strip()
        missing: list[str] = []
        if not service_account_json:
            missing.append("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not sheet_id:
            missing.append("GOOGLE_SHEET_ID")
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Missing required configuration for google backend: {joined}")
        return GoogleSheetsClient(service_account_json=service_account_json, sheet_id=sheet_id)

    workbook_path = (local_workbook_override or settings.local_workbook_path or "").strip()
    if not workbook_path:
        raise ValueError(
            "Missing required configuration for local backend: "
            "set LOCAL_WORKBOOK_PATH or pass --local-workbook"
        )
    return LocalExcelClient(workbook_path=workbook_path)
