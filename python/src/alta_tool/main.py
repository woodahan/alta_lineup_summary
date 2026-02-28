from __future__ import annotations

from collections import Counter

import typer

from .aggregate import process_player
from .config import Settings, load_settings
from .io import IoBackend, build_sheet_backend
from .sources import T2Adapter, UltimateAdapter, UstaAdapter
from .sources.base import SourceAdapter

app = typer.Typer(help="ALTA ratings aggregation CLI")


@app.callback()
def main() -> None:
    """ALTA ratings aggregation commands."""


def _build_adapters(settings: Settings) -> list[SourceAdapter]:
    adapters: list[SourceAdapter] = [
        T2Adapter(
            username=settings.t2.username,
            password=settings.t2.password,
            login_url=settings.t2.login_url,
            search_url=settings.t2.search_url,
            cache_dir=settings.cache_dir,
        ),
        UltimateAdapter(
            username=settings.ultimate.username,
            password=settings.ultimate.password,
            login_url=settings.ultimate.login_url,
            search_url=settings.ultimate.search_url,
            cache_dir=settings.cache_dir,
        ),
    ]

    if settings.usta.search_url:
        adapters.append(
            UstaAdapter(
                username=settings.usta.username,
                password=settings.usta.password,
                login_url=settings.usta.login_url,
                search_url=settings.usta.search_url,
                cache_dir=settings.cache_dir,
            )
        )
    return adapters


def _validate_required_auth(adapters: list[SourceAdapter]) -> None:
    for adapter in adapters:
        adapter.load_cached_cookies()
        if not adapter.required_auth:
            continue
        try:
            ok, message = adapter.authenticate()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"{adapter.source_name} auth request failed: {exc}") from exc
        if not ok:
            raise RuntimeError(f"{adapter.source_name} auth failed: {message}")


@app.command()
def run(
    io_backend: IoBackend = typer.Option(
        "google",
        "--io-backend",
        help="Sheet backend to use: 'google' or 'local'",
    ),
    sheet_id: str | None = typer.Option(None, help="Override GOOGLE_SHEET_ID from env"),
    local_workbook: str | None = typer.Option(
        None, "--local-workbook", help="Override LOCAL_WORKBOOK_PATH for local backend"
    ),
    verbose: bool = typer.Option(True, "--verbose/--quiet", help="Show step-by-step progress logs"),
) -> None:
    try:
        def log(message: str) -> None:
            if verbose:
                typer.echo(message)

        log("Loading configuration...")
        settings = load_settings()
        log("Building source adapters...")
        adapters = _build_adapters(settings)
        log(f"Using sources: {', '.join(adapter.source_name for adapter in adapters)}")

        log("Validating required source authentication...")
        _validate_required_auth(adapters)
        log("Authentication complete.")

        log(f"Connecting to {io_backend} sheet backend...")
        sheets = build_sheet_backend(
            settings,
            io_backend=io_backend,
            sheet_id_override=sheet_id,
            local_workbook_override=local_workbook,
        )

        log("Reading input rows from 'Input' worksheet...")
        players = sheets.read_input()
        if not players:
            typer.echo("No valid input rows found in Input sheet.")
            return
        log(f"Loaded {len(players)} player row(s).")

        output_rows = []
        for idx, player in enumerate(players, start=1):
            log(f"[{idx}/{len(players)}] Processing {player.first_name} {player.last_name}...")
            row = process_player(query=player, adapters=adapters)
            output_rows.append(row)
            log(f"[{idx}/{len(players)}] Status={row.status}")

        log("Writing results to 'Output' worksheet...")
        sheets.write_output(output_rows)
        log("Output write complete.")

        counts = Counter(row.status for row in output_rows)
        typer.echo(
            "Run complete. "
            f"ok={counts.get('ok', 0)} "
            f"ambiguous={counts.get('ambiguous', 0)} "
            f"not_found={counts.get('not_found', 0)} "
            f"error={counts.get('error', 0)}"
        )
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Run failed [{exc.__class__.__name__}]: {exc}", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
