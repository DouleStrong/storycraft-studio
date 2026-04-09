from __future__ import annotations

import asyncio
import json
import os

from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, selectinload

from .auth import get_current_user, get_db_session, hash_password, issue_token, verify_password
from .config import load_settings, review_intervention_min_severity
from .database import create_engine_and_session_factory
from .migrations import run_migrations
from .models import (
    Chapter,
    Character,
    CharacterReferenceImage,
    ExportPackage,
    GenerationJob,
    IllustrationAsset,
    NarrativeBlock,
    DialogueBlock,
    Project,
    ProjectSnapshot,
    ReviewIntervention,
    Scene,
    StoryBible,
    StoryBibleRevision,
    User,
)
from .providers import LLMProviderError, StoryAgentPipeline
from .schemas import (
    CharacterAttachRequest,
    ChapterLockRequest,
    DialogueBlockPatchRequest,
    EmptyRequest,
    ExportRequest,
    LoginRequest,
    NarrativeBlockPatchRequest,
    OutlineGenerateRequest,
    ProjectDuplicateRequest,
    ProjectCreateRequest,
    ProjectSnapshotRequest,
    RegisterRequest,
    ReviewInterventionRetryRequest,
    ScenePatchRequest,
    SceneIllustrationRequest,
    StoryBiblePatchRequest,
)
from .services import (
    build_chapter_revision_diff,
    build_story_bible_revision_diff,
    bootstrap_project,
    create_content_revision,
    create_character_visual_profile,
    create_story_bible_revision,
    current_story_bible_revision,
    delete_character_files,
    delete_export_files,
    delete_illustration_files,
    delete_project_files,
    require_content_revision,
    require_chapter,
    require_dialogue_block,
    require_export,
    require_illustration,
    require_job,
    require_narrative_block,
    require_project,
    require_review_intervention,
    require_scene,
    require_story_bible_revision,
    restore_chapter_from_payload,
    serialize_character,
    serialize_chapter,
    serialize_content_revision,
    serialize_dialogue_block,
    serialize_export,
    serialize_job,
    serialize_narrative_block,
    serialize_project,
    serialize_project_snapshot,
    serialize_review_intervention,
    serialize_scene,
    serialize_story_bible,
    serialize_story_bible_revision,
    snapshot_chapter_payload,
    snapshot_project_payload,
)
from .storage import LocalAssetStore
from .task_queue import InlineTaskQueue, RQTaskQueue, TaskQueue
from .workflow import WorkflowRunner


