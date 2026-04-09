from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .exporting import (
    build_docx_bundle,
    build_export_delivery_summary,
    build_pdf_bundle,
)
from .models import (
    AgentRun,
    Chapter,
    Character,
    CharacterReferenceImage,
    CharacterVisualProfile,
    ContentRevision,
    DialogueBlock,
    ExportPackage,
    GenerationJob,
    IllustrationAsset,
    NarrativeBlock,
    Project,
    ProjectSnapshot,
    ReviewIntervention,
    Scene,
    StoryBible,
    StoryBibleRevision,
    User,
)
from .storage import LocalAssetStore


WORKFLOW_STAGE_KEYS = ("queued", "context", "generate", "review", "persist", "complete")
WORKFLOW_STAGE_LABELS = {
    "queued": "排队",
    "context": "载入上下文",
    "generate": "生成",
    "review": "审校",
    "persist": "回填",
    "complete": "完成",
}
WORKFLOW_STEP_STAGE = {
    "queued": "queued",
    "load_project": "context",
    "load_chapter": "context",
    "load_scene": "context",
    "load_export": "context",
    "planner": "generate",
    "writer_draft": "generate",
    "writer_scenes": "generate",
    "visual_prompt": "generate",
    "image_generation": "generate",
    "reviewer_draft": "review",
    "reviewer_scenes": "review",
    "draft_decision_gate": "review",
    "scenes_decision_gate": "review",
    "create_intervention": "review",
    "persist_outline": "persist",
    "persist_outline_repair": "persist",
    "persist_draft": "persist",
    "persist_scenes": "persist",
    "persist_assets": "persist",
    "persist_export": "persist",
    "complete": "complete",
}
WORKFLOW_STEP_LABELS = {
    "queued": "任务入队",
    "load_project": "读取项目上下文",
    "load_chapter": "读取章节上下文",
    "load_scene": "读取场景上下文",
    "load_export": "读取导出上下文",
    "planner": "Planner 规划大纲",
    "writer_draft": "Writer 生成正文",
    "writer_scenes": "Writer 拆分场景",
    "visual_prompt": "Visual Prompt 生成提示词",
    "image_generation": "Image Generation 生成候选图",
    "reviewer_draft": "Reviewer 审校正文",
    "reviewer_scenes": "Reviewer 审校场景",
    "draft_decision_gate": "Reviewer 决策正文去向",
    "scenes_decision_gate": "Reviewer 决策场景去向",
    "create_intervention": "等待作者确认",
    "persist_outline": "回填章节大纲",
    "persist_outline_repair": "回填规划修复",
    "persist_draft": "写入章节成稿",
    "persist_scenes": "写入 Scene 卡",
    "persist_assets": "写入剧照资产",
    "persist_export": "写入导出包",
    "complete": "工作流完成",
}
JOB_ACTIVE_STAGES = {
    "outline": {"queued", "context", "generate", "persist", "complete"},
    "outline_repair": {"queued", "context", "generate", "persist", "complete"},
    "chapter_draft": {"queued", "context", "generate", "review", "persist", "complete"},
    "chapter_draft_retry": {"queued", "context", "generate", "review", "persist", "complete"},
    "chapter_scenes": {"queued", "context", "generate", "review", "persist", "complete"},
    "chapter_scenes_retry": {"queued", "context", "generate", "review", "persist", "complete"},
    "scene_illustrations": {"queued", "context", "generate", "persist", "complete"},
    "export": {"queued", "context", "persist", "complete"},
}


def public_path(file_path: str, root: Path, mount_prefix: str) -> str:
    file_obj = Path(file_path)
    try:
        relative = file_obj.relative_to(root)
    except ValueError:
        return file_path
    return f"{mount_prefix}/{relative.as_posix()}"


def resolve_continuity_notes(review_payload: dict | None, default_note: str) -> list[str]:
    payload = review_payload or {}
    continuity_notes = [str(note).strip() for note in payload.get("continuity_notes", []) if str(note).strip()]
    if continuity_notes:
        return continuity_notes

    issues = [str(issue).strip() for issue in payload.get("issues", []) if str(issue).strip()]
    if issues:
        normalized = []
        for issue in issues:
            if issue.startswith("Reviewer"):
                normalized.append(issue)
            else:
                normalized.append(f"Reviewer：{issue}")
        return normalized

    return [default_note]


def current_story_bible_revision(story_bible: StoryBible | None) -> StoryBibleRevision | None:
    if not story_bible:
        return None
    revisions = sorted(story_bible.revisions, key=lambda item: (item.revision_index, item.id), reverse=True)
    return revisions[0] if revisions else None


def workflow_stage_for_step(step_key: str | None) -> str | None:
    if not step_key:
        return None
    return WORKFLOW_STEP_STAGE.get(step_key)


def workflow_step_label(step_key: str | None) -> str:
    if not step_key:
        return ""
    return WORKFLOW_STEP_LABELS.get(step_key, step_key.replace("_", " ").strip())


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").split())


def _excerpt(value: str | None, limit: int = 180) -> str:
    normalized = _normalize_text(value)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _normalize_rules(value: list[str] | None) -> list[str]:
    return [item.strip() for item in (value or []) if item and item.strip()]


def _changed_status(base_exists: bool, target_exists: bool, is_changed: bool) -> str:
    if base_exists and target_exists:
        return "changed" if is_changed else "unchanged"
    if base_exists:
        return "removed"
    return "added"


def _count_dialogues(scene_payloads: list[dict]) -> int:
    return sum(len(scene.get("dialogue_blocks", [])) for scene in scene_payloads)


