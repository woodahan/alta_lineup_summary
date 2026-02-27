from __future__ import annotations

from .base import SourceAdapter


class UstaAdapter(SourceAdapter):
    source_name = "usta"
    required_auth = False

    def is_required(self) -> bool:
        return False
