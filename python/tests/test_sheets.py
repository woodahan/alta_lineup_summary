from alta_tool.models import OutputRow
from alta_tool.io.google import GoogleSheetsClient


class FakeWorksheet:
    def __init__(self, title: str, rows: list[dict[str, str]]):
        self.title = title
        self._rows = rows
        self.cleared = False
        self.updated_values = None
        self.formatted_ranges = []

    def get_all_records(self, default_blank: str = ""):
        return self._rows

    def row_values(self, index: int):
        if index != 1:
            return []
        return ["first_name", "last_name", "city_hint", "state_hint"]

    def clear(self):
        self.cleared = True

    def update(self, values, range_name: str):
        self.updated_values = (values, range_name)

    def format(self, range_name: str, cell_format: dict):
        self.formatted_ranges.append((range_name, cell_format))


class FakeSpreadsheet:
    def __init__(self):
        self.input_ws = FakeWorksheet(
            "Input",
            [
                {"first_name": "Jane", "last_name": "Doe", "city_hint": "Atlanta", "state_hint": "GA"},
                {"first_name": "", "last_name": "Missing"},
            ],
        )
        self.output_ws = FakeWorksheet("Output", [])

    def worksheet(self, name: str):
        if name == "Input":
            return self.input_ws
        if name == "Output":
            return self.output_ws
        raise ValueError(name)

    def add_worksheet(self, title: str, rows: int, cols: int):
        _ = rows, cols
        self.output_ws = FakeWorksheet(title, [])
        return self.output_ws


class FakeGspreadClient:
    def __init__(self, spreadsheet: FakeSpreadsheet):
        self._spreadsheet = spreadsheet

    def open_by_key(self, sheet_id: str):
        assert sheet_id == "sheet-id"
        return self._spreadsheet


def test_sheets_read_and_write(monkeypatch):
    fake_spreadsheet = FakeSpreadsheet()

    def fake_service_account(filename: str):
        assert filename == "/tmp/sa.json"
        return FakeGspreadClient(fake_spreadsheet)

    monkeypatch.setattr("alta_tool.io.google.gspread.service_account", fake_service_account)

    client = GoogleSheetsClient(service_account_json="/tmp/sa.json", sheet_id="sheet-id")
    queries = client.read_input()
    assert len(queries) == 1
    assert queries[0].first_name == "Jane"

    out = [
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
            notes="",
        )
    ]
    client.write_output(out)

    values, range_name = fake_spreadsheet.output_ws.updated_values
    assert range_name == "A1"
    assert values[0][0] == "first_name"
    assert values[1][0] == "Jane"
    assert "highest_rating_t2" in values[0]
    assert "winning_rating" in values[0]
    assert ("Q:Q", {"wrapStrategy": "WRAP"}) in fake_spreadsheet.output_ws.formatted_ranges