def _scene_snapshot_summary(scene_payload: dict | None) -> str:
    if not scene_payload:
        return ""
    cast = " / ".join(scene_payload.get("cast_names", []))
    segments = [
        scene_payload.get("title", ""),
        scene_payload.get("scene_type", ""),
        scene_payload.get("location", ""),
        scene_payload.get("time_of_day", ""),
        cast,
        scene_payload.get("objective", ""),
        scene_payload.get("emotional_tone", ""),
    ]
    dialogue_preview = " ".join(
        f"{item.get('speaker', '').strip()}：{item.get('content', '').strip()}"
        for item in scene_payload.get("dialogue_blocks", [])[:2]
    )
    if dialogue_preview:
        segments.append(dialogue_preview)
    return _excerpt(" | ".join(segment for segment in segments if str(segment).strip()), limit=220)


def build_story_bible_revision_diff(
    base_revision: StoryBibleRevision | None,
    target_revision: StoryBibleRevision,
) -> dict:
    fields = []
    changed_field_count = 0
    field_specs = (
        ("world_notes", "世界观"),
        ("style_notes", "风格"),
        ("writing_rules", "写作禁忌与规则"),
        ("addressing_rules", "称呼规则"),
        ("timeline_rules", "时间线约束"),
    )
    for field, label in field_specs:
        if field == "writing_rules":
            base_value = _normalize_rules(base_revision.writing_rules if base_revision else [])
            target_value = _normalize_rules(target_revision.writing_rules)
            changed = base_value != target_value
            item = {
                "field": field,
                "label": label,
                "changed": changed,
                "base_excerpt": " / ".join(base_value),
                "target_excerpt": " / ".join(target_value),
                "added": [rule for rule in target_value if rule not in base_value],
                "removed": [rule for rule in base_value if rule not in target_value],
            }
        else:
            base_value = getattr(base_revision, field, "") if base_revision else ""
            target_value = getattr(target_revision, field, "")
            changed = _normalize_text(base_value) != _normalize_text(target_value)
            item = {
                "field": field,
                "label": label,
                "changed": changed,
                "base_excerpt": _excerpt(base_value),
                "target_excerpt": _excerpt(target_value),
            }
        if changed:
            changed_field_count += 1
        fields.append(item)

    return {
        "base_revision": serialize_story_bible_revision(base_revision) if base_revision else None,
        "target_revision": serialize_story_bible_revision(target_revision),
        "summary": {
            "changed_field_count": changed_field_count,
            "base_revision_label": f"版本 #{base_revision.revision_index or base_revision.id}" if base_revision else "当前设定",
            "target_revision_label": f"版本 #{target_revision.revision_index or target_revision.id}",
        },
        "fields": fields,
    }


def build_chapter_revision_diff(
    chapter: Chapter,
    *,
    target_revision: ContentRevision,
    base_revision: ContentRevision | None = None,
) -> dict:
    base_payload = dict(base_revision.payload or {}) if base_revision else snapshot_chapter_payload(chapter)
    target_payload = dict(target_revision.payload or {})

    meta_specs = (
        ("title", "章节标题"),
        ("summary", "章节摘要"),
        ("chapter_goal", "章节目标"),
        ("hook", "章节钩子"),
        ("status", "章节状态"),
    )
    meta_changes = []
    for field, label in meta_specs:
        base_value = base_payload.get(field, "")
        target_value = target_payload.get(field, "")
        if _normalize_text(base_value) == _normalize_text(target_value):
            continue
        meta_changes.append(
            {
                "field": field,
                "label": label,
                "status": "changed",
                "base_excerpt": _excerpt(base_value),
                "target_excerpt": _excerpt(target_value),
            }
        )

    base_blocks = list(base_payload.get("narrative_blocks", []))
    target_blocks = list(target_payload.get("narrative_blocks", []))
    narrative_block_changes = []
    narrative_changed = 0
    narrative_added = 0
    narrative_removed = 0
    for index in range(max(len(base_blocks), len(target_blocks))):
        base_block = base_blocks[index] if index < len(base_blocks) else None
        target_block = target_blocks[index] if index < len(target_blocks) else None
        if not base_block and not target_block:
            continue
        base_content = _normalize_text(base_block.get("content")) if base_block else ""
        target_content = _normalize_text(target_block.get("content")) if target_block else ""
        status_name = _changed_status(bool(base_block), bool(target_block), base_content != target_content)
        if status_name == "unchanged":
            continue
        if status_name == "changed":
            narrative_changed += 1
        elif status_name == "added":
            narrative_added += 1
        elif status_name == "removed":
            narrative_removed += 1
        narrative_block_changes.append(
            {
                "order_index": index + 1,
                "status": status_name,
                "base_excerpt": _excerpt(base_block.get("content") if base_block else ""),
                "target_excerpt": _excerpt(target_block.get("content") if target_block else ""),
                "base_is_locked": bool(base_block.get("is_locked")) if base_block else False,
                "target_is_locked": bool(target_block.get("is_locked")) if target_block else False,
                "base_is_user_edited": bool(base_block.get("is_user_edited")) if base_block else False,
                "target_is_user_edited": bool(target_block.get("is_user_edited")) if target_block else False,
            }
        )

    base_scenes = list(base_payload.get("scenes", []))
    target_scenes = list(target_payload.get("scenes", []))
    scene_changes = []
    scene_changed = 0
    scene_added = 0
    scene_removed = 0
    for index in range(max(len(base_scenes), len(target_scenes))):
        base_scene = base_scenes[index] if index < len(base_scenes) else None
        target_scene = target_scenes[index] if index < len(target_scenes) else None
        if not base_scene and not target_scene:
            continue
        base_summary = _scene_snapshot_summary(base_scene)
        target_summary = _scene_snapshot_summary(target_scene)
        status_name = _changed_status(bool(base_scene), bool(target_scene), base_summary != target_summary)
        if status_name == "unchanged":
            continue
        if status_name == "changed":
            scene_changed += 1
        elif status_name == "added":
            scene_added += 1
        elif status_name == "removed":
            scene_removed += 1
        base_dialogues = base_scene.get("dialogue_blocks", []) if base_scene else []
        target_dialogues = target_scene.get("dialogue_blocks", []) if target_scene else []
        scene_changes.append(
            {
                "order_index": index + 1,
                "status": status_name,
                "base_title": base_scene.get("title", "") if base_scene else "",
                "target_title": target_scene.get("title", "") if target_scene else "",
                "base_excerpt": base_summary,
                "target_excerpt": target_summary,
                "dialogue_overview": {
                    "base_count": len(base_dialogues),
                    "target_count": len(target_dialogues),
                    "delta": abs(len(base_dialogues) - len(target_dialogues)),
                },
            }
        )

    return {
        "base": {
            "kind": "revision" if base_revision else "live",
            "revision_id": base_revision.id if base_revision else None,
            "label": f"Revision #{base_revision.id}" if base_revision else "当前章节",
        },
        "target": {
            "kind": "revision",
            "revision_id": target_revision.id,
            "label": f"Revision #{target_revision.id}",
        },
        "overview": {
            "meta_change_count": len(meta_changes),
            "narrative_blocks": {
                "base_count": len(base_blocks),
                "target_count": len(target_blocks),
                "changed": narrative_changed,
                "added": narrative_added,
                "removed": narrative_removed,
            },
            "scenes": {
                "base_count": len(base_scenes),
                "target_count": len(target_scenes),
                "changed": scene_changed,
                "added": scene_added,
                "removed": scene_removed,
            },
            "scene_count_delta": abs(len(base_scenes) - len(target_scenes)),
            "dialogue_count_delta": abs(_count_dialogues(base_scenes) - _count_dialogues(target_scenes)),
        },
        "meta_changes": meta_changes,
        "narrative_block_changes": narrative_block_changes,
        "scene_changes": scene_changes,
    }


