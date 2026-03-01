from pathlib import Path

import pytest

from alta_tool.io.local_excel import LocalExcelClient
from alta_tool.models import OutputRow

openpyxl = pytest.importorskip("openpyxl")


def _make_workbook(path: Path, *, headers: list[str], data_rows: list[list[str]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Input"
    ws.append(headers)
    for row in data_rows:
        ws.append(row)
    wb.save(path)


def test_local_excel_read_input_and_write_output(tmp_path: Path) -> None:
    workbook = tmp_path / "players.xlsx"
    _make_workbook(
        workbook,
        headers=["first_name", "last_name", "city_hint", "state_hint"],
        data_rows=[
            ["Jane", "Doe", "Atlanta", "ga"],
            ["", "Skip", "", ""],
        ],
    )

    client = LocalExcelClient(str(workbook))
    queries = client.read_input()
    assert len(queries) == 1
    assert queries[0].first_name == "Jane"
    assert queries[0].state_hint == "GA"

    rows = [
        OutputRow(
            first_name="Jane",
            last_name="Doe",
            player_city="Atlanta",
            highest_rating_t2="4.0",
            highest_year_t2=2024,
            profile_url_t2="https://t2",
            highest_rating_ultimate=None,
            highest_year_ultimate=None,
            profile_url_ultimate=None,
            profile_url_usta=None,
            winning_rating="4.0",
            winning_play_year=2024,
            winning_source="t2",
            profile_url="https://t2",
            match_confidence="high",
            status="ok",
            notes="- t2_no_ratings\n- t2_ambiguous_urls:\n  - https://one\n  - https://two",
        )
    ]
    client.write_output(rows)

    wb = openpyxl.load_workbook(workbook)
    assert "Output" in wb.sheetnames
    out = wb["Output"]
    assert out.cell(row=1, column=1).value == "first_name"
    assert out.cell(row=2, column=1).value == "Jane"
    assert out.cell(row=2, column=17).alignment.wrap_text is True
    assert "\n" in out.cell(row=2, column=17).value


def test_local_excel_requires_input_tab(tmp_path: Path) -> None:
    workbook = tmp_path / "players.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "Sheet1"
    wb.save(workbook)

    with pytest.raises(ValueError, match="Missing required worksheet tab 'Input'"):
        LocalExcelClient(str(workbook)).read_input()


def test_local_excel_requires_required_headers(tmp_path: Path) -> None:
    workbook = tmp_path / "players.xlsx"
    _make_workbook(workbook, headers=["first_name"], data_rows=[["Jane"]])

    with pytest.raises(ValueError, match="Input tab missing required columns"):
        LocalExcelClient(str(workbook)).read_input()
