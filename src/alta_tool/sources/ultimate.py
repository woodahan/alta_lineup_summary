from __future__ import annotations

from .base import SourceAdapter


class UltimateAdapter(SourceAdapter):
    source_name = "ultimate"
    required_auth = True

    def is_required(self) -> bool:
        return True