def infer_job_live_state(job: GenerationJob) -> dict:
    result_payload = dict(job.result_payload or {})
    live_state = dict(result_payload.get("live_state") or {})
    active_stages = JOB_ACTIVE_STAGES.get(job.job_type, {"queued", "context", "generate", "persist", "complete"})

    current_step = str(live_state.get("current_step") or "").strip()
    current_stage = str(live_state.get("current_stage") or "").strip()
    current_step_label = str(live_state.get("current_step_label") or "").strip()

    sorted_runs = sorted(job.agent_runs, key=lambda item: item.sequence)
    processing_run = next((run for run in reversed(sorted_runs) if run.status == "processing"), None)
    latest_run = sorted_runs[-1] if sorted_runs else None

    if not current_step and processing_run is not None:
        current_step = processing_run.step_key
    if not current_step and job.status == "queued":
        current_step = "queued"
    if not current_step and job.status == "completed":
        current_step = "complete"
    if not current_step and job.status == "awaiting_user":
        current_step = "create_intervention"
    if not current_step and latest_run is not None:
        current_step = latest_run.step_key

    if not current_stage and current_step:
        current_stage = workflow_stage_for_step(current_step) or ""
    if not current_stage:
        current_stage = "queued" if job.status == "queued" else "context"
    if not current_step_label:
        current_step_label = workflow_step_label(current_step)

    latest_agent_name = str(live_state.get("latest_agent_name") or "").strip()
    latest_agent_summary = str(live_state.get("latest_agent_summary") or "").strip()
    if not latest_agent_name and processing_run is not None:
        latest_agent_name = processing_run.agent_name
    if not latest_agent_summary and processing_run is not None:
        latest_agent_summary = processing_run.output_summary or processing_run.prompt_preview or job.status_message or ""
    if not latest_agent_summary and latest_run is not None:
        latest_agent_summary = latest_run.output_summary or latest_run.prompt_preview or job.status_message or ""
    if not latest_agent_summary:
        latest_agent_summary = job.status_message or ""

    stage_history = []
    if job.status != "queued":
        stage_history.append({"stage": "queued", "label": WORKFLOW_STAGE_LABELS["queued"], "status": "completed"})

    if "context" in active_stages and job.status != "queued":
        context_status = "completed"
        if current_stage == "context" and job.status == "processing":
            context_status = "processing"
        elif current_stage == "context" and job.status == "failed":
            context_status = "failed"
        stage_history.append(
            {
                "stage": "context",
                "label": WORKFLOW_STAGE_LABELS["context"],
                "status": context_status,
            }
        )

    generate_runs = [run for run in sorted_runs if workflow_stage_for_step(run.step_key) == "generate"]
    if "generate" in active_stages:
        if generate_runs:
            generate_status = "processing" if any(run.status == "processing" for run in generate_runs) else "completed"
            if job.status == "failed" and current_stage == "generate":
                generate_status = "failed"
            stage_history.append(
                {
                    "stage": "generate",
                    "label": WORKFLOW_STAGE_LABELS["generate"],
                    "status": generate_status,
                }
            )
        elif current_stage == "generate":
            stage_history.append(
                {
                    "stage": "generate",
                    "label": WORKFLOW_STAGE_LABELS["generate"],
                    "status": "failed" if job.status == "failed" else "processing",
                }
            )

    review_runs = [run for run in sorted_runs if workflow_stage_for_step(run.step_key) == "review"]
    if "review" in active_stages:
        if review_runs or current_stage == "review":
            review_status = "processing"
            if job.status == "awaiting_user":
                review_status = "awaiting_user"
            elif any(run.status == "processing" for run in review_runs):
                review_status = "processing"
            elif job.status == "failed" and current_stage == "review":
                review_status = "failed"
            elif review_runs:
                review_status = "completed"
            stage_history.append(
                {
                    "stage": "review",
                    "label": WORKFLOW_STAGE_LABELS["review"],
                    "status": review_status,
                }
            )

    persist_active = "persist" in active_stages
    if persist_active:
        persist_status = None
        if job.status == "completed":
            persist_status = "completed"
        elif job.status == "failed" and current_stage == "persist":
            persist_status = "failed"
        elif current_stage == "persist":
            persist_status = "processing"
        elif any(keyword in (job.status_message or "") for keyword in ("回填", "写入", "导出包")):
            persist_status = "processing"
        if persist_status:
            stage_history.append(
                {
                    "stage": "persist",
                    "label": WORKFLOW_STAGE_LABELS["persist"],
                    "status": persist_status,
                }
            )

    if job.status == "completed":
        current_stage = "complete"
        current_step = "complete"
        current_step_label = workflow_step_label("complete")
        stage_history.append({"stage": "complete", "label": WORKFLOW_STAGE_LABELS["complete"], "status": "completed"})

    stage_lookup = {item["stage"]: item for item in stage_history}
    stages = []
    for stage_key in WORKFLOW_STAGE_KEYS:
        if stage_key not in active_stages and stage_key not in {"queued", "complete"}:
            state = "skipped"
        elif stage_key in stage_lookup:
            state = stage_lookup[stage_key]["status"]
        elif stage_key == current_stage and job.status == "awaiting_user":
            state = "awaiting_user"
        elif stage_key == current_stage and job.status == "failed":
            state = "failed"
        elif stage_key == current_stage and job.status == "processing":
            state = "processing"
        else:
            state = "pending"
        stages.append({"stage": stage_key, "label": WORKFLOW_STAGE_LABELS[stage_key], "status": state})

    return {
        "current_stage": current_stage,
        "current_step": current_step,
        "current_step_label": current_step_label,
        "latest_agent_name": latest_agent_name,
        "latest_agent_summary": latest_agent_summary,
        "stage_history": stage_history,
        "stages": stages,
    }


