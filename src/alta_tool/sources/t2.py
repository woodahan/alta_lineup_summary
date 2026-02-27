from __future__ import annotations

from .base import SourceAdapter


class T2Adapter(SourceAdapter):
    source_name = "t2"
    required_auth = True

    def is_required(self) -> bool:
        return True
