from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.legacy_import import import_legacy_sqlite_sources
from app.models import Chapter, Character, CharacterReferenceImage, NarrativeBlock, Project, StoryBible, User


def _make_session_factory(database_path: Path):
    engine = create_engine(f"sqlite:///{database_path}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _seed_source_database(database_path: Path, *, title: str, image_name: str):
    runtime_dir = database_path.parent / "runtime"
    storage_dir = runtime_dir / "storage" / "reference-images"
    export_dir = runtime_dir / "exports"
    storage_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    image_path = storage_dir / image_name
    image_path.write_bytes(b"legacy-image")

    session_factory = _make_session_factory(database_path)
    with session_factory() as db:
        user = User(
            email="legacy@example.com",
            password_hash="hashed",
            pen_name="Legacy Author",
            access_token=None,
        )
        db.add(user)
        db.flush()

        project = Project(
            owner=user,
            title=title,
            genre="都市悬疑",
            tone="克制、电影感",
            era="当代",
            target_chapter_count=3,
            target_length="3章，短剧节奏",
            logline=f"{title} 的旧数据需要被迁移。",
            status="outlined",
        )
        db.add(project)
        db.flush()

        db.add(
            StoryBible(
                project=project,
                world_notes=f"{title} 的世界设定",
                style_notes="角色驱动，场景清晰",
                writing_rules=["角色选择推动冲突"],
            )
        )

        character = Character(
            project=project,
            name="林听",
            role="调查记者",
            personality="敏锐、压着情绪说话",
            goal="查清真相",
            speech_style="短句、追问锋利",
            appearance="深色外套，眼下疲惫",
            relationships="与旧搭档关系复杂",
            signature_line="她每次沉默都像在计算下一步。",
        )
        db.add(character)
        db.flush()
        db.add(
            CharacterReferenceImage(
                character=character,
                filename=image_name,
                path=str(image_path),
            )
        )

        chapter = Chapter(
            project=project,
            order_index=1,
            title="第一章·回声",
            summary="旧站台再次响起广播。",
            chapter_goal="让主角重新卷入事件核心。",
            hook="广播里出现了不该存在的名字。",
            status="drafted",
            continuity_notes=["Reviewer：保持人物压抑的说话节奏。"],
        )
        db.add(chapter)
        db.flush()
        db.add(NarrativeBlock(chapter=chapter, order_index=1, content=f"{title} 的旧章节正文。"))
        db.commit()

    return runtime_dir


def test_import_legacy_sqlite_sources_merges_sources_and_rewrites_storage_paths(tmp_path):
    source_a = tmp_path / "legacy-root" / "storycraft_studio.db"
    source_b = tmp_path / "backend" / "storycraft_studio.db"
    target_db = tmp_path / "postgres-replacement.db"
    target_storage = tmp_path / "runtime" / "storage"
    target_exports = tmp_path / "runtime" / "exports"

    _seed_source_database(source_a, title="旧库 A", image_name="a.png")
    _seed_source_database(source_b, title="旧库 B", image_name="b.png")

    report = import_legacy_sqlite_sources(
        source_database_urls=[
            f"sqlite:///{source_a}",
            f"sqlite:///{source_b}",
        ],
        target_database_url=f"sqlite:///{target_db}",
        target_storage_dir=target_storage,
        target_export_dir=target_exports,
    )

    assert report["source_count"] == 2
    assert report["users_merged"] == 1
    assert report["projects_imported"] == 2
    assert report["files_copied"] >= 2

    session_factory = _make_session_factory(target_db)
    with session_factory() as db:
        users = db.query(User).all()
        projects = db.query(Project).order_by(Project.title.asc()).all()
        reference_images = db.query(CharacterReferenceImage).order_by(CharacterReferenceImage.filename.asc()).all()

        assert len(users) == 1
        assert [project.title for project in projects] == ["旧库 A", "旧库 B"]
        assert len(reference_images) == 2

        for reference_image in reference_images:
            migrated_path = Path(reference_image.path)
            assert migrated_path.exists()
            assert migrated_path.is_relative_to(target_storage)