def serialize_story_bible_revision(revision: StoryBibleRevision) -> dict:
    return {
        "id": revision.id,
        "project_id": revision.project_id,
        "story_bible_id": revision.story_bible_id,
        "revision_index": revision.revision_index,
        "world_notes": revision.world_notes,
        "style_notes": revision.style_notes,
        "writing_rules": revision.writing_rules,
        "addressing_rules": revision.addressing_rules,
        "timeline_rules": revision.timeline_rules,
        "created_by": revision.created_by,
        "created_by_user_id": revision.created_by_user_id,
        "source_job_id": revision.source_job_id,
        "created_at": revision.created_at.isoformat(),
    }


def serialize_story_bible(story_bible: StoryBible | None) -> dict:
    current_revision = current_story_bible_revision(story_bible)
    return {
        "world_notes": story_bible.world_notes if story_bible else "",
        "style_notes": story_bible.style_notes if story_bible else "",
        "writing_rules": story_bible.writing_rules if story_bible else [],
        "addressing_rules": story_bible.addressing_rules if story_bible else "",
        "timeline_rules": story_bible.timeline_rules if story_bible else "",
        "current_revision": serialize_story_bible_revision(current_revision) if current_revision else None,
        "revision_count": len(story_bible.revisions) if story_bible else 0,
    }


def serialize_narrative_block(block: NarrativeBlock) -> dict:
    return {
        "id": block.id,
        "order_index": block.order_index,
        "content": block.content,
        "is_locked": block.is_locked,
        "is_user_edited": block.is_user_edited,
        "source_revision_id": block.source_revision_id,
        "last_editor_type": block.last_editor_type,
    }


def serialize_dialogue_block(block: DialogueBlock) -> dict:
    return {
        "id": block.id,
        "order_index": block.order_index,
        "speaker": block.speaker,
        "parenthetical": block.parenthetical,
        "content": block.content,
        "is_locked": block.is_locked,
        "is_user_edited": block.is_user_edited,
        "source_revision_id": block.source_revision_id,
        "last_editor_type": block.last_editor_type,
    }


def snapshot_chapter_payload(chapter: Chapter) -> dict:
    return {
        "id": chapter.id,
        "order_index": chapter.order_index,
        "title": chapter.title,
        "summary": chapter.summary,
        "chapter_goal": chapter.chapter_goal,
        "hook": chapter.hook,
        "status": chapter.status,
        "is_locked": chapter.is_locked,
        "source_story_bible_revision_id": chapter.source_story_bible_revision_id,
        "continuity_notes": chapter.continuity_notes,
        "narrative_blocks": [
            {
                "order_index": block.order_index,
                "content": block.content,
                "is_locked": block.is_locked,
                "is_user_edited": block.is_user_edited,
                "source_revision_id": block.source_revision_id,
                "last_editor_type": block.last_editor_type,
            }
            for block in sorted(chapter.narrative_blocks, key=lambda item: item.order_index)
        ],
        "scenes": [
            {
                "order_index": scene.order_index,
                "title": scene.title,
                "scene_type": scene.scene_type,
                "location": scene.location,
                "time_of_day": scene.time_of_day,
                "cast_names": scene.cast_names,
                "objective": scene.objective,
                "emotional_tone": scene.emotional_tone,
                "visual_prompt": scene.visual_prompt,
                "is_locked": scene.is_locked,
                "is_user_edited": scene.is_user_edited,
                "source_revision_id": scene.source_revision_id,
                "last_editor_type": scene.last_editor_type,
                "dialogue_blocks": [
                    {
                        "order_index": block.order_index,
                        "speaker": block.speaker,
                        "parenthetical": block.parenthetical,
                        "content": block.content,
                        "is_locked": block.is_locked,
                        "is_user_edited": block.is_user_edited,
                        "source_revision_id": block.source_revision_id,
                        "last_editor_type": block.last_editor_type,
                    }
                    for block in sorted(scene.dialogue_blocks, key=lambda item: item.order_index)
                ],
            }
            for scene in sorted(chapter.scenes, key=lambda item: item.order_index)
        ],
    }


