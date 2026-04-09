from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from app.config import load_settings


def test_alembic_cli_config_works_from_repo_root(tmp_path, monkeypatch):
    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parent
    db_path = tmp_path / "alembic_cli.db"

    monkeypatch.chdir(repo_root)

    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(config, "head")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    assert "projects" in inspector.get_table_names()


def test_upgrade_0004_backfills_story_bible_revisions_on_postgres():
    settings = load_settings()
    if not settings.database_url.startswith("postgresql"):
        return

    backend_root = Path(__file__).resolve().parents[1]
    source_url = make_url(settings.database_url)
    temp_db_name = f"storycraft_migration_{uuid.uuid4().hex[:8]}"
    admin_url = source_url.set(database="postgres")
    temp_db_url = source_url.set(database=temp_db_name)

    admin_engine = sa.create_engine(admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT")
    temp_engine = None
    try:
        with admin_engine.connect() as connection:
            connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{temp_db_name}" WITH (FORCE)'))
            connection.execute(sa.text(f'CREATE DATABASE "{temp_db_name}"'))

        config = Config(str(backend_root / "alembic.ini"))
        config.set_main_option("script_location", str(backend_root / "alembic"))
        config.set_main_option("prepend_sys_path", str(backend_root))
        config.set_main_option("sqlalchemy.url", temp_db_url.render_as_string(hide_password=False))

        command.upgrade(config, "0003_character_library_links")

        temp_engine = sa.create_engine(temp_db_url.render_as_string(hide_password=False))
        metadata = sa.MetaData()
        metadata.reflect(
            bind=temp_engine,
            only=("users", "projects", "story_bibles", "chapters"),
        )
        users = metadata.tables["users"]
        projects = metadata.tables["projects"]
        story_bibles = metadata.tables["story_bibles"]
        chapters = metadata.tables["chapters"]
        now = datetime.now(UTC)

        with temp_engine.begin() as connection:
            user_id = connection.execute(
                users.insert()
                .returning(users.c.id)
                .values(
                    email="migration@example.com",
                    password_hash="hashed",
                    pen_name="迁移作者",
                    access_token="migration-token",
                    created_at=now,
                    updated_at=now,
                )
            ).scalar_one()
            project_id = connection.execute(
                projects.insert()
                .returning(projects.c.id)
                .values(
                    owner_id=user_id,
                    title="迁移回归项目",
                    genre="都市悬疑",
                    tone="克制、潮湿、人物驱动",
                    era="当代",
                    target_chapter_count=6,
                    target_length="6章",
                    logline="用于验证 0004 迁移在 PostgreSQL 下的回填逻辑。",
                    status="draft",
                    created_at=now,
                    updated_at=now,
                )
            ).scalar_one()
            connection.execute(
                story_bibles.insert().values(
                    project_id=project_id,
                    world_notes="旧港被长年封存的录音资料重新浮出水面。",
                    style_notes="动作先于解释。",
                    writing_rules=["称呼稳定", "悬念必须落到人物选择"],
                    addressing_rules="主角始终直呼搭档姓名。",
                    timeline_rules="故事必须在三天内推进完。",
                    created_at=now,
                    updated_at=now,
                )
            )
            connection.execute(
                chapters.insert().values(
                    project_id=project_id,
                    order_index=1,
                    title="第一章·回潮",
                    summary="主角第一次听到被删节的录音片段。",
                    chapter_goal="让主角意识到旧案并未真正结束。",
                    hook="录音里出现了本不该活着的人名。",
                    status="planned",
                    is_locked=False,
                    continuity_notes=[],
                    created_at=now,
                    updated_at=now,
                )
            )

        command.upgrade(config, "head")

        verification_metadata = sa.MetaData()
        verification_metadata.reflect(bind=temp_engine, only=("story_bible_revisions", "chapters"))
        story_bible_revisions = verification_metadata.tables["story_bible_revisions"]
        upgraded_chapters = verification_metadata.tables["chapters"]
        with temp_engine.connect() as connection:
            revision_count = connection.execute(sa.select(sa.func.count()).select_from(story_bible_revisions)).scalar_one()
            chapter_revision_id = connection.execute(
                sa.select(upgraded_chapters.c.source_story_bible_revision_id).limit(1)
            ).scalar_one()
        assert revision_count == 1
        assert chapter_revision_id is not None
    finally:
        if temp_engine is not None:
            temp_engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{temp_db_name}" WITH (FORCE)'))
        admin_engine.dispose()
