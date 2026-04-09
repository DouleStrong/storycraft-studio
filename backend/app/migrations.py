from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from .config import Settings


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def make_alembic_config(settings: Settings) -> Config:
    backend_root = _backend_root()
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("prepend_sys_path", str(backend_root))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def run_migrations(settings: Settings) -> None:
    command.upgrade(make_alembic_config(settings), "head")