def create_story_bible_revision(
    project: Project,
    db: Session,
    *,
    created_by: str,
    created_by_user_id: int | None = None,
    source_job_id: int | None = None,
) -> StoryBibleRevision | None:
    if not project.story_bible:
        return None
    previous_revision = current_story_bible_revision(project.story_bible)
    revision = StoryBibleRevision(
        project=project,
        story_bible=project.story_bible,
        revision_index=(previous_revision.revision_index + 1) if previous_revision else 1,
        world_notes=project.story_bible.world_notes,
        style_notes=project.story_bible.style_notes,
        writing_rules=project.story_bible.writing_rules,
        addressing_rules=project.story_bible.addressing_rules,
        timeline_rules=project.story_bible.timeline_rules,
        created_by=created_by,
        created_by_user_id=created_by_user_id,
        source_job_id=source_job_id,
    )
    db.add(revision)
    db.flush()
    return revision


def create_content_revision(
    chapter: Chapter,
    db: Session,
    *,
    revision_kind: str,
    created_by: str,
    summary: str = "",
    created_by_user_id: int | None = None,
    source_job_id: int | None = None,
    story_bible_revision_id: int | None = None,
) -> ContentRevision:
    revision = ContentRevision(
        project_id=chapter.project_id,
        chapter=chapter,
        story_bible_revision_id=story_bible_revision_id or chapter.source_story_bible_revision_id,
        source_job_id=source_job_id,
        revision_kind=revision_kind,
        created_by=created_by,
        created_by_user_id=created_by_user_id,
        summary=summary,
        payload={},
    )
    db.add(revision)
    db.flush()
    revision.payload = snapshot_chapter_payload(chapter)
    db.flush()
    return revision


def serialize_content_revision(revision: ContentRevision) -> dict:
    payload = revision.payload or {}
    return {
        "id": revision.id,
        "project_id": revision.project_id,
        "chapter_id": revision.chapter_id,
        "story_bible_revision_id": revision.story_bible_revision_id,
        "source_job_id": revision.source_job_id,
        "revision_kind": revision.revision_kind,
        "created_by": revision.created_by,
        "created_by_user_id": revision.created_by_user_id,
        "summary": revision.summary,
        "created_at": revision.created_at.isoformat(),
        "narrative_block_count": len(payload.get("narrative_blocks", [])),
        "scene_count": len(payload.get("scenes", [])),
    }


def restore_chapter_from_payload(chapter: Chapter, payload: dict, db: Session) -> Chapter:
    chapter.title = payload.get("title", chapter.title)
    chapter.summary = payload.get("summary", chapter.summary)
    chapter.chapter_goal = payload.get("chapter_goal", chapter.chapter_goal)
    chapter.hook = payload.get("hook", chapter.hook)
    chapter.status = payload.get("status", chapter.status)
    chapter.is_locked = bool(payload.get("is_locked", chapter.is_locked))
    chapter.source_story_bible_revision_id = payload.get(
        "source_story_bible_revision_id",
        chapter.source_story_bible_revision_id,
    )
    chapter.continuity_notes = payload.get("continuity_notes", chapter.continuity_notes)

    narrative_payloads = list(payload.get("narrative_blocks", []))
    existing_blocks = sorted(chapter.narrative_blocks, key=lambda item: item.order_index)
    for index, block_payload in enumerate(narrative_payloads, start=1):
        block = existing_blocks[index - 1] if index - 1 < len(existing_blocks) else NarrativeBlock(chapter=chapter)
        if block.id is None:
            db.add(block)
        block.order_index = index
        block.content = block_payload.get("content", "")
        block.is_locked = bool(block_payload.get("is_locked", False))
        block.is_user_edited = bool(block_payload.get("is_user_edited", False))
        block.source_revision_id = block_payload.get("source_revision_id")
        block.last_editor_type = block_payload.get("last_editor_type", "agent")
    for block in existing_blocks[len(narrative_payloads) :]:
        db.delete(block)
    db.flush()

    existing_scenes = sorted(chapter.scenes, key=lambda item: item.order_index)
    scene_payloads = list(payload.get("scenes", []))
    for index, scene_payload in enumerate(scene_payloads, start=1):
        scene = existing_scenes[index - 1] if index - 1 < len(existing_scenes) else Scene(chapter=chapter)
        if scene.id is None:
            db.add(scene)
        scene.order_index = index
        scene.title = scene_payload.get("title", "")
        scene.scene_type = scene_payload.get("scene_type", "INT")
        scene.location = scene_payload.get("location", "")
        scene.time_of_day = scene_payload.get("time_of_day", "DAY")
        scene.cast_names = scene_payload.get("cast_names", [])
        scene.objective = scene_payload.get("objective", "")
        scene.emotional_tone = scene_payload.get("emotional_tone", "")
        scene.visual_prompt = scene_payload.get("visual_prompt")
        scene.is_locked = bool(scene_payload.get("is_locked", False))
        scene.is_user_edited = bool(scene_payload.get("is_user_edited", False))
        scene.source_revision_id = scene_payload.get("source_revision_id")
        scene.last_editor_type = scene_payload.get("last_editor_type", "agent")
        db.flush()

        dialogue_payloads = list(scene_payload.get("dialogue_blocks", []))
        existing_dialogues = sorted(scene.dialogue_blocks, key=lambda item: item.order_index)
        for dialogue_index, dialogue_payload in enumerate(dialogue_payloads, start=1):
            dialogue = (
                existing_dialogues[dialogue_index - 1]
                if dialogue_index - 1 < len(existing_dialogues)
                else DialogueBlock(scene=scene)
            )
            if dialogue.id is None:
                db.add(dialogue)
            dialogue.order_index = dialogue_index
            dialogue.speaker = dialogue_payload.get("speaker", "")
            dialogue.parenthetical = dialogue_payload.get("parenthetical", "")
            dialogue.content = dialogue_payload.get("content", "")
            dialogue.is_locked = bool(dialogue_payload.get("is_locked", False))
            dialogue.is_user_edited = bool(dialogue_payload.get("is_user_edited", False))
            dialogue.source_revision_id = dialogue_payload.get("source_revision_id")
            dialogue.last_editor_type = dialogue_payload.get("last_editor_type", "agent")
        for dialogue in existing_dialogues[len(dialogue_payloads) :]:
            db.delete(dialogue)

    for scene in existing_scenes[len(scene_payloads) :]:
        db.delete(scene)
    db.flush()
    return chapter


