from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    pen_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class ProjectCreateRequest(BaseModel):
    title: str
    genre: str
    tone: str
    era: str
    target_chapter_count: int = Field(default=6, ge=1, le=24)
    target_length: str
    logline: str


class OutlineGenerateRequest(BaseModel):
    chapter_count: int | None = Field(default=None, ge=1, le=24)


class ChapterGenerationRequest(BaseModel):
    pass


class StoryBiblePatchRequest(BaseModel):
    world_notes: str | None = None
    style_notes: str | None = None
    writing_rules: list[str] | None = None
    addressing_rules: str | None = None
    timeline_rules: str | None = None


class NarrativeBlockPatchRequest(BaseModel):
    content: str | None = None
    is_locked: bool | None = None


class DialogueBlockPatchRequest(BaseModel):
    speaker: str | None = None
    parenthetical: str | None = None
    content: str | None = None
    is_locked: bool | None = None


class ScenePatchRequest(BaseModel):
    title: str | None = None
    scene_type: str | None = None
    location: str | None = None
    time_of_day: str | None = None
    cast_names: list[str] | None = None
    objective: str | None = None
    emotional_tone: str | None = None
    visual_prompt: str | None = None
    is_locked: bool | None = None


class ProjectDuplicateRequest(BaseModel):
    title: str | None = None


class ProjectSnapshotRequest(BaseModel):
    label: str = ""


class SceneIllustrationRequest(BaseModel):
    candidate_count: int = Field(default=2, ge=1, le=4)
    extra_guidance: str = ""


class ExportRequest(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["pdf", "docx"])


class EmptyRequest(BaseModel):
    pass


class ChapterLockRequest(BaseModel):
    locked: bool


class ReviewInterventionRetryRequest(BaseModel):
    extra_guidance: str = ""


class CharacterAttachRequest(BaseModel):
    character_id: int
