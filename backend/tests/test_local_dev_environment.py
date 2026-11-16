import importlib
import secrets


def test_settings_loads_local_dotenv_defaults(monkeypatch, tmp_path):
    test_secret = secrets.token_urlsafe(32)
    env_file = tmp_path / ".env"
    env_file.write_text(
        'ENVIRONMENT="development"\n'
        'DATABASE_URL="sqlite:////tmp/local_obe_dev.sqlite"\n'
        f'JWT_SECRET_KEY="{test_secret}"\n'
        'CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    for key in ("ENVIRONMENT", "DATABASE_URL", "JWT_SECRET_KEY", "CORS_ORIGINS"):
        monkeypatch.delenv(key, raising=False)

    import app.config as config_module
    importlib.reload(config_module)

    settings = config_module.Settings()
    assert settings.ENVIRONMENT == "development"
    assert settings.DATABASE_URL == "sqlite:////tmp/local_obe_dev.sqlite"
    assert settings.JWT_SECRET_KEY == test_secret
    assert settings.CORS_ORIGINS == ["http://localhost:3000", "http://127.0.0.1:3000"]