def serialize_project_snapshot(snapshot: ProjectSnapshot) -> dict:
    payload = snapshot.payload or {}
    return {
        "id": snapshot.id,
        "project_id": snapshot.project_id,
        "label": snapshot.label,
        "created_by": snapshot.created_by,
        "created_by_user_id": snapshot.created_by_user_id,
        "chapter_count": len(payload.get("chapters", [])),
        "character_count": len(payload.get("characters", [])),
        "created_at": snapshot.created_at.isoformat(),
    }


def snapshot_project_payload(project: Project, storage_root: Path, export_root: Path) -> dict:
    return serialize_project(project, storage_root, export_root, detailed=True)


def serialize_agent_run(agent_run: AgentRun) -> dict:
    return {
        "id": agent_run.id,
        "sequence": agent_run.sequence,
        "step_key": agent_run.step_key,
        "agent_name": agent_run.agent_name,
        "status": agent_run.status,
        "adoption_state": agent_run.adoption_state,
        "model_id": agent_run.model_id,
        "input_summary": agent_run.input_summary,
        "prompt_preview": agent_run.prompt_preview,
        "output_summary": agent_run.output_summary,
        "stream_text": agent_run.stream_text,
        "public_notes": agent_run.public_notes,
        "issues": agent_run.issues,
        "decision": agent_run.decision,
        "usage_payload": agent_run.usage_payload,
        "error_message": agent_run.error_message,
        "started_at": agent_run.started_at.isoformat(),
        "completed_at": agent_run.completed_at.isoformat() if agent_run.completed_at else None,
    }


def serialize_review_intervention(intervention: ReviewIntervention) -> dict:
    return {
        "id": intervention.id,
        "job_id": intervention.job_id,
        "chapter_id": intervention.chapter_id,
        "reviewer_run_id": intervention.reviewer_run_id,
        "intervention_type": intervention.intervention_type,
        "reviewer_notes": intervention.reviewer_notes,
        "suggested_guidance": intervention.suggested_guidance,
        "user_guidance": intervention.user_guidance,
        "status": intervention.status,
        "resolution_job_id": intervention.resolution_job_id,
        "created_at": intervention.created_at.isoformat(),
        "resolved_at": intervention.resolved_at.isoformat() if intervention.resolved_at else None,
    }


