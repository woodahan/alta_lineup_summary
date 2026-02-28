import pytest

from alta_tool.config import load_settings


@pytest.fixture(autouse=True)
def disable_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep tests deterministic by preventing load_settings() from loading .env.
    monkeypatch.setattr("alta_tool.config.load_dotenv", lambda: None)


@pytest.mark.parametrize(
    "missing_key",
    [
        "T2_USERNAME",
        "T2_PASSWORD",
        "T2_LOGIN_URL",
        "T2_SEARCH_URL",
        "ULTIMATE_USERNAME",
        "ULTIMATE_PASSWORD",
        "ULTIMATE_LOGIN_URL",
        "ULTIMATE_SEARCH_URL",
    ],
)
def test_load_settings_requires_expected_env_vars(monkeypatch: pytest.MonkeyPatch, missing_key: str) -> None:
    baseline = {
        "T2_USERNAME": "u",
        "T2_PASSWORD": "p",
        "T2_LOGIN_URL": "https://t/login",
        "T2_SEARCH_URL": "https://t/search",
        "ULTIMATE_USERNAME": "u",
        "ULTIMATE_PASSWORD": "p",
        "ULTIMATE_LOGIN_URL": "https://u/login",
        "ULTIMATE_SEARCH_URL": "https://u/search",
    }

    for key, value in baseline.items():
        monkeypatch.setenv(key, value)

    monkeypatch.delenv(missing_key, raising=False)

    with pytest.raises(ValueError):
        load_settings()


def test_load_settings_allows_missing_google_env(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = {
        "T2_USERNAME": "u",
        "T2_PASSWORD": "p",
        "T2_LOGIN_URL": "https://t/login",
        "T2_SEARCH_URL": "https://t/search",
        "ULTIMATE_USERNAME": "u",
        "ULTIMATE_PASSWORD": "p",
        "ULTIMATE_LOGIN_URL": "https://u/login",
        "ULTIMATE_SEARCH_URL": "https://u/search",
    }
    for key, value in baseline.items():
        monkeypatch.setenv(key, value)

    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)

    settings = load_settings()
    assert settings.google_service_account_json == ""
    assert settings.google_sheet_id == ""
