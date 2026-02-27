from __future__ import annotations

from typing import Iterable

import gspread

from .models import OutputRow, PlayerQuery

INPUT_TAB = "Input"
OUTPUT_TAB = "Output"
REQUIRED_INPUT_HEADERS = ["first_name", "last_name"]


class SheetsClient:
    def __init__(self, service_account_json: str, sheet_id: str):
        self._gc = gspread.service_account(filename=service_account_json)
        self._sheet = self._gc.open_by_key(sheet_id)

    def read_input(self) -> list[PlayerQuery]:
        try:
            ws = self._sheet.worksheet(INPUT_TAB)
        except gspread.exceptions.WorksheetNotFound as exc:
            raise ValueError(
                "Missing required worksheet tab 'Input'. "
                "Create a tab named exactly 'Input' with headers: "
                "first_name,last_name,city_hint,state_hint"
            ) from exc
        rows = ws.get_all_records(default_blank="")
        if not ws.row_values(1):
            raise ValueError("Input tab is missing header row")

        header = [h.strip() for h in ws.row_values(1)]
        missing = [h for h in REQUIRED_INPUT_HEADERS if h not in header]
        if missing:
            raise ValueError(f"Input tab missing required columns: {', '.join(missing)}")

        queries: list[PlayerQuery] = []
        for row in rows:
            first = (row.get("first_name") or "").strip()
            last = (row.get("last_name") or "").strip()
            if not first or not last:
                continue
            city = (row.get("city_hint") or "").strip() or None
            state = (row.get("state_hint") or "").strip().upper() or "GA"
            queries.append(
                PlayerQuery(
                    first_name=first,
                    last_name=last,
                    city_hint=city,
                    state_hint=state,
                )
            )
        return queries

    def write_output(self, rows: Iterable[OutputRow]) -> None:
        try:
            ws = self._sheet.worksheet(OUTPUT_TAB)
        except gspread.exceptions.WorksheetNotFound:
            ws = self._sheet.add_worksheet(title=OUTPUT_TAB, rows=1000, cols=20)

        values = [OutputRow.headers()]
        values.extend(row.to_sheet_row() for row in rows)

        ws.clear()
        ws.update(values=values, range_name="A1")
