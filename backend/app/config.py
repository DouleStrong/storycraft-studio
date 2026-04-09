from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    app_name: str
    database_url: str
    allow_sqlite: bool
    storage_dir: Path
    export_dir: Path
    redis_url: str
    story_queue_name: str
    openai_base_url: str | None
    openai_api_key: str | None
    openai_model: str
    story_agent_planner_model: str | None
    story_agent_writer_model: str | None
    story_agent_reviewer_model: str | None
    story_agent_visual_model: str | None
    story_agent_image_model: str | None
    story_agent_image_size: str
    story_agent_timeout_seconds: int
    story_review_intervention_min_severity: str


def review_intervention_min_severity(settings: object) -> str:
    return str(getattr(settings, "story_review_intervention_min_severity", "critical")).strip().lower() or "critical"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_env_file() -> Path:
    configured_path = os.getenv("STORY_PLATFORM_ENV_FILE")
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return _project_root() / ".env"


def _settings_base_dir() -> Path:
    return _resolve_env_file().parent


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()

    if "=" not in stripped:
        return None

    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None

    if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
        value = value[1:-1]

    return key, value


def _is_truthy(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "yes", "on"}


def _resolve_path_setting(raw_value: str, *, base_dir: Path) -> Path:
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _resolve_database_url(raw_value: str, *, base_dir: Path) -> str:
    if not raw_value.startswith("sqlite:///"):
        return raw_value

    sqlite_path = raw_value.removeprefix("sqlite:///")
    if sqlite_path == ":memory:":
        return raw_value

    resolved = _resolve_path_setting(sqlite_path, base_dir=base_dir)
    return f"sqlite:///{resolved}"


def load_env_file(*, override: bool = False) -> None:
    if _is_truthy(os.getenv("STORY_PLATFORM_SKIP_DOTENV")):
        return

    env_file = _resolve_env_file()
    if not env_file.exists():
        return

    parsed_values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(raw_line)
        if not parsed:
            continue
        key, value = parsed
        parsed_values[key] = value

    should_override = override or _is_truthy(os.getenv("STORY_PLATFORM_DOTENV_OVERRIDE")) or _is_truthy(
        parsed_values.get("STORY_PLATFORM_DOTENV_OVERRIDE")
    )
    for key, value in parsed_values.items():
        if should_override or key not in os.environ:
            os.environ[key] = value


def load_settings() -> Settings:
    load_env_file()
    settings_base_dir = _settings_base_dir()
    base_storage = _resolve_path_setting(
        os.getenv("STORY_PLATFORM_STORAGE_DIR", "./runtime/storage"),
        base_dir=settings_base_dir,
    )
    export_dir = _resolve_path_setting(
        os.getenv("STORY_PLATFORM_EXPORT_DIR", "./runtime/exports"),
        base_dir=settings_base_dir,
    )
    default_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    return Settings(
        app_name="StoryCraft Studio",
        database_url=_resolve_database_url(
            os.getenv(
                "STORY_PLATFORM_DB_URL",
                "postgresql+psycopg://storycraft:storycraft@127.0.0.1:5432/storycraft",
            ),
            base_dir=settings_base_dir,
        ),
        allow_sqlite=_is_truthy(os.getenv("STORY_PLATFORM_ALLOW_SQLITE")),
        storage_dir=base_storage,
        export_dir=export_dir,
        redis_url=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
        story_queue_name=os.getenv("STORY_QUEUE_NAME", "storycraft"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=default_model,
        story_agent_planner_model=os.getenv("STORY_AGENT_PLANNER_MODEL"),
        story_agent_writer_model=os.getenv("STORY_AGENT_WRITER_MODEL"),
        story_agent_reviewer_model=os.getenv("STORY_AGENT_REVIEWER_MODEL"),
        story_agent_visual_model=os.getenv("STORY_AGENT_VISUAL_MODEL"),
        story_agent_image_model=os.getenv("STORY_AGENT_IMAGE_MODEL") or os.getenv("OPENAI_IMAGE_MODEL"),
        story_agent_image_size=os.getenv("STORY_AGENT_IMAGE_SIZE", "1536x1024").strip(),
        story_agent_timeout_seconds=int(os.getenv("STORY_AGENT_TIMEOUT_SECONDS", "45")),
        story_review_intervention_min_severity=os.getenv(
            "STORY_REVIEW_INTERVENTION_MIN_SEVERITY",
            "critical",
        ).strip().lower(),
    )
