# alta-ratings

CLI tool to read Georgia player names from Google Sheets, query tennis rating sources, and write consolidated output.

## Quick start

1. Install `uv` (https://docs.astral.sh/uv/).
2. Sync dependencies: `uv sync --extra dev`
3. Copy `.env.example` to `.env` and fill values.
4. Run CLI: `uv run alta-ratings run`
5. Run tests: `uv run pytest -q`

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
- `winning_rating`
- `winning_play_year`
- `winning_source`
- `profile_url`
- `match_confidence`
- `status`
- `notes`

If duplicate profiles remain after filtering, row status is `ambiguous` and `notes` includes `candidate_urls=`.
