# alta-ratings

CLI tool to read Georgia player names from a sheet source (Google Sheets or local Excel), query tennis rating sources, and write consolidated output.

Project location: `python/` (this directory). If you are in repo root, run `cd python` first.

## Quick start

1. Install `uv` (https://docs.astral.sh/uv/).
2. Sync dependencies: `uv sync --extra dev`
3. Copy `.env.example` to `.env` and fill values.
4. Run CLI: `uv run alta-ratings run`
5. Run tests: `uv run pytest -q`

## Sheet backends

`run` supports two sheet backends:

- `google` (default)
- `local` (`.xlsx` file; compatible with Apple Numbers and Excel)

Examples:

- `uv run alta-ratings run`
- `uv run alta-ratings run --io-backend local` or `uv run alta-ratings run --io-backend local --local-workbook <xlsx path>`

## Local Excel setup (`.env`)

For local mode, set:

- `LOCAL_WORKBOOK_PATH=/absolute/path/to/players.xlsx`

or pass `--local-workbook` at runtime.

Workbook requirements:

- Workbook must be `.xlsx`
- Input tab must be named exactly `Input`
- Output tab is named `Output` (created automatically if missing)

## Google Sheets setup (`.env`)

Required env vars for Google integration:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_SHEET_ID`

These are only required when using `--io-backend google` (or default mode).

### 1) Create a Google service account key JSON

1. Open Google Cloud Console.
2. Create/select a project.
3. Enable `Google Sheets API` and `Google Drive API`.
4. Go to `IAM & Admin` -> `Service Accounts`.
5. Create a service account (any name).
6. Open the service account -> `Keys` -> `Add key` -> `Create new key` -> `JSON`.
7. Save that JSON file locally (for example `google-sa.json`).

Set in `.env`:

`GOOGLE_SERVICE_ACCOUNT_JSON=/absolute/path/to/google-sa.json`

### 2) Share your Google Sheet with the service account

1. Open the JSON file and copy `client_email`.
2. Open your Google Sheet.
3. Click `Share` and add that `client_email` with `Editor` access.

### 3) Get the Google Sheet ID

From sheet URL:

`https://docs.google.com/spreadsheets/d/<THIS_IS_SHEET_ID>/edit#gid=0`

Set in `.env`:

`GOOGLE_SHEET_ID=<THIS_IS_SHEET_ID>`

### 4) Input tab requirements

Create a tab named exactly `Input` with headers:

- `first_name`
- `last_name`
- optional: `city_hint`
- optional: `state_hint`

## Source configuration

- T2 is required.
- Ultimate is required.
- USTA is best-effort (auth optional), but include `USTA_SEARCH_URL` to query it each run.

## Ultimate response debugging

Use this script to inspect what Ultimate search actually returns:

`uv run python scripts/inspect_ultimate_search.py --first-name Jane --last-name Doe --state GA`

It prints status/final URL/content type and saves the full raw body to:
- `.cache/ultimate_search_response.txt` (default)

## T2 response debugging

Use this script to inspect what T2 search actually returns:

`uv run python scripts/inspect_t2_search.py --first-name Jane --last-name Doe --state GA`

It prints status/final URL/content type and saves the full raw body to:
- `.cache/t2_search_response.txt` (default)

## USTA response debugging

Use this script to inspect what USTA search actually returns:

`uv run python scripts/inspect_usta_search.py --first-name Jane --last-name Doe --state GA`

It prints status/final URL/content type and saves the full raw body to:
- `.cache/usta_search_response.txt` (default)

## Input sheet (`Input` tab)

Required columns:
- `first_name`
- `last_name`

Optional columns:
- `city_hint`
- `state_hint` (defaults to `GA`)

## Output sheet (`Output` tab)

- `first_name`
- `last_name`
- `player_city`
- `highest_rating_t2`
- `highest_year_t2`
- `profile_url_t2`
- `highest_rating_ultimate`
- `highest_year_ultimate`
- `profile_url_ultimate`
- `profile_url_usta`
- `winning_source`
- `winning_rating`
- `winning_play_year`
- `division_ranking`
- `league_ranking`
- `profile_url`
- `match_confidence`
- `status`
- `notes`

If duplicate profiles remain after filtering, row status is `ambiguous` and `notes` includes a `candidate_urls` section.