def serialize_job(job: GenerationJob, detailed: bool = False) -> dict:
    result_payload = dict(job.result_payload or {})
    result_payload["live_state"] = infer_job_live_state(job)
    payload = {
        "id": job.id,
        "job_type": job.job_type,
        "project_id": job.project_id,
        "chapter_id": job.chapter_id,
        "scene_id": job.scene_id,
        "status": job.status,
        "progress": job.progress,
        "status_message": job.status_message,
        "error_message": job.error_message,
        "result": result_payload,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
    if detailed:
        payload["agent_runs"] = [serialize_agent_run(item) for item in sorted(job.agent_runs, key=lambda run: run.sequence)]
        payload["pending_interventions"] = [
            serialize_review_intervention(item)
            for item in sorted(job.review_interventions, key=lambda intervention: intervention.id)
            if item.status == "pending"
        ]
    return payload


def serialize_visual_profile(profile: CharacterVisualProfile | None) -> dict | None:
    if not profile:
        return None
    return {
        "visual_anchor": profile.visual_anchor,
        "signature_palette": profile.signature_palette,
        "silhouette_notes": profile.silhouette_notes,
        "wardrobe_notes": profile.wardrobe_notes,
        "atmosphere_notes": profile.atmosphere_notes,
    }


def serialize_reference_image(reference_image: CharacterReferenceImage, storage_root: Path) -> dict:
    return {
        "id": reference_image.id,
        "filename": reference_image.filename,
        "path": reference_image.path,
        "url": public_path(reference_image.path, storage_root, "/media/storage"),
    }


def serialize_illustration(asset: IllustrationAsset, storage_root: Path) -> dict:
    return {
        "id": asset.id,
        "prompt_text": asset.prompt_text,
        "status": asset.status,
        "candidate_index": asset.candidate_index,
        "is_canonical": asset.is_canonical,
        "path": asset.file_path,
        "url": public_path(asset.file_path, storage_root, "/media/storage"),
        "thumbnail_url": public_path(asset.thumbnail_path, storage_root, "/media/storage"),
    }


def serialize_character(character: Character, storage_root: Path) -> dict:
    return {
        "id": character.id,
        "name": character.name,
        "role": character.role,
        "personality": character.personality,
        "goal": character.goal,
        "speech_style": character.speech_style,
        "appearance": character.appearance,
        "relationships": character.relationships,
        "signature_line": character.signature_line,
        "linked_project_ids": [project.id for project in character.projects],
        "reference_images": [serialize_reference_image(item, storage_root) for item in character.reference_images],
        "visual_profile": serialize_visual_profile(character.visual_profile),
    }


def serialize_scene(scene: Scene, storage_root: Path) -> dict:
    return {
        "id": scene.id,
        "order_index": scene.order_index,
        "title": scene.title,
        "scene_type": scene.scene_type,
        "location": scene.location,
        "time_of_day": scene.time_of_day,
        "cast_names": scene.cast_names,
        "objective": scene.objective,
        "emotional_tone": scene.emotional_tone,
        "visual_prompt": scene.visual_prompt,
        "is_locked": scene.is_locked,
        "is_user_edited": scene.is_user_edited,
        "source_revision_id": scene.source_revision_id,
        "last_editor_type": scene.last_editor_type,
        "dialogue_blocks": [serialize_dialogue_block(block) for block in sorted(scene.dialogue_blocks, key=lambda item: item.order_index)],
        "illustrations": [serialize_illustration(asset, storage_root) for asset in sorted(scene.illustrations, key=lambda item: item.candidate_index)],
    }


def serialize_chapter(chapter: Chapter, storage_root: Path) -> dict:
    latest_revision = sorted(chapter.content_revisions, key=lambda item: item.id, reverse=True)[0] if chapter.content_revisions else None
    return {
        "id": chapter.id,
        "order_index": chapter.order_index,
        "title": chapter.title,
        "summary": chapter.summary,
        "chapter_goal": chapter.chapter_goal,
        "hook": chapter.hook,
        "status": chapter.status,
        "is_locked": chapter.is_locked,
        "source_story_bible_revision_id": chapter.source_story_bible_revision_id,
        "continuity_notes": chapter.continuity_notes,
        "latest_revision": serialize_content_revision(latest_revision) if latest_revision else None,
        "pending_interventions": [
            serialize_review_intervention(item)
            for item in sorted(chapter.review_interventions, key=lambda intervention: intervention.id)
            if item.status == "pending"
        ],
        "narrative_blocks": [serialize_narrative_block(block) for block in sorted(chapter.narrative_blocks, key=lambda item: item.order_index)],
        "scenes": [serialize_scene(scene, storage_root) for scene in sorted(chapter.scenes, key=lambda item: item.order_index)],
    }


def serialize_project(project: Project, storage_root: Path, export_root: Path, detailed: bool = False) -> dict:
    payload = {
        "id": project.id,
        "title": project.title,
        "genre": project.genre,
        "tone": project.tone,
        "era": project.era,
        "target_chapter_count": project.target_chapter_count,
        "target_length": project.target_length,
        "logline": project.logline,
        "status": project.status,
        "cover_image_path": project.cover_image_path,
        "cover_image_url": public_path(project.cover_image_path, storage_root, "/media/storage") if project.cover_image_path else None,
    }
    if not detailed:
        return payload

    payload.update(
        {
            "story_bible": serialize_story_bible(project.story_bible),
            "characters": [serialize_character(character, storage_root) for character in project.characters],
            "chapters": [serialize_chapter(chapter, storage_root) for chapter in sorted(project.chapters, key=lambda item: item.order_index)],
            "jobs": [serialize_job(job) for job in sorted(project.jobs, key=lambda item: item.id, reverse=True)[:10]],
            "exports": [serialize_export(item, export_root) for item in sorted(project.exports, key=lambda export_item: export_item.id, reverse=True)],
            "snapshots": [serialize_project_snapshot(item) for item in sorted(project.snapshots, key=lambda snapshot: snapshot.id, reverse=True)[:5]],
        }
    )
    return payload


def serialize_export(export_package: ExportPackage, export_root: Path) -> dict:
    serialized_files = []
    for item in export_package.files:
        path = item.get("path")
        serialized_files.append(
            {
                **item,
                "filename": Path(path).name if path else "",
                "url": public_path(path, export_root, "/media/exports"),
            }
        )

    return {
        "id": export_package.id,
        "status": export_package.status,
        "formats": export_package.formats,
        "files": serialized_files,
        "delivery_summary": build_export_delivery_summary(export_package.project, export_package, serialized_files),
        "created_at": export_package.created_at.isoformat(),
        "completed_at": export_package.completed_at.isoformat() if export_package.completed_at else None,
    }


def require_project(db: Session, user: User, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def require_chapter(db: Session, user: User, chapter_id: int) -> Chapter:
    chapter = (
        db.query(Chapter)
        .join(Project, Chapter.project_id == Project.id)
        .filter(Chapter.id == chapter_id, Project.owner_id == user.id)
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")
    return chapter


def require_narrative_block(db: Session, user: User, block_id: int) -> NarrativeBlock:
    block = (
        db.query(NarrativeBlock)
        .join(Chapter, NarrativeBlock.chapter_id == Chapter.id)
        .join(Project, Chapter.project_id == Project.id)
        .filter(NarrativeBlock.id == block_id, Project.owner_id == user.id)
        .first()
    )
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Narrative block not found")
    return block


def require_dialogue_block(db: Session, user: User, block_id: int) -> DialogueBlock:
    block = (
        db.query(DialogueBlock)
        .join(Scene, DialogueBlock.scene_id == Scene.id)
        .join(Chapter, Scene.chapter_id == Chapter.id)
        .join(Project, Chapter.project_id == Project.id)
        .filter(DialogueBlock.id == block_id, Project.owner_id == user.id)
        .first()
    )
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dialogue block not found")
    return block


def require_character(db: Session, user: User, character_id: int) -> Character:
    character = db.query(Character).filter(Character.id == character_id, Character.owner_id == user.id).first()
    if not character:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    return character


def require_scene(db: Session, user: User, scene_id: int) -> Scene:
    scene = (
        db.query(Scene)
        .join(Chapter, Scene.chapter_id == Chapter.id)
        .join(Project, Chapter.project_id == Project.id)
        .filter(Scene.id == scene_id, Project.owner_id == user.id)
        .first()
    )
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    return scene


def require_job(db: Session, user: User, job_id: int) -> GenerationJob:
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id, GenerationJob.user_id == user.id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def require_review_intervention(db: Session, user: User, intervention_id: int) -> ReviewIntervention:
    intervention = (
        db.query(ReviewIntervention)
        .join(GenerationJob, ReviewIntervention.job_id == GenerationJob.id)
        .filter(ReviewIntervention.id == intervention_id, GenerationJob.user_id == user.id)
        .first()
    )
    if not intervention:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review intervention not found")
    return intervention


def require_illustration(db: Session, user: User, illustration_id: int) -> IllustrationAsset:
    illustration = (
        db.query(IllustrationAsset)
        .join(Project, IllustrationAsset.project_id == Project.id)
        .filter(IllustrationAsset.id == illustration_id, Project.owner_id == user.id)
        .first()
    )
    if not illustration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Illustration not found")
    return illustration


def require_export(db: Session, user: User, export_id: int) -> ExportPackage:
    export_package = (
        db.query(ExportPackage)
        .join(Project, ExportPackage.project_id == Project.id)
        .filter(ExportPackage.id == export_id, Project.owner_id == user.id)
        .first()
    )
    if not export_package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    return export_package


def require_content_revision(db: Session, user: User, chapter_id: int, revision_id: int) -> ContentRevision:
    revision = (
        db.query(ContentRevision)
        .join(Chapter, ContentRevision.chapter_id == Chapter.id)
        .join(Project, Chapter.project_id == Project.id)
        .filter(ContentRevision.id == revision_id, ContentRevision.chapter_id == chapter_id, Project.owner_id == user.id)
        .first()
    )
    if not revision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content revision not found")
    return revision


def require_story_bible_revision(db: Session, user: User, project_id: int, revision_id: int) -> StoryBibleRevision:
    revision = (
        db.query(StoryBibleRevision)
        .join(Project, StoryBibleRevision.project_id == Project.id)
        .filter(StoryBibleRevision.id == revision_id, StoryBibleRevision.project_id == project_id, Project.owner_id == user.id)
        .first()
    )
    if not revision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story Bible revision not found")
    return revision


def delete_illustration_files(illustration: IllustrationAsset, asset_store: LocalAssetStore):
    asset_store.remove_file(illustration.file_path, root=asset_store.storage_dir)
    asset_store.remove_file(illustration.thumbnail_path, root=asset_store.storage_dir)


def delete_character_files(character: Character, asset_store: LocalAssetStore):
    for reference_image in character.reference_images:
        asset_store.remove_file(reference_image.path, root=asset_store.storage_dir)


def delete_export_files(export_package: ExportPackage, asset_store: LocalAssetStore):
    for file_info in export_package.files:
        asset_store.remove_file(file_info.get("path"), root=asset_store.export_dir)


def delete_project_files(project: Project, asset_store: LocalAssetStore):
    asset_store.remove_file(project.cover_image_path, root=asset_store.storage_dir)
    for illustration in project.illustrations:
        delete_illustration_files(illustration, asset_store)
    for export_package in project.exports:
        delete_export_files(export_package, asset_store)


def bootstrap_project(project: Project, db: Session, asset_store: LocalAssetStore):
    if not project.story_bible:
        db.add(
            StoryBible(
                project=project,
                world_notes=f"《{project.title}》发生在{project.era}，整体类型为{project.genre}。",
                style_notes=project.tone,
                writing_rules=["以人物推动情节", "保持章节结尾具有牵引力", "优先使用场景化描写"],
                addressing_rules="保持主要角色称呼稳定，除非剧情明确触发关系变化。",
                timeline_rules="默认按连续时间推进，不要无提示跳时。",
            )
        )

    if not project.cover_image_path:
        image_path, _ = asset_store.create_story_image(
            category="covers",
            basename=f"project_{project.id}",
            title=project.title,
            subtitle=project.logline,
            tone=project.tone,
        )
        project.cover_image_path = image_path


def create_character_visual_profile(character: Character, profile_data: dict, db: Session):
    character.signature_line = profile_data["signature_line"]
    visual_profile = character.visual_profile
    if not visual_profile:
        visual_profile = CharacterVisualProfile(character=character)
        db.add(visual_profile)

    visual_profile.visual_anchor = profile_data["visual_anchor"]
    visual_profile.signature_palette = profile_data["signature_palette"]
    visual_profile.silhouette_notes = profile_data["silhouette_notes"]
    visual_profile.wardrobe_notes = profile_data["wardrobe_notes"]
    visual_profile.atmosphere_notes = profile_data["atmosphere_notes"]


def export_project_bundle(project: Project, export_package: ExportPackage, asset_store: LocalAssetStore):
    project_export_dir = asset_store.export_dir / f"project_{project.id}"
    project_export_dir.mkdir(parents=True, exist_ok=True)

    files = []
    if "pdf" in export_package.formats:
        pdf_path = project_export_dir / f"{project.title}_bundle.pdf"
        pdf_info = build_pdf_bundle(
            project,
            pdf_path,
            selected_chapter_ids=export_package.selected_chapter_ids,
            selected_illustration_ids=export_package.selected_illustration_ids,
        )
        files.append({"format": "pdf", **pdf_info})

    if "docx" in export_package.formats:
        docx_path = project_export_dir / f"{project.title}_bundle.docx"
        docx_info = build_docx_bundle(
            project,
            docx_path,
            selected_chapter_ids=export_package.selected_chapter_ids,
            selected_illustration_ids=export_package.selected_illustration_ids,
        )
        files.append({"format": "docx", **docx_info})

    export_package.files = files


def build_pdf(project: Project, target_path: Path):
    build_pdf_bundle(project, target_path)


def build_docx(project: Project, target_path: Path):
    build_docx_bundle(project, target_path)
