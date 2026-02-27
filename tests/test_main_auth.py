import pytest

from alta_tool.main import _validate_required_auth


class FakeAdapter:
    def __init__(self, source_name: str, required_auth: bool, ok: bool):
        self.source_name = source_name
        self.required_auth = required_auth
        self._ok = ok
        self.loaded = False

    def load_cached_cookies(self):
        self.loaded = True

    def authenticate(self):
        return self._ok, "bad creds" if not self._ok else "ok"


def test_validate_required_auth_fails_fast() -> None:
    adapters = [FakeAdapter("t2", True, False)]
    with pytest.raises(RuntimeError):
        _validate_required_auth(adapters)  # type: ignore[arg-type]


def test_validate_required_auth_skips_optional_auth() -> None:
    adapters = [FakeAdapter("usta", False, False)]
    _validate_required_auth(adapters)  # type: ignore[arg-type]
    assert adapters[0].loaded is True
