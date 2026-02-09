from src.config import Settings


def test_settings_loads_with_env_vars(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    settings = Settings(_env_file=None)

    assert settings.supabase_url == "https://example.supabase.co"
    assert settings.supabase_anon_key == "anon-key"
    assert settings.supabase_service_key == "service-key"
    assert settings.openai_model == "gpt-test"
