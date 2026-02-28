from __future__ import annotations

from typing import Iterable, Protocol

from ..models import OutputRow, PlayerQuery


class SheetBackend(Protocol):
    def read_input(self) -> list[PlayerQuery]:
        ...

    def write_output(self, rows: Iterable[OutputRow]) -> None:
        ...
