from pathlib import Path

from types import SimpleNamespace

from app.config import load_settings, review_intervention_min_severity


def test_load_settings_defaults_to_postgres_when_db_url_is_not_configured(monkeypatch):
    monkeypatch.setenv("STORY_PLATFORM_SKIP_DOTENV", "1")
    monkeypatch.delenv("STORY_PLATFORM_ENV_FILE", raising=False)
    monkeypatch.delenv("STORY_PLATFORM_DB_URL", raising=False)
    monkeypatch.delenv("STORY_PLATFORM_STORAGE_DIR", raising=False)
    monkeypatch.delenv("STORY_PLATFORM_EXPORT_DIR", raising=False)

    settings = load_settings()

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_load_settings_reads_values_from_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_BASE_URL=https://example.test/v1",
                "OPENAI_API_KEY=test-key",
                "OPENAI_MODEL=test-model",
                "STORY_AGENT_TIMEOUT_SECONDS=99",
                "STORY_PLATFORM_DB_URL=sqlite:///./custom.db",
                "STORY_PLATFORM_STORAGE_DIR=./custom-storage",
                "STORY_PLATFORM_EXPORT_DIR=./custom-exports",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("STORY_PLATFORM_ENV_FILE", str(env_file))
    monkeypatch.delenv("STORY_PLATFORM_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("STORY_AGENT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("STORY_PLATFORM_DB_URL", raising=False)
    monkeypatch.delenv("STORY_PLATFORM_STORAGE_DIR", raising=False)
    monkeypatch.delenv("STORY_PLATFORM_EXPORT_DIR", raising=False)

    settings = load_settings()

    assert settings.openai_base_url == "https://example.test/v1"
    assert settings.openai_api_key == "test-key"
    assert settings.openai_model == "test-model"
    assert settings.story_agent_timeout_seconds == 99
    assert settings.database_url == f"sqlite:///{(tmp_path / 'custom.db').resolve()}"
    assert settings.storage_dir == (tmp_path / "custom-storage").resolve()
    assert settings.export_dir == (tmp_path / "custom-exports").resolve()


def test_load_settings_can_override_ambient_env_when_env_file_requests_it(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "STORY_PLATFORM_DOTENV_OVERRIDE=1",
                "OPENAI_BASE_URL=https://example.test/v1",
                "OPENAI_API_KEY=file-key",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("STORY_PLATFORM_ENV_FILE", str(env_file))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://ambient.example/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")
    monkeypatch.delenv("STORY_PLATFORM_SKIP_DOTENV", raising=False)

    settings = load_settings()

    assert settings.openai_base_url == "https://example.test/v1"
    assert settings.openai_api_key == "file-key"


def test_load_settings_resolves_relative_paths_consistently_when_cwd_changes(tmp_path, monkeypatch):
    env_dir = tmp_path / "project-root"
    env_dir.mkdir(parents=True)
    env_file = env_dir / ".env"
    env_file.write_text(
        "\n".join(
            [
                "STORY_PLATFORM_DB_URL=sqlite:///./storycraft_studio.db",
                "STORY_PLATFORM_STORAGE_DIR=./runtime/storage",
                "STORY_PLATFORM_EXPORT_DIR=./runtime/exports",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STORY_PLATFORM_ENV_FILE", str(env_file))
    monkeypatch.delenv("STORY_PLATFORM_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("STORY_PLATFORM_DB_URL", raising=False)
    monkeypatch.delenv("STORY_PLATFORM_STORAGE_DIR", raising=False)
    monkeypatch.delenv("STORY_PLATFORM_EXPORT_DIR", raising=False)

    settings = load_settings()

    assert settings.database_url == f"sqlite:///{(env_dir / 'storycraft_studio.db').resolve()}"
    assert settings.storage_dir == (env_dir / "runtime" / "storage").resolve()
    assert settings.export_dir == (env_dir / "runtime" / "exports").resolve()


def test_review_intervention_min_severity_falls_back_for_legacy_settings_objects():
    legacy_settings = SimpleNamespace()

    assert review_intervention_min_severity(legacy_settings) == "critical"
