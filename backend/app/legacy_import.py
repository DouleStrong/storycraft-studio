from __future__ import annotations

import argparse
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine
from sqlalchemy.orm import selectinload, sessionmaker

from .config import load_settings
from .database import Base
from .models import (
    Chapter,
    Character,
    CharacterReferenceImage,
    CharacterVisualProfile,
    DialogueBlock,
    ExportPackage,
    IllustrationAsset,
    NarrativeBlock,
    Project,
    Scene,
    StoryBible,
    User,
)


@dataclass(slots=True)
class LegacyImportReport:
    source_count: int = 0
    users_merged: int = 0
    projects_imported: int = 0
    characters_imported: int = 0
    chapters_imported: int = 0
    scenes_imported: int = 0
    illustrations_imported: int = 0
    exports_imported: int = 0
    files_copied: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class LegacyAssetRemapper:
    def __init__(
        self,
        *,
        source_storage_dir: Path,
        source_export_dir: Path,
        target_storage_dir: Path,
        target_export_dir: Path,
    ):
        self.source_storage_dir = source_storage_dir.resolve()
        self.source_export_dir = source_export_dir.resolve()
        self.target_storage_dir = target_storage_dir.resolve()
        self.target_export_dir = target_export_dir.resolve()
        self.files_copied = 0

    def remap_storage_path(self, raw_path: str | None) -> str | None:
        return self._remap_path(raw_path, source_root=self.source_storage_dir, target_root=self.target_storage_dir)

    def remap_export_path(self, raw_path: str | None) -> str | None:
        return self._remap_path(raw_path, source_root=self.source_export_dir, target_root=self.target_export_dir)

    def remap_export_files(self, files: list[dict] | None) -> list[dict]:
        results = []
        for item in files or []:
            path = self.remap_export_path(item.get("path"))
            results.append({**item, "path": path} if path else dict(item))
        return results

    def _remap_path(self, raw_path: str | None, *, source_root: Path, target_root: Path) -> str | None:
        if not raw_path:
            return raw_path

        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = source_root.parent / candidate
        candidate = candidate.resolve()

        try:
            relative_path = candidate.relative_to(source_root)
        except ValueError:
            return str(candidate)

        target_path = (target_root / relative_path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if candidate.exists() and not target_path.exists():
            shutil.copy2(candidate, target_path)
            self.files_copied += 1
        return str(target_path)


def detect_legacy_sqlite_database_urls(project_root: Path | None = None) -> list[str]:
    root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    candidates = [
        root / "storycraft_studio.db",
        root / "backend" / "storycraft_studio.db",
    ]
    return [f"sqlite:///{candidate}" for candidate in candidates if candidate.exists()]


def import_legacy_sqlite_sources(
    *,
    source_database_urls: list[str],
    target_database_url: str,
    target_storage_dir: Path,
    target_export_dir: Path,
) -> dict[str, int]:
    target_engine = create_engine(target_database_url, future=True)
    Base.metadata.create_all(target_engine)
    target_session_factory = sessionmaker(
        bind=target_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    report = LegacyImportReport(source_count=len(source_database_urls))
    with target_session_factory() as target_db:
        for source_database_url in source_database_urls:
            _import_single_source(
                source_database_url=source_database_url,
                target_db=target_db,
                target_storage_dir=target_storage_dir,
                target_export_dir=target_export_dir,
                report=report,
            )
        target_db.commit()

    return report.to_dict()


def _import_single_source(
    *,
    source_database_url: str,
    target_db,
    target_storage_dir: Path,
    target_export_dir: Path,
    report: LegacyImportReport,
) -> None:
    source_engine = create_engine(source_database_url, future=True)
    source_session_factory = sessionmaker(
        bind=source_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    source_db_path = _sqlite_database_path(source_database_url)
    source_storage_dir = source_db_path.parent / "runtime" / "storage"
    source_export_dir = source_db_path.parent / "runtime" / "exports"
    remapper = LegacyAssetRemapper(
        source_storage_dir=source_storage_dir,
        source_export_dir=source_export_dir,
        target_storage_dir=target_storage_dir,
        target_export_dir=target_export_dir,
    )

    with source_session_factory() as source_db:
        projects = (
            source_db.query(Project)
            .options(selectinload(Project.story_bible))
            .options(selectinload(Project.owned_characters).selectinload(Character.reference_images))
            .options(selectinload(Project.owned_characters).selectinload(Character.visual_profile))
            .options(selectinload(Project.chapters).selectinload(Chapter.narrative_blocks))
            .options(selectinload(Project.chapters).selectinload(Chapter.scenes).selectinload(Scene.dialogue_blocks))
            .options(selectinload(Project.chapters).selectinload(Chapter.scenes).selectinload(Scene.illustrations))
            .options(selectinload(Project.exports))
            .all()
        )

        user_map: dict[int, User] = {}
        project_map: dict[int, Project] = {}
        chapter_map: dict[int, Chapter] = {}
        scene_map: dict[int, Scene] = {}

        for source_project in projects:
            source_user = source_project.owner
            target_user = _merge_user(target_db, source_user, report)
            user_map[source_user.id] = target_user

            target_project = _merge_project(target_db, source_project, target_user, remapper, report)
            project_map[source_project.id] = target_project

            _merge_story_bible(target_project, source_project.story_bible)
            character_map = _merge_characters(target_db, target_project, source_project, remapper, report)
            chapter_map.update(_merge_chapters(target_db, target_project, source_project, report))

            for source_chapter in source_project.chapters:
                target_chapter = chapter_map[source_chapter.id]
                scene_map.update(_merge_scenes(target_db, target_chapter, source_chapter, remapper, report))

            _merge_exports(target_db, target_project, source_project.exports, remapper, report)
            target_db.flush()

    report.files_copied += remapper.files_copied


def _sqlite_database_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("Only sqlite legacy sources are supported.")
    return Path(database_url.removeprefix("sqlite:///")).expanduser().resolve()


def _merge_user(target_db, source_user: User, report: LegacyImportReport) -> User:
    existing = target_db.query(User).filter(User.email == source_user.email).first()
    if existing:
        return existing

    user = User(
        email=source_user.email,
        password_hash=source_user.password_hash,
        pen_name=source_user.pen_name,
        access_token=source_user.access_token,
    )
    target_db.add(user)
    target_db.flush()
    report.users_merged += 1
    return user


def _project_key(owner_id: int, source_project: Project) -> tuple:
    return (
        owner_id,
        source_project.title,
        source_project.genre,
        source_project.era,
        source_project.target_length,
        source_project.logline,
    )


def _merge_project(target_db, source_project: Project, target_user: User, remapper: LegacyAssetRemapper, report: LegacyImportReport) -> Project:
    existing_projects = target_db.query(Project).filter(Project.owner_id == target_user.id).all()
    source_key = _project_key(target_user.id, source_project)
    for existing in existing_projects:
        if _project_key(target_user.id, existing) == source_key:
            if not existing.cover_image_path:
                existing.cover_image_path = remapper.remap_storage_path(source_project.cover_image_path)
            return existing

    project = Project(
        owner=target_user,
        title=source_project.title,
        genre=source_project.genre,
        tone=source_project.tone,
        era=source_project.era,
        target_chapter_count=source_project.target_chapter_count,
        target_length=source_project.target_length,
        logline=source_project.logline,
        status=source_project.status,
        cover_image_path=remapper.remap_storage_path(source_project.cover_image_path),
    )
    target_db.add(project)
    target_db.flush()
    report.projects_imported += 1
    return project


def _merge_story_bible(target_project: Project, source_story_bible: StoryBible | None) -> None:
    if not source_story_bible:
        return
    if not target_project.story_bible:
        target_project.story_bible = StoryBible(
            world_notes=source_story_bible.world_notes,
            style_notes=source_story_bible.style_notes,
            writing_rules=list(source_story_bible.writing_rules or []),
        )
        return

    if not target_project.story_bible.world_notes:
        target_project.story_bible.world_notes = source_story_bible.world_notes
    if not target_project.story_bible.style_notes:
        target_project.story_bible.style_notes = source_story_bible.style_notes
    merged_rules = list(dict.fromkeys([*(target_project.story_bible.writing_rules or []), *(source_story_bible.writing_rules or [])]))
    target_project.story_bible.writing_rules = merged_rules


def _merge_characters(target_db, target_project: Project, source_project: Project, remapper: LegacyAssetRemapper, report: LegacyImportReport) -> dict[int, Character]:
    target_lookup = {(character.name, character.role): character for character in target_project.characters}
    character_map: dict[int, Character] = {}

    for source_character in source_project.owned_characters:
        target_character = target_lookup.get((source_character.name, source_character.role))
        if not target_character:
            target_character = Character(
                owner=target_project.owner,
                project=target_project,
                name=source_character.name,
                role=source_character.role,
                personality=source_character.personality,
                goal=source_character.goal,
                speech_style=source_character.speech_style,
                appearance=source_character.appearance,
                relationships=source_character.relationships,
                signature_line=source_character.signature_line,
            )
            target_db.add(target_character)
            target_db.flush()
            target_lookup[(source_character.name, source_character.role)] = target_character
            report.characters_imported += 1

        existing_paths = {item.path for item in target_character.reference_images}
        for reference_image in source_character.reference_images:
            remapped_path = remapper.remap_storage_path(reference_image.path)
            if remapped_path in existing_paths:
                continue
            target_db.add(
                CharacterReferenceImage(
                    character=target_character,
                    filename=reference_image.filename,
                    path=remapped_path,
                )
            )
            existing_paths.add(remapped_path)

        if source_character.visual_profile and not target_character.visual_profile:
            target_db.add(
                CharacterVisualProfile(
                    character=target_character,
                    visual_anchor=source_character.visual_profile.visual_anchor,
                    signature_palette=source_character.visual_profile.signature_palette,
                    silhouette_notes=source_character.visual_profile.silhouette_notes,
                    wardrobe_notes=source_character.visual_profile.wardrobe_notes,
                    atmosphere_notes=source_character.visual_profile.atmosphere_notes,
                )
            )

        character_map[source_character.id] = target_character

    return character_map


def _merge_chapters(target_db, target_project: Project, source_project: Project, report: LegacyImportReport) -> dict[int, Chapter]:
    target_lookup = {chapter.order_index: chapter for chapter in target_project.chapters}
    chapter_map: dict[int, Chapter] = {}

    for source_chapter in source_project.chapters:
        target_chapter = target_lookup.get(source_chapter.order_index)
        if not target_chapter:
            target_chapter = Chapter(
                project=target_project,
                order_index=source_chapter.order_index,
                title=source_chapter.title,
                summary=source_chapter.summary,
                chapter_goal=source_chapter.chapter_goal,
                hook=source_chapter.hook,
                status=source_chapter.status,
                is_locked=source_chapter.is_locked,
                continuity_notes=list(source_chapter.continuity_notes or []),
            )
            target_db.add(target_chapter)
            target_db.flush()
            target_lookup[source_chapter.order_index] = target_chapter
            report.chapters_imported += 1

        existing_blocks = {(block.order_index, block.content) for block in target_chapter.narrative_blocks}
        for block in source_chapter.narrative_blocks:
            key = (block.order_index, block.content)
            if key in existing_blocks:
                continue
            target_db.add(
                NarrativeBlock(
                    chapter=target_chapter,
                    order_index=block.order_index,
                    content=block.content,
                )
            )
            existing_blocks.add(key)

        chapter_map[source_chapter.id] = target_chapter

    return chapter_map


def _merge_scenes(target_db, target_chapter: Chapter, source_chapter: Chapter, remapper: LegacyAssetRemapper, report: LegacyImportReport) -> dict[int, Scene]:
    target_lookup = {(scene.order_index, scene.title): scene for scene in target_chapter.scenes}
    scene_map: dict[int, Scene] = {}

    for source_scene in source_chapter.scenes:
        key = (source_scene.order_index, source_scene.title)
        target_scene = target_lookup.get(key)
        if not target_scene:
            target_scene = Scene(
                chapter=target_chapter,
                order_index=source_scene.order_index,
                title=source_scene.title,
                scene_type=source_scene.scene_type,
                location=source_scene.location,
                time_of_day=source_scene.time_of_day,
                cast_names=list(source_scene.cast_names or []),
                objective=source_scene.objective,
                emotional_tone=source_scene.emotional_tone,
                visual_prompt=source_scene.visual_prompt,
            )
            target_db.add(target_scene)
            target_db.flush()
            target_lookup[key] = target_scene
            report.scenes_imported += 1

        existing_dialogues = {
            (dialogue.order_index, dialogue.speaker, dialogue.content) for dialogue in target_scene.dialogue_blocks
        }
        for dialogue in source_scene.dialogue_blocks:
            dialogue_key = (dialogue.order_index, dialogue.speaker, dialogue.content)
            if dialogue_key in existing_dialogues:
                continue
            target_db.add(
                DialogueBlock(
                    scene=target_scene,
                    order_index=dialogue.order_index,
                    speaker=dialogue.speaker,
                    parenthetical=dialogue.parenthetical,
                    content=dialogue.content,
                )
            )
            existing_dialogues.add(dialogue_key)

        existing_illustrations = {
            (asset.candidate_index, asset.prompt_text, asset.file_path) for asset in target_scene.illustrations
        }
        for illustration in source_scene.illustrations:
            remapped_file = remapper.remap_storage_path(illustration.file_path)
            illustration_key = (illustration.candidate_index, illustration.prompt_text, remapped_file)
            if illustration_key in existing_illustrations:
                continue
            target_db.add(
                IllustrationAsset(
                    project=target_chapter.project,
                    scene=target_scene,
                    character_id=None,
                    prompt_text=illustration.prompt_text,
                    file_path=remapped_file,
                    thumbnail_path=remapper.remap_storage_path(illustration.thumbnail_path),
                    status=illustration.status,
                    candidate_index=illustration.candidate_index,
                    is_canonical=illustration.is_canonical,
                )
            )
            existing_illustrations.add(illustration_key)
            report.illustrations_imported += 1

        scene_map[source_scene.id] = target_scene

    return scene_map


def _merge_exports(target_db, target_project: Project, source_exports: Iterable[ExportPackage], remapper: LegacyAssetRemapper, report: LegacyImportReport) -> None:
    existing_keys = {
        (export_package.created_at, tuple(export_package.formats or []), tuple(file_info.get("path") for file_info in export_package.files))
        for export_package in target_project.exports
    }

    for source_export in source_exports:
        remapped_files = remapper.remap_export_files(source_export.files)
        export_key = (
            source_export.created_at,
            tuple(source_export.formats or []),
            tuple(file_info.get("path") for file_info in remapped_files),
        )
        if export_key in existing_keys:
            continue
        target_db.add(
            ExportPackage(
                project=target_project,
                status=source_export.status,
                formats=list(source_export.formats or []),
                files=remapped_files,
                selected_chapter_ids=list(source_export.selected_chapter_ids or []),
                selected_illustration_ids=list(source_export.selected_illustration_ids or []),
                created_at=source_export.created_at,
                completed_at=source_export.completed_at,
            )
        )
        existing_keys.add(export_key)
        report.exports_imported += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Import legacy StoryCraft SQLite databases into the configured primary database.")
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        default=[],
        help="Legacy SQLite database URL. Can be passed multiple times.",
    )
    args = parser.parse_args()

    settings = load_settings()
    sources = args.sources or detect_legacy_sqlite_database_urls()
    if not sources:
        raise SystemExit("No legacy SQLite databases were found.")

    report = import_legacy_sqlite_sources(
        source_database_urls=sources,
        target_database_url=settings.database_url,
        target_storage_dir=settings.storage_dir,
        target_export_dir=settings.export_dir,
    )
    print(report)


if __name__ == "__main__":
    main()
