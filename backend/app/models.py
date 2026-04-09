from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    pen_name: Mapped[str] = mapped_column(String(120))
    access_token: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    projects: Mapped[list["Project"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    characters: Mapped[list["Character"]] = relationship(back_populates="owner")
    jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    genre: Mapped[str] = mapped_column(String(120))
    tone: Mapped[str] = mapped_column(String(255))
    era: Mapped[str] = mapped_column(String(120))
    target_chapter_count: Mapped[int] = mapped_column(Integer, default=6)
    target_length: Mapped[str] = mapped_column(String(120))
    logline: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    cover_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    owner: Mapped["User"] = relationship(back_populates="projects")
    story_bible: Mapped["StoryBible"] = relationship(back_populates="project", cascade="all, delete-orphan", uselist=False)
    owned_characters: Mapped[list["Character"]] = relationship(back_populates="project", foreign_keys="Character.project_id")
    character_links: Mapped[list["ProjectCharacterLink"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    linked_characters: Mapped[list["Character"]] = relationship(
        secondary="project_characters",
        back_populates="linked_projects",
        overlaps="character_links,project_links,project",
    )
    chapters: Mapped[list["Chapter"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="project")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="project")
    illustrations: Mapped[list["IllustrationAsset"]] = relationship(back_populates="project")
    exports: Mapped[list["ExportPackage"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    story_bible_revisions: Mapped[list["StoryBibleRevision"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    snapshots: Mapped[list["ProjectSnapshot"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    @property
    def characters(self) -> list["Character"]:
        merged: dict[int, Character] = {}
        for character in [*self.owned_characters, *self.linked_characters]:
            merged[character.id] = character
        return sorted(merged.values(), key=lambda item: (item.created_at, item.id))


class StoryBible(TimestampMixin, Base):
    __tablename__ = "story_bibles"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True)
    world_notes: Mapped[str] = mapped_column(Text, default="")
    style_notes: Mapped[str] = mapped_column(Text, default="")
    writing_rules: Mapped[list[str]] = mapped_column(JSON, default=list)
    addressing_rules: Mapped[str] = mapped_column(Text, default="")
    timeline_rules: Mapped[str] = mapped_column(Text, default="")

    project: Mapped["Project"] = relationship(back_populates="story_bible")
    revisions: Mapped[list["StoryBibleRevision"]] = relationship(back_populates="story_bible", cascade="all, delete-orphan")


class StoryBibleRevision(Base):
    __tablename__ = "story_bible_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    story_bible_id: Mapped[int] = mapped_column(ForeignKey("story_bibles.id"), index=True)
    revision_index: Mapped[int] = mapped_column(Integer, default=1)
    world_notes: Mapped[str] = mapped_column(Text, default="")
    style_notes: Mapped[str] = mapped_column(Text, default="")
    writing_rules: Mapped[list[str]] = mapped_column(JSON, default=list)
    addressing_rules: Mapped[str] = mapped_column(Text, default="")
    timeline_rules: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(40), default="system")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    source_job_id: Mapped[int | None] = mapped_column(ForeignKey("generation_jobs.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    project: Mapped["Project"] = relationship(back_populates="story_bible_revisions")
    story_bible: Mapped["StoryBible"] = relationship(back_populates="revisions")


class ProjectCharacterLink(Base):
    __tablename__ = "project_characters"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), primary_key=True)

    project: Mapped["Project"] = relationship(back_populates="character_links", overlaps="linked_characters,linked_projects")
    character: Mapped["Character"] = relationship(back_populates="project_links", overlaps="linked_characters,linked_projects")


class Character(TimestampMixin, Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True, deferred=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(255))
    personality: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    speech_style: Mapped[str] = mapped_column(Text)
    appearance: Mapped[str] = mapped_column(Text)
    relationships: Mapped[str] = mapped_column(Text)
    signature_line: Mapped[str] = mapped_column(String(255), default="")

    owner: Mapped["User"] = relationship(back_populates="characters")
    project: Mapped["Project"] = relationship(back_populates="owned_characters")
    project_links: Mapped[list["ProjectCharacterLink"]] = relationship(back_populates="character", cascade="all, delete-orphan")
    linked_projects: Mapped[list["Project"]] = relationship(
        secondary="project_characters",
        back_populates="linked_characters",
        overlaps="character_links,project_links,project",
    )
    reference_images: Mapped[list["CharacterReferenceImage"]] = relationship(back_populates="character", cascade="all, delete-orphan")
    visual_profile: Mapped["CharacterVisualProfile"] = relationship(back_populates="character", cascade="all, delete-orphan", uselist=False)
    illustrations: Mapped[list["IllustrationAsset"]] = relationship(back_populates="character")

    @property
    def projects(self) -> list["Project"]:
        merged: dict[int, Project] = {}
        if self.project is not None:
            merged[self.project.id] = self.project
        for project in self.linked_projects:
            merged[project.id] = project
        return sorted(merged.values(), key=lambda item: item.id)


class CharacterReferenceImage(TimestampMixin, Base):
    __tablename__ = "character_reference_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))

    character: Mapped["Character"] = relationship(back_populates="reference_images")


class CharacterVisualProfile(TimestampMixin, Base):
    __tablename__ = "character_visual_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), unique=True)
    visual_anchor: Mapped[str] = mapped_column(Text)
    signature_palette: Mapped[str] = mapped_column(String(255))
    silhouette_notes: Mapped[str] = mapped_column(Text)
    wardrobe_notes: Mapped[str] = mapped_column(Text)
    atmosphere_notes: Mapped[str] = mapped_column(Text)

    character: Mapped["Character"] = relationship(back_populates="visual_profile")


class Chapter(TimestampMixin, Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    chapter_goal: Mapped[str] = mapped_column(Text)
    hook: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="planned")
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    source_story_bible_revision_id: Mapped[int | None] = mapped_column(ForeignKey("story_bible_revisions.id"), nullable=True, index=True)
    continuity_notes: Mapped[list[str]] = mapped_column(JSON, default=list)

    project: Mapped["Project"] = relationship(back_populates="chapters")
    narrative_blocks: Mapped[list["NarrativeBlock"]] = relationship(back_populates="chapter", cascade="all, delete-orphan")
    scenes: Mapped[list["Scene"]] = relationship(back_populates="chapter", cascade="all, delete-orphan")
    jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="chapter")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="chapter")
    review_interventions: Mapped[list["ReviewIntervention"]] = relationship(back_populates="chapter")
    content_revisions: Mapped[list["ContentRevision"]] = relationship(back_populates="chapter", cascade="all, delete-orphan")


class NarrativeBlock(TimestampMixin, Base):
    __tablename__ = "narrative_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    source_revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    last_editor_type: Mapped[str] = mapped_column(String(40), default="agent")

    chapter: Mapped["Chapter"] = relationship(back_populates="narrative_blocks")


class Scene(TimestampMixin, Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    scene_type: Mapped[str] = mapped_column(String(60))
    location: Mapped[str] = mapped_column(String(255))
    time_of_day: Mapped[str] = mapped_column(String(60))
    cast_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    objective: Mapped[str] = mapped_column(Text)
    emotional_tone: Mapped[str] = mapped_column(String(120))
    visual_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    source_revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    last_editor_type: Mapped[str] = mapped_column(String(40), default="agent")

    chapter: Mapped["Chapter"] = relationship(back_populates="scenes")
    dialogue_blocks: Mapped[list["DialogueBlock"]] = relationship(back_populates="scene", cascade="all, delete-orphan")
    illustrations: Mapped[list["IllustrationAsset"]] = relationship(back_populates="scene", cascade="all, delete-orphan")
    jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="scene")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="scene")


class DialogueBlock(TimestampMixin, Base):
    __tablename__ = "dialogue_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(120))
    parenthetical: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    source_revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    last_editor_type: Mapped[str] = mapped_column(String(40), default="agent")

    scene: Mapped["Scene"] = relationship(back_populates="dialogue_blocks")


class ContentRevision(Base):
    __tablename__ = "content_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), index=True)
    story_bible_revision_id: Mapped[int | None] = mapped_column(ForeignKey("story_bible_revisions.id"), nullable=True, index=True)
    source_job_id: Mapped[int | None] = mapped_column(ForeignKey("generation_jobs.id"), nullable=True, index=True)
    revision_kind: Mapped[str] = mapped_column(String(40), default="draft")
    created_by: Mapped[str] = mapped_column(String(40), default="agent")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    chapter: Mapped["Chapter"] = relationship(back_populates="content_revisions")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), nullable=True, index=True)
    scene_id: Mapped[int | None] = mapped_column(ForeignKey("scenes.id"), nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    status_message: Mapped[str] = mapped_column(Text, default="")
    input_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    result_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="jobs")
    project: Mapped["Project"] = relationship(back_populates="jobs")
    chapter: Mapped["Chapter"] = relationship(back_populates="jobs")
    scene: Mapped["Scene"] = relationship(back_populates="jobs")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    review_interventions: Mapped[list["ReviewIntervention"]] = relationship(back_populates="job", foreign_keys="ReviewIntervention.job_id")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("generation_jobs.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), nullable=True, index=True)
    scene_id: Mapped[int | None] = mapped_column(ForeignKey("scenes.id"), nullable=True, index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    step_key: Mapped[str] = mapped_column(String(80))
    agent_name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default="completed")
    adoption_state: Mapped[str] = mapped_column(String(40), default="proposed")
    model_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_summary: Mapped[str] = mapped_column(Text, default="")
    prompt_preview: Mapped[str] = mapped_column(Text, default="")
    output_summary: Mapped[str] = mapped_column(Text, default="")
    stream_text: Mapped[str] = mapped_column(Text, default="")
    public_notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    issues: Mapped[list[str]] = mapped_column(JSON, default=list)
    decision: Mapped[str | None] = mapped_column(String(80), nullable=True)
    usage_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    job: Mapped["GenerationJob"] = relationship(back_populates="agent_runs")
    project: Mapped["Project"] = relationship(back_populates="agent_runs")
    chapter: Mapped["Chapter"] = relationship(back_populates="agent_runs")
    scene: Mapped["Scene"] = relationship(back_populates="agent_runs")
    review_interventions: Mapped[list["ReviewIntervention"]] = relationship(back_populates="reviewer_run")


class ReviewIntervention(Base):
    __tablename__ = "review_interventions"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("generation_jobs.id"), index=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), index=True)
    reviewer_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True, index=True)
    intervention_type: Mapped[str] = mapped_column(String(80))
    reviewer_notes: Mapped[str] = mapped_column(Text)
    suggested_guidance: Mapped[str] = mapped_column(Text, default="")
    user_guidance: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="pending")
    resolution_job_id: Mapped[int | None] = mapped_column(ForeignKey("generation_jobs.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    job: Mapped["GenerationJob"] = relationship(back_populates="review_interventions", foreign_keys=[job_id])
    chapter: Mapped["Chapter"] = relationship(back_populates="review_interventions")
    reviewer_run: Mapped["AgentRun"] = relationship(back_populates="review_interventions")
    resolution_job: Mapped["GenerationJob"] = relationship(foreign_keys=[resolution_job_id])


class IllustrationAsset(TimestampMixin, Base):
    __tablename__ = "illustration_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    scene_id: Mapped[int | None] = mapped_column(ForeignKey("scenes.id"), nullable=True, index=True)
    character_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id"), nullable=True, index=True)
    prompt_text: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(String(500))
    thumbnail_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(40), default="completed")
    candidate_index: Mapped[int] = mapped_column(Integer, default=1)
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped["Project"] = relationship(back_populates="illustrations")
    scene: Mapped["Scene"] = relationship(back_populates="illustrations")
    character: Mapped["Character"] = relationship(back_populates="illustrations")


class ExportPackage(Base):
    __tablename__ = "export_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    formats: Mapped[list[str]] = mapped_column(JSON, default=list)
    files: Mapped[list[dict]] = mapped_column(JSON, default=list)
    selected_chapter_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    selected_illustration_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="exports")


class ProjectSnapshot(Base):
    __tablename__ = "project_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(40), default="user")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    project: Mapped["Project"] = relationship(back_populates="snapshots")