def create_app(
    *,
    story_agents: StoryAgentPipeline | None = None,
    task_queue: TaskQueue | None = None,
) -> FastAPI:
    settings = load_settings()
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    if settings.database_url.startswith("sqlite:///") and not (settings.allow_sqlite or os.getenv("PYTEST_CURRENT_TEST")):
        raise RuntimeError(
            "SQLite runtime support has been disabled. Configure STORY_PLATFORM_DB_URL to PostgreSQL and run the legacy import tool first."
        )
    if settings.database_url.startswith("sqlite:///"):
        db_path = settings.database_url.removeprefix("sqlite:///")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    run_migrations(settings)
    engine, session_factory = create_engine_and_session_factory(settings)

    asset_store = LocalAssetStore(settings.storage_dir, settings.export_dir)
    asset_store.storage_dir.mkdir(parents=True, exist_ok=True)
    asset_store.export_dir.mkdir(parents=True, exist_ok=True)

    injected_story_agents = story_agents is not None
    story_agents = story_agents or StoryAgentPipeline.from_settings(settings)
    workflow_runner = WorkflowRunner(
        session_factory,
        asset_store,
        story_agents,
        review_intervention_min_severity=review_intervention_min_severity(settings),
    )

    queue_backend = os.getenv("STORY_PLATFORM_QUEUE_BACKEND", "rq").strip().lower()
    if task_queue is None:
        if injected_story_agents or os.getenv("PYTEST_CURRENT_TEST") or queue_backend == "inline":
            task_queue = InlineTaskQueue(workflow_runner.run_job)
        else:
            task_queue = RQTaskQueue(
                redis_url=settings.redis_url,
                queue_name=settings.story_queue_name,
            )

    app = FastAPI(title=settings.app_name, version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.asset_store = asset_store
    app.state.story_agents = story_agents
    app.state.workflow_runner = workflow_runner
    app.state.task_queue = task_queue

    app.mount("/media/storage", StaticFiles(directory=str(settings.storage_dir)), name="storage")
    app.mount("/media/exports", StaticFiles(directory=str(settings.export_dir)), name="exports")
    if frontend_dir.exists():
        app.mount("/studio", StaticFiles(directory=str(frontend_dir), html=True), name="studio")

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/")
    async def root():
        if frontend_dir.exists():
            return RedirectResponse(url="/studio/")
        return {"name": settings.app_name}

    @app.post("/api/auth/register", status_code=201)
    async def register(payload: RegisterRequest, db: Session = Depends(get_db_session)):
        email = payload.email.strip().lower()
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        token = issue_token()
        user = User(
            email=email,
            password_hash=hash_password(payload.password),
            pen_name=payload.pen_name.strip(),
            access_token=token,
        )
        db.add(user)
        db.flush()
        return {"user": {"id": user.id, "email": user.email, "pen_name": user.pen_name}, "token": token}

    @app.post("/api/auth/login")
    async def login(payload: LoginRequest, db: Session = Depends(get_db_session)):
        email = payload.email.strip().lower()
        user = db.query(User).filter(User.email == email).first()
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user.access_token = issue_token()
        db.flush()
        return {"user": {"id": user.id, "email": user.email, "pen_name": user.pen_name}, "token": user.access_token}

    @app.get("/api/projects")
    async def list_projects(current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        projects = (
            db.query(Project)
            .filter(Project.owner_id == current_user.id)
            .order_by(Project.updated_at.desc())
            .all()
        )
        return [serialize_project(project, settings.storage_dir, settings.export_dir) for project in projects]

    @app.post("/api/projects", status_code=201)
    async def create_project(payload: ProjectCreateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        project = Project(
            owner=current_user,
            title=payload.title.strip(),
            genre=payload.genre.strip(),
            tone=payload.tone.strip(),
            era=payload.era.strip(),
            target_chapter_count=payload.target_chapter_count,
            target_length=payload.target_length.strip(),
            logline=payload.logline.strip(),
            status="draft",
        )
        db.add(project)
        db.flush()
        bootstrap_project(project, db, asset_store)
        create_story_bible_revision(project, db, created_by="system", created_by_user_id=current_user.id)
        db.flush()
        return serialize_project(project, settings.storage_dir, settings.export_dir)

    def project_character_load_options():
        return (
            selectinload(Project.owned_characters).selectinload(Character.reference_images),
            selectinload(Project.owned_characters).selectinload(Character.visual_profile),
            selectinload(Project.owned_characters).selectinload(Character.linked_projects),
            selectinload(Project.linked_characters).selectinload(Character.reference_images),
            selectinload(Project.linked_characters).selectinload(Character.visual_profile),
            selectinload(Project.linked_characters).selectinload(Character.project),
            selectinload(Project.linked_characters).selectinload(Character.linked_projects),
        )

    def character_library_load_options():
        return (
            selectinload(Character.reference_images),
            selectinload(Character.visual_profile),
            selectinload(Character.project),
            selectinload(Character.linked_projects),
        )

    def character_project_ids(character: Character) -> list[int]:
        return [project.id for project in character.projects]

    def attach_character_to_project(character: Character, project: Project) -> None:
        if project.id in character_project_ids(character):
            return
        character.linked_projects.append(project)

    def detach_character_from_project(character: Character, project: Project) -> bool:
        detached = False
        if character.project_id == project.id:
            character.project = None
            detached = True
        remaining_links = [item for item in character.linked_projects if item.id != project.id]
        if len(remaining_links) != len(character.linked_projects):
            character.linked_projects = remaining_links
            detached = True
        return detached

    async def persist_character(
        *,
        current_user: User,
        db: Session,
        name: str,
        role: str,
        personality: str,
        goal: str,
        speech_style: str,
        appearance: str,
        relationships: str,
        reference_image: UploadFile | None,
        project: Project | None = None,
    ) -> Character:
        character = Character(
            owner=current_user,
            project=project,
            name=name.strip(),
            role=role.strip(),
            personality=personality.strip(),
            goal=goal.strip(),
            speech_style=speech_style.strip(),
            appearance=appearance.strip(),
            relationships=relationships.strip(),
        )
        db.add(character)
        db.flush()

        if reference_image:
            payload = await reference_image.read()
            stored_path = asset_store.save_upload("reference-images", reference_image.filename, payload)
            db.add(CharacterReferenceImage(character=character, filename=reference_image.filename, path=stored_path))

        if project is not None:
            try:
                profile_result = app.state.story_agents.build_character_profile(project, character)
                create_character_visual_profile(character, profile_result.payload, db)
            except LLMProviderError:
                pass

        db.flush()
        db.refresh(character)
        return character

    def require_project_without_active_jobs(db: Session, current_user: User, project_id: int):
        project = (
            db.query(Project)
            .options(
                selectinload(Project.story_bible).selectinload(StoryBible.revisions),
                *project_character_load_options(),
                selectinload(Project.illustrations),
                selectinload(Project.exports),
                selectinload(Project.jobs),
                selectinload(Project.snapshots),
            )
            .filter(Project.id == project_id, Project.owner_id == current_user.id)
            .first()
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        active_job = next((job for job in project.jobs if job.status in {"queued", "processing"}), None)
        if active_job:
            raise HTTPException(status_code=409, detail="Project has active jobs and cannot be deleted yet")
        return project

    def require_chapter_without_active_jobs(db: Session, current_user: User, chapter_id: int) -> Chapter:
        chapter = require_chapter(db, current_user, chapter_id)
        active_job = (
            db.query(GenerationJob)
            .filter(
                GenerationJob.chapter_id == chapter.id,
                GenerationJob.status.in_(("queued", "processing")),
            )
            .first()
        )
        if active_job:
            raise HTTPException(status_code=409, detail="Chapter has active jobs and cannot change lock state")
        return chapter

    def require_project_with_content(db: Session, current_user: User, project_id: int) -> Project:
        project = (
            db.query(Project)
            .options(
                selectinload(Project.story_bible).selectinload(StoryBible.revisions),
                *project_character_load_options(),
                selectinload(Project.chapters).selectinload(Chapter.narrative_blocks),
                selectinload(Project.chapters).selectinload(Chapter.content_revisions),
                selectinload(Project.chapters).selectinload(Chapter.scenes).selectinload(Scene.dialogue_blocks),
                selectinload(Project.chapters).selectinload(Chapter.scenes).selectinload(Scene.illustrations),
                selectinload(Project.jobs),
                selectinload(Project.snapshots),
            )
            .filter(Project.id == project_id, Project.owner_id == current_user.id)
            .first()
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    def _normalize_queue_probe(probe: object) -> dict | None:
        if probe is None:
            return None
        if isinstance(probe, dict):
            return probe
        if hasattr(probe, "__dict__"):
            return dict(vars(probe))
        return None

    def sync_job_status_from_queue(job: GenerationJob, db: Session) -> GenerationJob:
        if job.status not in {"queued", "processing"}:
            return job

        probe_fn = getattr(app.state.task_queue, "probe", None)
        if not callable(probe_fn):
            return job

        probe = _normalize_queue_probe(probe_fn(job.id))
        if not probe:
            return job

        probe_status = str(probe.get("status", "")).strip().lower()
        probe_error = str(probe.get("error_message", "")).strip()
        probe_message = str(probe.get("status_message", "")).strip()
        did_change = False

        if probe_status == "failed":
            job.status = "failed"
            job.error_message = probe_error or job.error_message
            job.status_message = probe_message or f"任务失败：{probe_error or 'RQ worker execution failed'}"
            job.completed_at = job.completed_at or datetime.now(UTC)
            did_change = True
        elif probe_status == "processing" and job.status == "queued":
            job.status = "processing"
            job.status_message = probe_message or job.status_message or "Worker 已接手，正在处理当前任务。"
            did_change = True
        elif probe_status == "queued" and not job.status_message:
            job.status_message = probe_message or "任务已入队，正在等待 worker 接手。"
            did_change = True

        if did_change:
            db.flush()
        return job

    def sync_project_jobs_from_queue(project: Project, db: Session) -> None:
        for job in project.jobs:
            sync_job_status_from_queue(job, db)

    def queue_job(
        db: Session,
        current_user: User,
        job_type: str,
        snapshot: dict,
        *,
        project_id: int | None = None,
        chapter_id: int | None = None,
        scene_id: int | None = None,
        retry_count: int = 0,
    ):
        job = GenerationJob(
            user=current_user,
            project_id=project_id,
            chapter_id=chapter_id,
            scene_id=scene_id,
            job_type=job_type,
            status="queued",
            progress=0,
            status_message="任务已入队，正在等待 worker 接手。",
            input_snapshot=snapshot,
            retry_count=retry_count,
        )
        db.add(job)
        db.flush()
        db.commit()
        db.refresh(job)
        app.state.task_queue.enqueue(job.id)
        return job

    @app.delete("/api/projects/{project_id}", status_code=204)
    async def delete_project(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        project = require_project_without_active_jobs(db, current_user, project_id)
        delete_project_files(project, asset_store)
        for character in list(project.owned_characters):
            character.project = None
        for illustration in list(project.illustrations):
            db.delete(illustration)
        for job in list(project.jobs):
            db.delete(job)
        db.delete(project)
        db.flush()
        return Response(status_code=204)

    @app.get("/api/projects/{project_id}")
    async def project_detail(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        project = (
            db.query(Project)
            .options(
                selectinload(Project.story_bible).selectinload(StoryBible.revisions),
                *project_character_load_options(),
                selectinload(Project.chapters).selectinload(Chapter.narrative_blocks),
                selectinload(Project.chapters).selectinload(Chapter.content_revisions),
                selectinload(Project.chapters).selectinload(Chapter.review_interventions),
                selectinload(Project.chapters).selectinload(Chapter.scenes).selectinload(Scene.dialogue_blocks),
                selectinload(Project.chapters).selectinload(Chapter.scenes).selectinload(Scene.illustrations),
                selectinload(Project.jobs),
                selectinload(Project.exports),
                selectinload(Project.snapshots),
            )
            .filter(Project.id == project_id, Project.owner_id == current_user.id)
            .first()
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        sync_project_jobs_from_queue(project, db)
        return serialize_project(project, settings.storage_dir, settings.export_dir, detailed=True)

    @app.get("/api/projects/{project_id}/story-bible")
    async def get_story_bible(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        project = require_project_with_content(db, current_user, project_id)
        return serialize_story_bible(project.story_bible)

    @app.patch("/api/projects/{project_id}/story-bible")
    async def patch_story_bible(
        project_id: int,
        payload: StoryBiblePatchRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        project = require_project_with_content(db, current_user, project_id)
        story_bible = project.story_bible
        if not story_bible:
            raise HTTPException(status_code=404, detail="Story Bible not found")

        if payload.world_notes is not None:
            story_bible.world_notes = payload.world_notes.strip()
        if payload.style_notes is not None:
            story_bible.style_notes = payload.style_notes.strip()
        if payload.writing_rules is not None:
            story_bible.writing_rules = [item.strip() for item in payload.writing_rules if str(item).strip()]
        if payload.addressing_rules is not None:
            story_bible.addressing_rules = payload.addressing_rules.strip()
        if payload.timeline_rules is not None:
            story_bible.timeline_rules = payload.timeline_rules.strip()

        create_story_bible_revision(project, db, created_by="user", created_by_user_id=current_user.id)
        db.flush()
        return serialize_story_bible(story_bible)

    @app.get("/api/projects/{project_id}/story-bible/revisions")
    async def list_story_bible_revisions(
        project_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        project = require_project_with_content(db, current_user, project_id)
        revisions = sorted(project.story_bible.revisions, key=lambda item: (item.revision_index, item.id), reverse=True)
        return [serialize_story_bible_revision(item) for item in revisions]

    @app.get("/api/projects/{project_id}/story-bible/revisions/{revision_id}/diff")
    async def get_story_bible_revision_diff(
        project_id: int,
        revision_id: int,
        base_revision_id: int | None = None,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        project = require_project_with_content(db, current_user, project_id)
        target_revision = require_story_bible_revision(db, current_user, project_id, revision_id)
        if base_revision_id is not None:
            base_revision = require_story_bible_revision(db, current_user, project_id, base_revision_id)
        else:
            base_revision = current_story_bible_revision(project.story_bible)
        return build_story_bible_revision_diff(base_revision, target_revision)

    @app.post("/api/projects/{project_id}/snapshots", status_code=201)
    async def create_project_snapshot(
        project_id: int,
        payload: ProjectSnapshotRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        project = require_project_with_content(db, current_user, project_id)
        snapshot = ProjectSnapshot(
            project=project,
            label=payload.label.strip(),
            payload=snapshot_project_payload(project, settings.storage_dir, settings.export_dir),
            created_by="user",
            created_by_user_id=current_user.id,
        )
        db.add(snapshot)
        db.flush()
        return serialize_project_snapshot(snapshot)

    @app.get("/api/projects/{project_id}/snapshots")
    async def list_project_snapshots(
        project_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        project = require_project_with_content(db, current_user, project_id)
        snapshots = sorted(project.snapshots, key=lambda item: item.id, reverse=True)
        return [serialize_project_snapshot(item) for item in snapshots]

    @app.post("/api/projects/{project_id}/duplicate", status_code=201)
    async def duplicate_project(
        project_id: int,
        payload: ProjectDuplicateRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        project = require_project_with_content(db, current_user, project_id)
        duplicate = Project(
            owner=current_user,
            title=(payload.title or f"{project.title}·副本").strip(),
            genre=project.genre,
            tone=project.tone,
            era=project.era,
            target_chapter_count=project.target_chapter_count,
            target_length=project.target_length,
            logline=project.logline,
            status=project.status,
        )
        db.add(duplicate)
        db.flush()
        bootstrap_project(duplicate, db, asset_store)
        db.flush()

        if duplicate.story_bible and project.story_bible:
            duplicate.story_bible.world_notes = project.story_bible.world_notes
            duplicate.story_bible.style_notes = project.story_bible.style_notes
            duplicate.story_bible.writing_rules = list(project.story_bible.writing_rules)
            duplicate.story_bible.addressing_rules = project.story_bible.addressing_rules
            duplicate.story_bible.timeline_rules = project.story_bible.timeline_rules
        duplicate_story_bible_revision = create_story_bible_revision(
            duplicate,
            db,
            created_by="duplicate",
            created_by_user_id=current_user.id,
        )

        for character in project.characters:
            attach_character_to_project(character, duplicate)

        for chapter in sorted(project.chapters, key=lambda item: item.order_index):
            new_chapter = Chapter(
                project=duplicate,
                order_index=chapter.order_index,
                title=chapter.title,
                summary=chapter.summary,
                chapter_goal=chapter.chapter_goal,
                hook=chapter.hook,
                status=chapter.status,
                is_locked=chapter.is_locked,
                source_story_bible_revision_id=duplicate_story_bible_revision.id if duplicate_story_bible_revision else None,
                continuity_notes=list(chapter.continuity_notes),
            )
            db.add(new_chapter)
            db.flush()

            for block in sorted(chapter.narrative_blocks, key=lambda item: item.order_index):
                db.add(
                    NarrativeBlock(
                        chapter=new_chapter,
                        order_index=block.order_index,
                        content=block.content,
                        is_locked=block.is_locked,
                        is_user_edited=block.is_user_edited,
                        source_revision_id=block.source_revision_id,
                        last_editor_type=block.last_editor_type,
                    )
                )

            for scene in sorted(chapter.scenes, key=lambda item: item.order_index):
                new_scene = Scene(
                    chapter=new_chapter,
                    order_index=scene.order_index,
                    title=scene.title,
                    scene_type=scene.scene_type,
                    location=scene.location,
                    time_of_day=scene.time_of_day,
                    cast_names=list(scene.cast_names),
                    objective=scene.objective,
                    emotional_tone=scene.emotional_tone,
                    visual_prompt=scene.visual_prompt,
                    is_locked=scene.is_locked,
                    is_user_edited=scene.is_user_edited,
                    source_revision_id=scene.source_revision_id,
                    last_editor_type=scene.last_editor_type,
                )
                db.add(new_scene)
                db.flush()
                for dialogue in sorted(scene.dialogue_blocks, key=lambda item: item.order_index):
                    db.add(
                        DialogueBlock(
                            scene=new_scene,
                            order_index=dialogue.order_index,
                            speaker=dialogue.speaker,
                            parenthetical=dialogue.parenthetical,
                            content=dialogue.content,
                            is_locked=dialogue.is_locked,
                            is_user_edited=dialogue.is_user_edited,
                            source_revision_id=dialogue.source_revision_id,
                            last_editor_type=dialogue.last_editor_type,
                        )
                    )

                for illustration in sorted(scene.illustrations, key=lambda item: item.candidate_index):
                    original_file = Path(illustration.file_path)
                    original_thumb = Path(illustration.thumbnail_path)
                    if not original_file.exists() or not original_thumb.exists():
                        continue
                    duplicated_file_path = asset_store.save_upload(
                        "illustrations",
                        original_file.name,
                        original_file.read_bytes(),
                    )
                    duplicated_thumb_path = asset_store.save_upload(
                        "illustrations/thumbs",
                        original_thumb.name,
                        original_thumb.read_bytes(),
                    )
                    db.add(
                        IllustrationAsset(
                            project=duplicate,
                            scene=new_scene,
                            prompt_text=illustration.prompt_text,
                            file_path=duplicated_file_path,
                            thumbnail_path=duplicated_thumb_path,
                            status=illustration.status,
                            candidate_index=illustration.candidate_index,
                            is_canonical=illustration.is_canonical,
                        )
                    )

            db.flush()
            duplicate_revision = create_content_revision(
                new_chapter,
                db,
                revision_kind="duplicate",
                created_by="duplicate",
                created_by_user_id=current_user.id,
                summary=f"Duplicated from project {project.id}.",
                story_bible_revision_id=duplicate_story_bible_revision.id if duplicate_story_bible_revision else None,
            )
            for block in new_chapter.narrative_blocks:
                if block.source_revision_id is None:
                    block.source_revision_id = duplicate_revision.id
            for scene in new_chapter.scenes:
                if scene.source_revision_id is None:
                    scene.source_revision_id = duplicate_revision.id
                for dialogue in scene.dialogue_blocks:
                    if dialogue.source_revision_id is None:
                        dialogue.source_revision_id = duplicate_revision.id
            duplicate_revision.payload = snapshot_project_payload(duplicate, settings.storage_dir, settings.export_dir)["chapters"][
                new_chapter.order_index - 1
            ]

        db.flush()
        db.refresh(duplicate)
        duplicate = require_project_with_content(db, current_user, duplicate.id)
        return serialize_project(duplicate, settings.storage_dir, settings.export_dir, detailed=True)

    @app.get("/api/characters")
    async def list_character_library(current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        characters = (
            db.query(Character)
            .options(*character_library_load_options())
            .filter(Character.owner_id == current_user.id)
            .order_by(Character.updated_at.desc(), Character.id.desc())
            .all()
        )
        return [serialize_character(character, settings.storage_dir) for character in characters]

    @app.post("/api/characters", status_code=201)
    async def create_library_character(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
        name: str = Form(...),
        role: str = Form(...),
        personality: str = Form(...),
        goal: str = Form(...),
        speech_style: str = Form(...),
        appearance: str = Form(...),
        relationships: str = Form(...),
        project_id: int | None = Form(default=None),
        reference_image: UploadFile | None = File(default=None),
    ):
        project = require_project(db, current_user, project_id) if project_id else None
        character = await persist_character(
            current_user=current_user,
            db=db,
            name=name,
            role=role,
            personality=personality,
            goal=goal,
            speech_style=speech_style,
            appearance=appearance,
            relationships=relationships,
            reference_image=reference_image,
            project=project,
        )
        return serialize_character(character, settings.storage_dir)

    @app.post("/api/projects/{project_id}/characters", status_code=201)
    async def create_character(
        project_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
        name: str = Form(...),
        role: str = Form(...),
        personality: str = Form(...),
        goal: str = Form(...),
        speech_style: str = Form(...),
        appearance: str = Form(...),
        relationships: str = Form(...),
        reference_image: UploadFile | None = File(default=None),
    ):
        project = require_project(db, current_user, project_id)
        character = await persist_character(
            current_user=current_user,
            db=db,
            name=name,
            role=role,
            personality=personality,
            goal=goal,
            speech_style=speech_style,
            appearance=appearance,
            relationships=relationships,
            reference_image=reference_image,
            project=project,
        )
        return serialize_character(character, settings.storage_dir)

    @app.post("/api/projects/{project_id}/characters/attach")
    async def attach_character(
        project_id: int,
        payload: CharacterAttachRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        project = require_project(db, current_user, project_id)
        character = (
            db.query(Character)
            .options(*character_library_load_options())
            .filter(Character.id == payload.character_id, Character.owner_id == current_user.id)
            .first()
        )
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")
        attach_character_to_project(character, project)
        db.flush()
        db.refresh(character)
        return serialize_character(character, settings.storage_dir)

    @app.delete("/api/projects/{project_id}/characters/{character_id}", status_code=204)
    async def detach_character(
        project_id: int,
        character_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        project = require_project(db, current_user, project_id)
        character = (
            db.query(Character)
            .options(*character_library_load_options())
            .filter(Character.id == character_id, Character.owner_id == current_user.id)
            .first()
        )
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

        active_job = (
            db.query(GenerationJob)
            .filter(
                GenerationJob.project_id == project.id,
                GenerationJob.status.in_(("queued", "processing")),
            )
            .first()
        )
        if active_job:
            raise HTTPException(status_code=409, detail="Project has active jobs and cannot change characters yet")

        if not detach_character_from_project(character, project):
            raise HTTPException(status_code=404, detail="Character is not attached to this project")

        db.flush()
        return Response(status_code=204)

    @app.delete("/api/characters/{character_id}", status_code=204)
    async def delete_character(character_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        character = (
            db.query(Character)
            .options(*character_library_load_options())
            .filter(Character.id == character_id, Character.owner_id == current_user.id)
            .first()
        )
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

        project_ids = character_project_ids(character)
        active_job = (
            db.query(GenerationJob)
            .filter(GenerationJob.project_id.in_(project_ids), GenerationJob.status.in_(("queued", "processing")))
            .first()
        )
        if active_job:
            raise HTTPException(status_code=409, detail="Character is referenced by a project with active jobs")

        delete_character_files(character, asset_store)
        for illustration in db.query(IllustrationAsset).filter(IllustrationAsset.character_id == character.id).all():
            illustration.character_id = None
        db.delete(character)
        db.flush()
        return Response(status_code=204)

    @app.post("/api/projects/{project_id}/generate/outline", status_code=202)
    async def generate_outline(project_id: int, payload: OutlineGenerateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        project = require_project(db, current_user, project_id)
        latest_story_bible_revision = current_story_bible_revision(project.story_bible)
        snapshot = {}
        if payload.chapter_count is not None:
            snapshot["chapter_count"] = payload.chapter_count
        else:
            snapshot["chapter_count"] = project.target_chapter_count
        if latest_story_bible_revision:
            snapshot["story_bible_revision_id"] = latest_story_bible_revision.id
        job = queue_job(db, current_user, "outline", snapshot, project_id=project_id)
        return serialize_job(job)

    @app.post("/api/chapters/{chapter_id}/generate-draft", status_code=202)
    async def generate_chapter_draft(chapter_id: int, payload: EmptyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        chapter = require_chapter(db, current_user, chapter_id)
        if chapter.is_locked:
            raise HTTPException(status_code=409, detail="Locked chapter cannot be regenerated")
        snapshot = {}
        latest_story_bible_revision = current_story_bible_revision(chapter.project.story_bible)
        if latest_story_bible_revision:
            snapshot["story_bible_revision_id"] = latest_story_bible_revision.id
        job = queue_job(db, current_user, "chapter_draft", snapshot, project_id=chapter.project_id, chapter_id=chapter.id)
        return serialize_job(job)

    @app.post("/api/chapters/{chapter_id}/generate-scenes", status_code=202)
    async def generate_chapter_scenes(chapter_id: int, payload: EmptyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        chapter = require_chapter(db, current_user, chapter_id)
        if chapter.is_locked:
            raise HTTPException(status_code=409, detail="Locked chapter cannot be regenerated")
        snapshot = {}
        latest_story_bible_revision = current_story_bible_revision(chapter.project.story_bible)
        if latest_story_bible_revision:
            snapshot["story_bible_revision_id"] = latest_story_bible_revision.id
        job = queue_job(db, current_user, "chapter_scenes", snapshot, project_id=chapter.project_id, chapter_id=chapter.id)
        return serialize_job(job)

    @app.get("/api/chapters/{chapter_id}/revisions")
    async def list_chapter_revisions(chapter_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        chapter = (
            db.query(Chapter)
            .options(selectinload(Chapter.content_revisions))
            .join(Project, Chapter.project_id == Project.id)
            .filter(Chapter.id == chapter_id, Project.owner_id == current_user.id)
            .first()
        )
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
        revisions = sorted(chapter.content_revisions, key=lambda item: item.id, reverse=True)
        return [serialize_content_revision(item) for item in revisions]

    @app.get("/api/chapters/{chapter_id}/revisions/{revision_id}/diff")
    async def get_chapter_revision_diff(
        chapter_id: int,
        revision_id: int,
        base_revision_id: int | None = None,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        chapter = require_chapter(db, current_user, chapter_id)
        target_revision = require_content_revision(db, current_user, chapter_id, revision_id)
        base_revision = (
            require_content_revision(db, current_user, chapter_id, base_revision_id) if base_revision_id is not None else None
        )
        return build_chapter_revision_diff(chapter, target_revision=target_revision, base_revision=base_revision)

    @app.post("/api/chapters/{chapter_id}/revisions/{revision_id}/restore")
    async def restore_chapter_revision(
        chapter_id: int,
        revision_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        chapter = require_chapter_without_active_jobs(db, current_user, chapter_id)
        revision = require_content_revision(db, current_user, chapter_id, revision_id)
        restore_chapter_from_payload(chapter, revision.payload or {}, db)
        restored_revision = create_content_revision(
            chapter,
            db,
            revision_kind="restore",
            created_by="user",
            created_by_user_id=current_user.id,
            summary=f"Restored from revision {revision.id}.",
            story_bible_revision_id=revision.story_bible_revision_id,
        )
        for block in chapter.narrative_blocks:
            block.source_revision_id = restored_revision.id
        for scene in chapter.scenes:
            scene.source_revision_id = restored_revision.id
            for dialogue in scene.dialogue_blocks:
                dialogue.source_revision_id = restored_revision.id
        restored_revision.payload = snapshot_chapter_payload(chapter)
        db.flush()
        return serialize_chapter(chapter, settings.storage_dir)

    @app.patch("/api/narrative-blocks/{block_id}")
    async def patch_narrative_block(
        block_id: int,
        payload: NarrativeBlockPatchRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        block = require_narrative_block(db, current_user, block_id)
        chapter = require_chapter_without_active_jobs(db, current_user, block.chapter_id)
        if payload.content is not None:
            block.content = payload.content
        if payload.is_locked is not None:
            block.is_locked = payload.is_locked
        block.is_user_edited = True
        block.last_editor_type = "user"
        revision = create_content_revision(
            chapter,
            db,
            revision_kind="user_patch",
            created_by="user",
            created_by_user_id=current_user.id,
            summary=f"User edited narrative block {block.id}.",
        )
        block.source_revision_id = revision.id
        revision.payload = snapshot_chapter_payload(chapter)
        db.flush()
        return serialize_narrative_block(block)

    @app.patch("/api/dialogue-blocks/{block_id}")
    async def patch_dialogue_block(
        block_id: int,
        payload: DialogueBlockPatchRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        block = require_dialogue_block(db, current_user, block_id)
        chapter = require_chapter_without_active_jobs(db, current_user, block.scene.chapter_id)
        if payload.speaker is not None:
            block.speaker = payload.speaker.strip()
        if payload.parenthetical is not None:
            block.parenthetical = payload.parenthetical.strip()
        if payload.content is not None:
            block.content = payload.content
        if payload.is_locked is not None:
            block.is_locked = payload.is_locked
        block.is_user_edited = True
        block.last_editor_type = "user"
        revision = create_content_revision(
            chapter,
            db,
            revision_kind="user_patch",
            created_by="user",
            created_by_user_id=current_user.id,
            summary=f"User edited dialogue block {block.id}.",
        )
        block.source_revision_id = revision.id
        revision.payload = snapshot_chapter_payload(chapter)
        db.flush()
        return serialize_dialogue_block(block)

    @app.patch("/api/scenes/{scene_id}")
    async def patch_scene(
        scene_id: int,
        payload: ScenePatchRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        scene = require_scene(db, current_user, scene_id)
        chapter = require_chapter_without_active_jobs(db, current_user, scene.chapter_id)
        if payload.title is not None:
            scene.title = payload.title.strip()
        if payload.scene_type is not None:
            scene.scene_type = payload.scene_type.strip().upper() or scene.scene_type
        if payload.location is not None:
            scene.location = payload.location.strip()
        if payload.time_of_day is not None:
            scene.time_of_day = payload.time_of_day.strip().upper() or scene.time_of_day
        if payload.cast_names is not None:
            scene.cast_names = [str(name).strip() for name in payload.cast_names if str(name).strip()]
        if payload.objective is not None:
            scene.objective = payload.objective.strip()
        if payload.emotional_tone is not None:
            scene.emotional_tone = payload.emotional_tone.strip()
        if payload.visual_prompt is not None:
            scene.visual_prompt = payload.visual_prompt.strip()
        if payload.is_locked is not None:
            scene.is_locked = payload.is_locked
        scene.is_user_edited = True
        scene.last_editor_type = "user"
        revision = create_content_revision(
            chapter,
            db,
            revision_kind="user_patch",
            created_by="user",
            created_by_user_id=current_user.id,
            summary=f"User edited scene {scene.id}.",
        )
        scene.source_revision_id = revision.id
        revision.payload = snapshot_chapter_payload(chapter)
        db.flush()
        return serialize_scene(scene, settings.storage_dir)

    @app.post("/api/scenes/{scene_id}/generate-illustrations", status_code=202)
    async def generate_scene_illustrations(
        scene_id: int,
        payload: SceneIllustrationRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        scene = require_scene(db, current_user, scene_id)
        job = queue_job(
            db,
            current_user,
            "scene_illustrations",
            {
                "candidate_count": payload.candidate_count,
                "extra_guidance": payload.extra_guidance.strip(),
            },
            project_id=scene.chapter.project_id,
            chapter_id=scene.chapter_id,
            scene_id=scene.id,
        )
        return serialize_job(job)

    @app.post("/api/illustrations/{illustration_id}/canonical")
    async def mark_illustration_canonical(
        illustration_id: int,
        payload: EmptyRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        illustration = require_illustration(db, current_user, illustration_id)
        if illustration.scene_id:
            siblings = db.query(IllustrationAsset).filter(IllustrationAsset.scene_id == illustration.scene_id).all()
            for sibling in siblings:
                sibling.is_canonical = sibling.id == illustration.id
        illustration.is_canonical = True
        db.flush()
        return {"id": illustration.id, "is_canonical": illustration.is_canonical}

    @app.delete("/api/illustrations/{illustration_id}", status_code=204)
    async def delete_illustration(illustration_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        illustration = require_illustration(db, current_user, illustration_id)
        scene_id = illustration.scene_id
        was_canonical = illustration.is_canonical
        delete_illustration_files(illustration, asset_store)
        db.delete(illustration)
        db.flush()

        if was_canonical and scene_id:
            replacement = (
                db.query(IllustrationAsset)
                .filter(IllustrationAsset.scene_id == scene_id)
                .order_by(IllustrationAsset.candidate_index.asc(), IllustrationAsset.id.asc())
                .first()
            )
            if replacement:
                replacement.is_canonical = True
                db.flush()
        return Response(status_code=204)

    @app.post("/api/projects/{project_id}/exports", status_code=202)
    async def create_export(project_id: int, payload: ExportRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        project = require_project(db, current_user, project_id)
        selected_chapter_ids = [chapter.id for chapter in sorted(project.chapters, key=lambda item: item.order_index)]
        selected_illustration_ids = [
            illustration.id
            for chapter in sorted(project.chapters, key=lambda item: item.order_index)
            for scene in sorted(chapter.scenes, key=lambda item: item.order_index)
            for illustration in scene.illustrations
            if illustration.is_canonical
        ]
        export_package = ExportPackage(
            project=project,
            status="queued",
            formats=payload.formats,
            selected_chapter_ids=selected_chapter_ids,
            selected_illustration_ids=selected_illustration_ids,
        )
        db.add(export_package)
        db.flush()
        job = queue_job(
            db,
            current_user,
            "export",
            {"export_id": export_package.id},
            project_id=project.id,
        )
        return serialize_job(job)

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        job = (
            db.query(GenerationJob)
            .options(selectinload(GenerationJob.agent_runs), selectinload(GenerationJob.review_interventions))
            .filter(GenerationJob.id == job_id, GenerationJob.user_id == current_user.id)
            .first()
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        sync_job_status_from_queue(job, db)
        return serialize_job(job, detailed=True)

    @app.post("/api/jobs/{job_id}/retry", status_code=202)
    async def retry_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        job = require_job(db, current_user, job_id)
        sync_job_status_from_queue(job, db)
        if job.status != "failed":
            raise HTTPException(status_code=409, detail="Only failed jobs can be retried")
        if job.chapter_id:
            chapter = require_chapter(db, current_user, job.chapter_id)
            if chapter.is_locked and job.job_type in {"chapter_draft", "chapter_draft_retry", "chapter_scenes", "chapter_scenes_retry"}:
                raise HTTPException(status_code=409, detail="Locked chapter cannot be retried")

        follow_up_job = queue_job(
            db,
            current_user,
            job.job_type,
            dict(job.input_snapshot or {}),
            project_id=job.project_id,
            chapter_id=job.chapter_id,
            scene_id=job.scene_id,
            retry_count=(job.retry_count or 0) + 1,
        )
        return serialize_job(follow_up_job)

    def load_job_snapshot(job_id: int, *, user_id: int) -> dict | None:
        with session_factory() as session:
            job = (
                session.query(GenerationJob)
                .options(selectinload(GenerationJob.agent_runs), selectinload(GenerationJob.review_interventions))
                .filter(GenerationJob.id == job_id, GenerationJob.user_id == user_id)
                .first()
            )
            if not job:
                return None
            sync_job_status_from_queue(job, session)
            return serialize_job(job, detailed=True)

    @app.get("/api/jobs/{job_id}/stream")
    async def stream_job(job_id: int, once: bool = False, current_user: User = Depends(get_current_user)):
        initial_payload = load_job_snapshot(job_id, user_id=current_user.id)
        if not initial_payload:
            raise HTTPException(status_code=404, detail="Job not found")

        async def event_stream():
            last_emitted = None
            while True:
                payload = load_job_snapshot(job_id, user_id=current_user.id)
                if payload is None:
                    break
                serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                if serialized != last_emitted:
                    last_emitted = serialized
                    yield f"event: job\ndata: {serialized}\n\n"
                    if once:
                        break
                if payload["status"] in {"awaiting_user", "completed", "failed"}:
                    done_payload = json.dumps(
                        {"job_id": job_id, "status": payload["status"]},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    yield f"event: done\ndata: {done_payload}\n\n"
                    break
                await asyncio.sleep(0.25)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/exports/{export_id}")
    async def get_export(export_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        export_package = require_export(db, current_user, export_id)
        return serialize_export(export_package, settings.export_dir)

    @app.delete("/api/exports/{export_id}", status_code=204)
    async def delete_export(export_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        export_package = require_export(db, current_user, export_id)
        if export_package.status in {"queued", "processing"}:
            raise HTTPException(status_code=409, detail="Export is still running and cannot be deleted yet")
        delete_export_files(export_package, asset_store)
        db.delete(export_package)
        db.flush()
        return Response(status_code=204)

    @app.patch("/api/chapters/{chapter_id}/lock")
    async def lock_chapter(
        chapter_id: int,
        payload: ChapterLockRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        chapter = require_chapter_without_active_jobs(db, current_user, chapter_id)
        chapter.is_locked = payload.locked
        db.flush()
        return {"id": chapter.id, "is_locked": chapter.is_locked}

    @app.post("/api/review-interventions/{intervention_id}/retry", status_code=202)
    async def retry_review_intervention(
        intervention_id: int,
        payload: ReviewInterventionRetryRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        intervention = require_review_intervention(db, current_user, intervention_id)
        if intervention.status != "pending":
            raise HTTPException(status_code=409, detail="Review intervention has already been handled")

        chapter = require_chapter(db, current_user, intervention.chapter_id)
        if chapter.is_locked:
            raise HTTPException(status_code=409, detail="Locked chapter cannot be regenerated")

        original_job = intervention.job
        extra_guidance = payload.extra_guidance.strip()
        snapshot = {"extra_guidance": extra_guidance, "intervention_id": intervention.id}

        if intervention.intervention_type == "rewrite_writer":
            if original_job.job_type in {"chapter_draft", "chapter_draft_retry"}:
                job_type = "chapter_draft_retry"
            elif original_job.job_type in {"chapter_scenes", "chapter_scenes_retry"}:
                job_type = "chapter_scenes_retry"
            else:
                raise HTTPException(status_code=409, detail="This intervention cannot trigger a writer rewrite")
        elif intervention.intervention_type == "fallback_planner":
            job_type = "outline_repair"
            snapshot["anchor_chapter_id"] = chapter.id
            snapshot["chapter_count"] = chapter.project.target_chapter_count
        else:
            raise HTTPException(status_code=409, detail="Unsupported intervention type")

        follow_up_job = queue_job(
            db,
            current_user,
            job_type,
            snapshot,
            project_id=chapter.project_id,
            chapter_id=chapter.id if job_type != "outline_repair" else None,
            retry_count=(original_job.retry_count or 0) + 1,
        )
        intervention.user_guidance = extra_guidance
        intervention.status = "resolved"
        intervention.resolution_job_id = follow_up_job.id
        intervention.resolved_at = datetime.now(UTC)
        db.flush()
        return serialize_job(follow_up_job)

    @app.post("/api/review-interventions/{intervention_id}/dismiss")
    async def dismiss_review_intervention(
        intervention_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ):
        intervention = require_review_intervention(db, current_user, intervention_id)
        if intervention.status != "pending":
            raise HTTPException(status_code=409, detail="Review intervention has already been handled")
        intervention.status = "dismissed"
        intervention.resolved_at = datetime.now(UTC)
        db.flush()
        return serialize_review_intervention(intervention)

    @app.delete("/api/jobs/{job_id}", status_code=204)
    async def delete_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
        job = require_job(db, current_user, job_id)
        if job.status in {"queued", "processing"}:
            raise HTTPException(status_code=409, detail="Job is still running and cannot be deleted yet")
        db.delete(job)
        db.flush()
        return Response(status_code=204)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return app


app = create_app()
