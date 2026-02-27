# alta-ratings

CLI tool to read Georgia player names from Google Sheets, query tennis rating sources, and write consolidated output.

## Quick start

1. Install `uv` (https://docs.astral.sh/uv/).
2. Sync dependencies: `uv sync --extra dev`
3. Copy `.env.example` to `.env` and fill values.
4. Run CLI: `uv run alta-ratings run`
5. Run tests: `uv run pytest -q`

## Source configuration

- Ultimate is required.
- T2 is optional by default (`ENABLE_T2=false`).
- Set `ENABLE_T2=true` only when T2 login/search config is ready.

## Ultimate response debugging

Use this script to inspect what Ultimate search actually returns:

`uv run python scripts/inspect_ultimate_search.py --first-name Jane --last-name Doe --state GA`

It prints status/final URL/content type and saves the full raw body to:
- `.cache/ultimate_search_response.txt` (default)

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
- `highest_rating`
- `play_year`
- `winning_source`
- `profile_url`
- `match_confidence`
- `status`
- `notes`

If duplicate profiles remain after filtering, row status is `ambiguous` and `notes` includes `candidate_urls=`.
