from __future__ import annotations

from collections import Counter

import typer

from .aggregate import process_player
from .config import Settings, load_settings
from .sheets import SheetsClient
from .sources import T2Adapter, UltimateAdapter, UstaAdapter
from .sources.base import SourceAdapter

app = typer.Typer(help="ALTA ratings aggregation CLI")


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
        ok, message = adapter.authenticate()
        if not ok:
            raise RuntimeError(f"{adapter.source_name} auth failed: {message}")


@app.command()
def run(sheet_id: str | None = typer.Option(None, help="Override GOOGLE_SHEET_ID from env")) -> None:
    settings = load_settings()
    if sheet_id:
        settings = Settings(
            google_service_account_json=settings.google_service_account_json,
            google_sheet_id=sheet_id,
            ultimate=settings.ultimate,
            t2=settings.t2,
            usta=settings.usta,
            cache_dir=settings.cache_dir,
        )

    adapters = _build_adapters(settings)
    _validate_required_auth(adapters)

    sheets = SheetsClient(
        service_account_json=settings.google_service_account_json,
        sheet_id=settings.google_sheet_id,
    )

    players = sheets.read_input()
    if not players:
        typer.echo("No valid input rows found in Input sheet.")
        return

    output_rows = [process_player(query=player, adapters=adapters) for player in players]
    sheets.write_output(output_rows)

    counts = Counter(row.status for row in output_rows)
    typer.echo(
        "Run complete. "
        f"ok={counts.get('ok', 0)} "
        f"ambiguous={counts.get('ambiguous', 0)} "
        f"not_found={counts.get('not_found', 0)} "
        f"error={counts.get('error', 0)}"
    )


if __name__ == "__main__":
    app()
