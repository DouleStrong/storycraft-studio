from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable

from sqlalchemy.orm import Session, selectinload

from .langfuse_tracing import NoopLangfuseWorkflowTrace
from .models import (
    AgentRun,
    Chapter,
    Character,
    DialogueBlock,
    ExportPackage,
    GenerationJob,
    IllustrationAsset,
    NarrativeBlock,
    Project,
    ReviewIntervention,
    Scene,
)
from .providers import StructuredAgentResponse, StoryAgentPipeline
from .services import (
    create_content_revision,
    create_story_bible_revision,
    current_story_bible_revision,
    export_project_bundle,
    resolve_continuity_notes,
    snapshot_chapter_payload,
)
from .storage import LocalAssetStore


SEVERITY_RANK = {
    "minor": 0,
    "moderate": 1,
    "major": 2,
    "critical": 3,
}


def _compact_trace_metadata(**kwargs) -> dict:
    return {key: value for key, value in kwargs.items() if value not in (None, "", [], {}, ())}


@dataclass(slots=True)
class WorkflowNode:
    key: str
    handler: Callable[["WorkflowExecution"], str | None]


@dataclass(slots=True)
class WorkflowGraph:
    key: str
    start_at: str
    nodes: dict[str, WorkflowNode]


@dataclass(slots=True)
class WorkflowExecution:
    db: Session
    job: GenerationJob
    asset_store: LocalAssetStore
    story_agents: StoryAgentPipeline
    langfuse_trace: object | None = None
    state: dict = field(default_factory=dict)
    result_summary: dict = field(default_factory=dict)
    final_status: str = "completed"
    progress_points: dict[str, int] = field(default_factory=dict)
    _sequence: int = 0
    _langfuse_observations: dict[int, object] = field(default_factory=dict)

    def set_progress(self, node_key: str) -> None:
        progress = self.progress_points.get(node_key)
        if progress is not None:
            self.job.progress = progress
            self.db.flush()

    def set_status_message(self, message: str) -> None:
        self.job.status_message = message
        self.db.flush()

    def next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    @staticmethod
    def _merge_usage_payload(
        existing_payload: dict | None,
        *,
        provider_usage: dict | None = None,
        langfuse_payload: dict | None = None,
    ) -> dict:
        payload = dict(existing_payload or {})
        if provider_usage:
            payload.update(provider_usage)
        if langfuse_payload:
            payload["langfuse"] = langfuse_payload
        return payload

    def record_agent_run(
        self,
        *,
        step_key: str,
        agent_name: str,
        response: StructuredAgentResponse,
        adoption_state: str = "proposed",
        status: str = "completed",
    ) -> AgentRun:
        run = AgentRun(
            job=self.job,
            project_id=self.job.project_id,
            chapter_id=self.job.chapter_id,
            scene_id=self.job.scene_id,
            sequence=self.next_sequence(),
            step_key=step_key,
            agent_name=agent_name,
            status=status,
            adoption_state=adoption_state,
            model_id=response.trace.get("model"),
            input_summary=response.input_summary or response.trace.get("input_summary", ""),
            prompt_preview=response.prompt_preview or response.trace.get("prompt_preview", ""),
            output_summary=response.output_summary or response.trace.get("output_summary", ""),
            stream_text=response.trace.get("stream_text", ""),
            public_notes=response.payload.get("public_notes", []),
            issues=response.payload.get("issues", []),
            decision=response.payload.get("decision"),
            usage_payload=self._merge_usage_payload(
                None,
                provider_usage=response.trace.get("usage", {}),
                langfuse_payload=response.trace.get("langfuse"),
            ),
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        self.db.add(run)
        self.db.flush()
        return run

    def begin_agent_run(
        self,
        *,
        step_key: str,
        agent_name: str,
        model_id: str | None,
        input_summary: str,
        prompt_preview: str,
        output_summary: str,
        public_notes: list[str] | None = None,
    ) -> AgentRun:
        run = AgentRun(
            job=self.job,
            project_id=self.job.project_id,
            chapter_id=self.job.chapter_id,
            scene_id=self.job.scene_id,
            sequence=self.next_sequence(),
            step_key=step_key,
            agent_name=agent_name,
            status="processing",
            adoption_state="proposed",
            model_id=model_id,
            input_summary=input_summary,
            prompt_preview=prompt_preview,
            output_summary=output_summary,
            stream_text="",
            public_notes=public_notes or [],
            issues=[],
            usage_payload={},
            started_at=datetime.now(UTC),
            completed_at=None,
        )
        self.db.add(run)
        self.db.flush()
        if self.langfuse_trace and not isinstance(self.langfuse_trace, NoopLangfuseWorkflowTrace):
            langfuse_observation = getattr(self.langfuse_trace, "start_agent_observation", lambda **_: None)(
                step_key=step_key,
                agent_name=agent_name,
                model_id=model_id,
                input_summary=input_summary,
                prompt_preview=prompt_preview,
                metadata={
                    "job_id": self.job.id,
                    "project_id": self.job.project_id,
                    "chapter_id": self.job.chapter_id,
                    "scene_id": self.job.scene_id,
                },
            )
            if langfuse_observation is not None:
                self._langfuse_observations[run.id] = langfuse_observation
                run.usage_payload = self._merge_usage_payload(
                    run.usage_payload,
                    langfuse_payload=getattr(langfuse_observation, "payload", lambda: {})(),
                )
                self.db.flush()
        return run

    def update_agent_run_stream(
        self,
        run: AgentRun,
        *,
        stream_text: str | None = None,
        output_summary: str | None = None,
        public_notes: list[str] | None = None,
        status_message: str | None = None,
        progress: int | None = None,
    ) -> None:
        if stream_text is not None:
            run.stream_text = stream_text
        if output_summary is not None:
            run.output_summary = output_summary
        if public_notes is not None:
            run.public_notes = public_notes
        if status_message is not None:
            self.job.status_message = status_message
        if progress is not None:
            self.job.progress = max(self.job.progress, min(progress, 95))
        langfuse_observation = self._langfuse_observations.get(run.id)
        if langfuse_observation is not None:
            getattr(langfuse_observation, "update", lambda **_: None)(
                output=stream_text or output_summary or status_message,
                metadata=_compact_trace_metadata(progress=progress, public_notes=public_notes),
            )
        self.db.flush()

    def complete_agent_run(
        self,
        run: AgentRun,
        *,
        response: StructuredAgentResponse,
        adoption_state: str = "proposed",
        status: str = "completed",
    ) -> AgentRun:
        run.status = status
        run.adoption_state = adoption_state
        run.model_id = response.trace.get("model")
        run.input_summary = response.input_summary or response.trace.get("input_summary", run.input_summary)
        run.prompt_preview = response.prompt_preview or response.trace.get("prompt_preview", run.prompt_preview)
        run.output_summary = response.output_summary or response.trace.get("output_summary", run.output_summary)
        run.stream_text = response.trace.get("stream_text", run.stream_text)
        run.public_notes = response.payload.get("public_notes", run.public_notes)
        run.issues = response.payload.get("issues", [])
        run.decision = response.payload.get("decision")
        langfuse_observation = self._langfuse_observations.pop(run.id, None)
        langfuse_payload = getattr(langfuse_observation, "payload", lambda: {})() if langfuse_observation else None
        run.usage_payload = self._merge_usage_payload(
            run.usage_payload,
            provider_usage=response.trace.get("usage", {}),
            langfuse_payload=langfuse_payload,
        )
        run.completed_at = datetime.now(UTC)
        if langfuse_observation is not None:
            getattr(langfuse_observation, "complete", lambda **_: None)(
                output=response.output_summary or response.trace.get("output_summary") or response.raw_text,
                metadata={
                    "status": status,
                    "adoption_state": adoption_state,
                    "public_notes": response.payload.get("public_notes", []),
                    "issues": response.payload.get("issues", []),
                    "decision": response.payload.get("decision"),
                    "prompt_name": response.trace.get("prompt_name"),
                    "prompt_source": response.trace.get("prompt_source"),
                    "prompt_version": response.trace.get("prompt_version"),
                    "prompt_label": response.trace.get("prompt_label"),
                },
            )
        self.db.flush()
        return run

    def fail_agent_run(self, run: AgentRun, *, error_message: str) -> AgentRun:
        run.status = "failed"
        run.adoption_state = "rejected"
        run.error_message = error_message
        run.completed_at = datetime.now(UTC)
        langfuse_observation = self._langfuse_observations.pop(run.id, None)
        if langfuse_observation is not None:
            run.usage_payload = self._merge_usage_payload(
                run.usage_payload,
                langfuse_payload=getattr(langfuse_observation, "payload", lambda: {})(),
            )
            getattr(langfuse_observation, "fail", lambda **_: None)(
                output=error_message,
                metadata={"status": "failed", "error_message": error_message},
            )
        self.db.flush()
        return run

    def create_intervention(
        self,
        *,
        chapter: Chapter,
        reviewer_run: AgentRun,
        intervention_type: str,
        reviewer_notes: str,
        suggested_guidance: str,
    ) -> ReviewIntervention:
        intervention = ReviewIntervention(
            job=self.job,
            chapter=chapter,
            reviewer_run=reviewer_run,
            intervention_type=intervention_type,
            reviewer_notes=reviewer_notes,
            suggested_guidance=suggested_guidance,
            status="pending",
        )
        self.db.add(intervention)
        self.db.flush()
        return intervention


class WorkflowRunner:
    def __init__(
        self,
        session_factory,
        asset_store: LocalAssetStore,
        story_agents: StoryAgentPipeline,
        *,
        langfuse_tracer=None,
        review_intervention_min_severity: str = "critical",
    ):
        self.session_factory = session_factory
        self.asset_store = asset_store
        self.story_agents = story_agents
        self.langfuse_tracer = langfuse_tracer
        self.review_intervention_min_severity = review_intervention_min_severity
        self.graphs = self._build_graphs()

    def run_job(self, job_id: int) -> None:
        from .database import session_scope

        with session_scope(self.session_factory) as db:
            job = db.get(GenerationJob, job_id)
            if not job:
                return

            graph = self.graphs.get(job.job_type)
            if not graph:
                job.status = "failed"
                job.error_message = f"Unsupported workflow: {job.job_type}"
                job.completed_at = datetime.now(UTC)
                return

            execution = WorkflowExecution(
                db=db,
                job=job,
                asset_store=self.asset_store,
                story_agents=self.story_agents,
                langfuse_trace=self.langfuse_tracer.start_workflow_trace(job=job) if self.langfuse_tracer else None,
                progress_points=self._progress_points_for(graph),
            )

            try:
                job.status = "processing"
                job.progress = 5
                job.status_message = "工作流已启动，正在整理创作上下文。"
                job.error_message = None
                job.completed_at = None
                db.flush()

                node_key: str | None = graph.start_at
                while node_key:
                    execution.set_progress(node_key)
                    node = graph.nodes[node_key]
                    node_key = node.handler(execution)

                job.status = execution.final_status
                job.progress = 100
                job.status_message = (
                    "Reviewer 需要你确认后再继续。"
                    if execution.final_status == "awaiting_user"
                    else "本轮协作已完成。"
                )
                langfuse_payload = getattr(execution.langfuse_trace, "payload", lambda: {})()
                if langfuse_payload:
                    execution.result_summary["langfuse"] = langfuse_payload
                job.result_payload = execution.result_summary
                job.completed_at = datetime.now(UTC)
                if execution.langfuse_trace is not None:
                    getattr(execution.langfuse_trace, "complete", lambda **_: None)(
                        output=execution.result_summary,
                        metadata={
                            "status": job.status,
                            "job_type": job.job_type,
                            "progress": job.progress,
                        },
                    )
            except Exception as exc:  # pragma: no cover - surfaced via API status
                job.status = "failed"
                job.error_message = str(exc)
                job.status_message = f"任务失败：{exc}"
                job.completed_at = datetime.now(UTC)
                if execution.langfuse_trace is not None:
                    getattr(execution.langfuse_trace, "fail", lambda **_: None)(
                        output=str(exc),
                        metadata={
                            "status": "failed",
                            "job_type": job.job_type,
                            "error_message": str(exc),
                        },
                    )
            finally:
                if execution.langfuse_trace is not None:
                    getattr(execution.langfuse_trace, "close", lambda: None)()

    def _build_graphs(self) -> dict[str, WorkflowGraph]:
        return {
            "outline": WorkflowGraph(
                key="outline",
                start_at="load_project",
                nodes={
                    "load_project": WorkflowNode("load_project", self._load_project_for_outline),
                    "planner": WorkflowNode("planner", self._planner_step),
                    "persist_outline": WorkflowNode("persist_outline", self._persist_outline),
                },
            ),
            "outline_repair": WorkflowGraph(
                key="outline_repair",
                start_at="load_project",
                nodes={
                    "load_project": WorkflowNode("load_project", self._load_project_for_outline),
                    "planner": WorkflowNode("planner", self._planner_step),
                    "persist_outline_repair": WorkflowNode("persist_outline_repair", self._persist_outline_repair),
                },
            ),
            "chapter_draft": self._build_draft_graph("chapter_draft"),
            "chapter_draft_retry": self._build_draft_graph("chapter_draft_retry"),
            "chapter_scenes": self._build_scenes_graph("chapter_scenes"),
            "chapter_scenes_retry": self._build_scenes_graph("chapter_scenes_retry"),
            "scene_illustrations": WorkflowGraph(
                key="scene_illustrations",
                start_at="load_scene",
                nodes={
                    "load_scene": WorkflowNode("load_scene", self._load_scene_context),
                    "visual_prompt": WorkflowNode("visual_prompt", self._visual_prompt_step),
                    "image_generation": WorkflowNode("image_generation", self._image_generation_step),
                    "persist_assets": WorkflowNode("persist_assets", self._persist_scene_assets),
                },
            ),
            "export": WorkflowGraph(
                key="export",
                start_at="load_export",
                nodes={
                    "load_export": WorkflowNode("load_export", self._load_export_context),
                    "persist_export": WorkflowNode("persist_export", self._persist_export),
                },
            ),
        }

    def _build_draft_graph(self, key: str) -> WorkflowGraph:
        return WorkflowGraph(
            key=key,
            start_at="load_chapter",
            nodes={
                "load_chapter": WorkflowNode("load_chapter", self._load_chapter_context),
                "writer_draft": WorkflowNode("writer_draft", self._writer_draft_step),
                "reviewer_draft": WorkflowNode("reviewer_draft", self._reviewer_draft_step),
                "draft_decision_gate": WorkflowNode("draft_decision_gate", self._draft_decision_gate),
                "persist_draft": WorkflowNode("persist_draft", self._persist_draft),
                "create_intervention": WorkflowNode("create_intervention", self._create_intervention),
            },
        )

    def _build_scenes_graph(self, key: str) -> WorkflowGraph:
        return WorkflowGraph(
            key=key,
            start_at="load_chapter",
            nodes={
                "load_chapter": WorkflowNode("load_chapter", self._load_chapter_context),
                "writer_scenes": WorkflowNode("writer_scenes", self._writer_scenes_step),
                "reviewer_scenes": WorkflowNode("reviewer_scenes", self._reviewer_scenes_step),
                "scenes_decision_gate": WorkflowNode("scenes_decision_gate", self._scenes_decision_gate),
                "persist_scenes": WorkflowNode("persist_scenes", self._persist_scenes),
                "create_intervention": WorkflowNode("create_intervention", self._create_intervention),
            },
        )

    @staticmethod
    def _progress_points_for(graph: WorkflowGraph) -> dict[str, int]:
        total = max(len(graph.nodes), 1)
        progress_points = {}
        for index, key in enumerate(graph.nodes, start=1):
            progress_points[key] = min(95, int(index * 90 / total))
        return progress_points

    @staticmethod
    def _stream_callback(
        execution: WorkflowExecution,
        run: AgentRun,
        *,
        live_status_message: str,
    ) -> Callable[[dict], None]:
        last_flush_at = 0.0

        def handle(event: dict) -> None:
            nonlocal last_flush_at
            now = time.monotonic()
            if now - last_flush_at < 0.35 and not event.get("final"):
                return
            last_flush_at = now
            execution.update_agent_run_stream(
                run,
                stream_text=event.get("text"),
                output_summary=live_status_message,
                status_message=live_status_message,
                progress=event.get("progress"),
            )

        return handle

    @staticmethod
    def _severity_rank(value: str | None) -> int:
        return SEVERITY_RANK.get((value or "").strip().lower(), SEVERITY_RANK["minor"])

    @staticmethod
    def _resolve_story_bible_revision_id(execution: WorkflowExecution, project: Project) -> int | None:
        snapshot_revision_id = execution.job.input_snapshot.get("story_bible_revision_id")
        if snapshot_revision_id is not None:
            return int(snapshot_revision_id)
        latest_revision = current_story_bible_revision(project.story_bible)
        return latest_revision.id if latest_revision else None

    @staticmethod
    def _chapter_has_protected_content(chapter: Chapter) -> bool:
        if any(block.is_locked or block.is_user_edited for block in chapter.narrative_blocks):
            return True
        for scene in chapter.scenes:
            if scene.is_locked or scene.is_user_edited:
                return True
            if any(block.is_locked or block.is_user_edited for block in scene.dialogue_blocks):
                return True
        return False

    def _should_require_manual_intervention(
        self,
        reviewer_result: StructuredAgentResponse,
        *,
        has_revised_payload: bool,
        chapter: Chapter | None = None,
    ) -> bool:
        decision = reviewer_result.payload.get("decision", "accept")
        if decision == "accept":
            return False
        if decision == "fallback_planner":
            return True
        if not has_revised_payload:
            return True
        if reviewer_result.payload.get("requires_user_confirmation"):
            return True
        if chapter is not None and self._chapter_has_protected_content(chapter):
            return self._severity_rank(reviewer_result.payload.get("severity")) >= self._severity_rank("major")
        return self._severity_rank(reviewer_result.payload.get("severity")) >= self._severity_rank(
            self.review_intervention_min_severity
        )

    def _apply_narrative_blocks_with_protection(
        self,
        execution: WorkflowExecution,
        chapter: Chapter,
        generated_blocks: list[str],
    ) -> list[NarrativeBlock]:
        changed_blocks: list[NarrativeBlock] = []
        existing_blocks = sorted(chapter.narrative_blocks, key=lambda item: item.order_index)
        total = max(len(existing_blocks), len(generated_blocks))
        for index in range(1, total + 1):
            existing = existing_blocks[index - 1] if index - 1 < len(existing_blocks) else None
            generated_content = generated_blocks[index - 1] if index - 1 < len(generated_blocks) else None
            if existing and (existing.is_locked or existing.is_user_edited):
                existing.order_index = index
                continue
            if generated_content is None:
                if existing:
                    execution.db.delete(existing)
                continue
            block = existing or NarrativeBlock(chapter=chapter)
            if block.id is None:
                execution.db.add(block)
            block.order_index = index
            block.content = generated_content
            block.is_user_edited = False
            block.last_editor_type = "agent"
            changed_blocks.append(block)
        execution.db.flush()
        return changed_blocks

    def _apply_dialogues_with_protection(
        self,
        execution: WorkflowExecution,
        scene: Scene,
        generated_dialogues: list[dict],
    ) -> list[DialogueBlock]:
        changed_dialogues: list[DialogueBlock] = []
        existing_dialogues = sorted(scene.dialogue_blocks, key=lambda item: item.order_index)
        total = max(len(existing_dialogues), len(generated_dialogues))
        for index in range(1, total + 1):
            existing = existing_dialogues[index - 1] if index - 1 < len(existing_dialogues) else None
            generated_payload = generated_dialogues[index - 1] if index - 1 < len(generated_dialogues) else None
            if existing and (existing.is_locked or existing.is_user_edited):
                existing.order_index = index
                continue
            if generated_payload is None:
                if existing:
                    execution.db.delete(existing)
                continue
            block = existing or DialogueBlock(scene=scene)
            if block.id is None:
                execution.db.add(block)
            block.order_index = index
            block.speaker = generated_payload["speaker"].strip()
            block.parenthetical = generated_payload.get("parenthetical", "").strip()
            block.content = generated_payload["content"].strip()
            block.is_user_edited = False
            block.last_editor_type = "agent"
            changed_dialogues.append(block)
        execution.db.flush()
        return changed_dialogues

    def _apply_scenes_with_protection(
        self,
        execution: WorkflowExecution,
        chapter: Chapter,
        generated_scenes: list[dict],
    ) -> tuple[list[Scene], list[DialogueBlock]]:
        changed_scenes: list[Scene] = []
        changed_dialogues: list[DialogueBlock] = []
        existing_scenes = sorted(chapter.scenes, key=lambda item: item.order_index)
        valid_cast_names = {character.name for character in chapter.project.characters}
        total = max(len(existing_scenes), len(generated_scenes))
        for index in range(1, total + 1):
            existing = existing_scenes[index - 1] if index - 1 < len(existing_scenes) else None
            generated_payload = generated_scenes[index - 1] if index - 1 < len(generated_scenes) else None
            if existing and (existing.is_locked or existing.is_user_edited):
                existing.order_index = index
                continue
            if generated_payload is None:
                if existing:
                    execution.db.delete(existing)
                continue
            scene = existing or Scene(chapter=chapter)
            if scene.id is None:
                execution.db.add(scene)
            scene.order_index = index
            scene.title = generated_payload["title"].strip()
            scene.scene_type = generated_payload["scene_type"].strip().upper() or "INT"
            scene.location = generated_payload["location"].strip()
            scene.time_of_day = generated_payload["time_of_day"].strip().upper() or "DAY"
            scene.cast_names = [name for name in generated_payload.get("cast_names", []) if name in valid_cast_names]
            scene.objective = generated_payload["objective"].strip()
            scene.emotional_tone = generated_payload["emotional_tone"].strip()
            scene.is_user_edited = False
            scene.last_editor_type = "agent"
            execution.db.flush()
            changed_scenes.append(scene)
            changed_dialogues.extend(
                self._apply_dialogues_with_protection(execution, scene, generated_payload.get("dialogues", []))
            )
        execution.db.flush()
        return changed_scenes, changed_dialogues

    def _load_project(self, db: Session, project_id: int) -> Project:
        project = (
            db.query(Project)
            .options(
                selectinload(Project.story_bible),
                selectinload(Project.owned_characters).selectinload(Character.visual_profile),
                selectinload(Project.owned_characters).selectinload(Character.linked_projects),
                selectinload(Project.linked_characters).selectinload(Character.visual_profile),
                selectinload(Project.linked_characters).selectinload(Character.project),
                selectinload(Project.linked_characters).selectinload(Character.linked_projects),
                selectinload(Project.chapters).selectinload(Chapter.narrative_blocks),
                selectinload(Project.chapters).selectinload(Chapter.scenes).selectinload(Scene.dialogue_blocks),
                selectinload(Project.chapters).selectinload(Chapter.review_interventions),
            )
            .filter(Project.id == project_id)
            .first()
        )
        if not project:
            raise ValueError("Project not found")
        return project

    def _load_project_for_outline(self, execution: WorkflowExecution) -> str:
        execution.set_status_message("正在读取项目、角色与既有世界观。")
        project = self._load_project(execution.db, execution.job.project_id)
        chapter_count = int(
            execution.job.input_snapshot.get("chapter_count")
            or project.target_chapter_count
            or 6
        )
        if execution.job.job_type == "outline":
            for chapter in list(project.chapters):
                if chapter.is_locked:
                    raise ValueError("Cannot regenerate outline while locked chapters exist")
        execution.state["project"] = project
        execution.state["chapter_count"] = chapter_count
        execution.state["extra_guidance"] = execution.job.input_snapshot.get("extra_guidance", "")
        execution.state["anchor_chapter_id"] = execution.job.input_snapshot.get("anchor_chapter_id")
        return "planner"

    def _planner_step(self, execution: WorkflowExecution) -> str:
        project: Project = execution.state["project"]
        anchor_chapter = None
        anchor_chapter_id = execution.state.get("anchor_chapter_id")
        if anchor_chapter_id:
            anchor_chapter = next((chapter for chapter in project.chapters if chapter.id == anchor_chapter_id), None)
        planner_run = execution.begin_agent_run(
            step_key="planner",
            agent_name="planner",
            model_id=getattr(execution.story_agents, "planner_model", None),
            input_summary=f"Plan {execution.state['chapter_count']} chapters for project {project.title}.",
            prompt_preview=f"Generate story bible updates and {execution.state['chapter_count']} distinct chapter plans for {project.title}.",
            output_summary="正在铺排章节冲突、人物关系与 hook。",
            public_notes=["正在梳理角色关系与长线矛盾。"],
        )
        execution.set_status_message("Planner 正在铺排章节冲突、人物关系与 hook。")
        try:
            result = execution.story_agents.plan_outline(
                project,
                execution.state["chapter_count"],
                extra_guidance=execution.state.get("extra_guidance", ""),
                anchor_chapter=anchor_chapter,
                on_stream=self._stream_callback(
                    execution,
                    planner_run,
                    live_status_message="Planner 正在铺排章节冲突、人物关系与 hook。",
                ),
            )
        except Exception as exc:
            execution.fail_agent_run(planner_run, error_message=str(exc))
            raise
        planner_run = execution.complete_agent_run(planner_run, response=result)
        execution.state["planner_result"] = result
        execution.state["planner_run"] = planner_run
        return "persist_outline_repair" if execution.job.job_type == "outline_repair" else "persist_outline"

    def _persist_outline(self, execution: WorkflowExecution) -> str | None:
        execution.set_status_message("Planner 已完成大纲，正在回填章节轨道。")
        project: Project = execution.state["project"]
        planner_result: StructuredAgentResponse = execution.state["planner_result"]
        planner_run: AgentRun = execution.state["planner_run"]
        chapter_count = execution.state["chapter_count"]
        bound_story_bible_revision_id = self._resolve_story_bible_revision_id(execution, project)
        planned_chapters = planner_result.payload.get("chapters", [])
        if len(planned_chapters) < chapter_count:
            raise ValueError("Planner did not return enough chapters")

        for chapter in list(project.chapters):
            execution.db.delete(chapter)
        execution.db.flush()

        story_bible_updates = planner_result.payload.get("story_bible_updates", {})
        if project.story_bible:
            project.story_bible.world_notes = story_bible_updates.get("world_notes", project.story_bible.world_notes)
            project.story_bible.style_notes = story_bible_updates.get("style_notes", project.story_bible.style_notes)
            project.story_bible.writing_rules = story_bible_updates.get("writing_rules", project.story_bible.writing_rules)
            project.story_bible.addressing_rules = story_bible_updates.get(
                "addressing_rules",
                project.story_bible.addressing_rules,
            )
            project.story_bible.timeline_rules = story_bible_updates.get(
                "timeline_rules",
                project.story_bible.timeline_rules,
            )
        story_bible_revision = create_story_bible_revision(
            project,
            execution.db,
            created_by="agent",
            source_job_id=execution.job.id,
        )

        for index, item in enumerate(planned_chapters[:chapter_count], start=1):
            execution.db.add(
                Chapter(
                    project=project,
                    order_index=index,
                    title=item["title"].strip(),
                    summary=item["summary"].strip(),
                    chapter_goal=item["chapter_goal"].strip(),
                    hook=item["hook"].strip(),
                    status="planned",
                    source_story_bible_revision_id=bound_story_bible_revision_id,
                )
            )

        project.status = "outlined"
        planner_run.adoption_state = "applied"
        execution.result_summary = {
            "project_id": project.id,
            "chapter_count": chapter_count,
            "story_bible_revision_id": bound_story_bible_revision_id,
            "applied_story_bible_revision_id": story_bible_revision.id if story_bible_revision else None,
            "story_bible_updates": story_bible_updates,
            "model_ids": {"planner": planner_run.model_id},
            "trace_count": 1,
        }
        execution.db.flush()
        return None

    def _persist_outline_repair(self, execution: WorkflowExecution) -> str | None:
        execution.set_status_message("Planner 回退方案已生成，正在更新受影响章节。")
        project: Project = execution.state["project"]
        planner_result: StructuredAgentResponse = execution.state["planner_result"]
        planner_run: AgentRun = execution.state["planner_run"]
        chapter_count = execution.state["chapter_count"]
        bound_story_bible_revision_id = self._resolve_story_bible_revision_id(execution, project)
        planned_chapters = planner_result.payload.get("chapters", [])
        if len(planned_chapters) < chapter_count:
            raise ValueError("Planner did not return enough chapters")

        anchor_chapter_id = execution.state.get("anchor_chapter_id")
        anchor_order = 1
        if anchor_chapter_id:
            chapter = next((item for item in project.chapters if item.id == anchor_chapter_id), None)
            if chapter:
                anchor_order = chapter.order_index

        story_bible_updates = planner_result.payload.get("story_bible_updates", {})
        if project.story_bible:
            project.story_bible.world_notes = story_bible_updates.get("world_notes", project.story_bible.world_notes)
            project.story_bible.style_notes = story_bible_updates.get("style_notes", project.story_bible.style_notes)
            project.story_bible.writing_rules = story_bible_updates.get("writing_rules", project.story_bible.writing_rules)
            project.story_bible.addressing_rules = story_bible_updates.get(
                "addressing_rules",
                project.story_bible.addressing_rules,
            )
            project.story_bible.timeline_rules = story_bible_updates.get(
                "timeline_rules",
                project.story_bible.timeline_rules,
            )
        story_bible_revision = create_story_bible_revision(
            project,
            execution.db,
            created_by="agent",
            source_job_id=execution.job.id,
        )

        updated_orders = []
        chapter_lookup = {chapter.order_index: chapter for chapter in project.chapters}
        for item in planned_chapters:
            order_index = int(item["order_index"])
            chapter = chapter_lookup.get(order_index)
            if not chapter or chapter.is_locked or order_index < anchor_order:
                continue
            chapter.title = item["title"].strip()
            chapter.summary = item["summary"].strip()
            chapter.chapter_goal = item["chapter_goal"].strip()
            chapter.hook = item["hook"].strip()
            chapter.source_story_bible_revision_id = bound_story_bible_revision_id
            if chapter.narrative_blocks or chapter.scenes:
                chapter.status = "needs_regeneration"
            else:
                chapter.status = "planned"
            updated_orders.append(order_index)

        planner_run.adoption_state = "applied"
        execution.result_summary = {
            "project_id": project.id,
            "chapter_count": chapter_count,
            "updated_orders": updated_orders,
            "story_bible_revision_id": bound_story_bible_revision_id,
            "applied_story_bible_revision_id": story_bible_revision.id if story_bible_revision else None,
            "story_bible_updates": story_bible_updates,
            "model_ids": {"planner": planner_run.model_id},
            "trace_count": 1,
        }
        execution.db.flush()
        return None

    def _load_chapter_context(self, execution: WorkflowExecution) -> str:
        execution.set_status_message("正在汇总当前章节、前序章节与角色设定。")
        chapter = (
            execution.db.query(Chapter)
            .options(selectinload(Chapter.narrative_blocks))
            .options(selectinload(Chapter.project).selectinload(Project.story_bible))
            .options(selectinload(Chapter.project).selectinload(Project.owned_characters).selectinload(Character.visual_profile))
            .options(selectinload(Chapter.project).selectinload(Project.owned_characters).selectinload(Character.linked_projects))
            .options(selectinload(Chapter.project).selectinload(Project.linked_characters).selectinload(Character.visual_profile))
            .options(selectinload(Chapter.project).selectinload(Project.linked_characters).selectinload(Character.project))
            .options(selectinload(Chapter.project).selectinload(Project.linked_characters).selectinload(Character.linked_projects))
            .options(selectinload(Chapter.scenes).selectinload(Scene.dialogue_blocks))
            .filter(Chapter.id == execution.job.chapter_id)
            .first()
        )
        if not chapter:
            raise ValueError("Chapter not found")
        if chapter.is_locked:
            raise ValueError("Locked chapter cannot be regenerated")

        previous_chapters = (
            execution.db.query(Chapter)
            .filter(Chapter.project_id == chapter.project_id, Chapter.order_index < chapter.order_index)
            .order_by(Chapter.order_index.asc())
            .all()
        )
        execution.state["chapter"] = chapter
        execution.state["project"] = chapter.project
        execution.state["previous_chapters"] = previous_chapters
        execution.state["extra_guidance"] = execution.job.input_snapshot.get("extra_guidance", "")
        if execution.job.job_type.startswith("chapter_scenes"):
            return "writer_scenes"
        return "writer_draft"

    def _writer_draft_step(self, execution: WorkflowExecution) -> str:
        chapter: Chapter = execution.state["chapter"]
        writer_run = execution.begin_agent_run(
            step_key="writer_draft",
            agent_name="writer",
            model_id=getattr(execution.story_agents, "writer_model", None),
            input_summary=f"Write draft blocks for chapter {chapter.order_index}: {chapter.title}.",
            prompt_preview=f"Write narrative blocks for chapter {chapter.title} that continue the established tone and causal chain.",
            output_summary="正在组织正文段落与章节情绪落点。",
            public_notes=["正在把章节目标落到可表演的动作与对白余韵上。"],
        )
        execution.set_status_message("Writer 正在组织正文段落与章节情绪落点。")
        try:
            result = execution.story_agents.write_chapter_draft(
                execution.state["project"],
                chapter,
                execution.state["previous_chapters"],
                extra_guidance=execution.state.get("extra_guidance", ""),
                on_stream=self._stream_callback(
                    execution,
                    writer_run,
                    live_status_message="Writer 正在组织正文段落与章节情绪落点。",
                ),
            )
        except Exception as exc:
            execution.fail_agent_run(writer_run, error_message=str(exc))
            raise
        writer_run = execution.complete_agent_run(writer_run, response=result)
        execution.state["writer_result"] = result
        execution.state["writer_run"] = writer_run
        return "reviewer_draft"

    def _reviewer_draft_step(self, execution: WorkflowExecution) -> str:
        chapter: Chapter = execution.state["chapter"]
        reviewer_run = execution.begin_agent_run(
            step_key="reviewer_draft",
            agent_name="reviewer",
            model_id=getattr(execution.story_agents, "reviewer_model", None),
            input_summary=f"Review draft for chapter {chapter.order_index}: {chapter.title}.",
            prompt_preview=f"Review the chapter draft for consistency, pacing, and motivation, then decide whether to accept, rewrite, or fall back to planning.",
            output_summary="正在审校口吻、时间线与情绪递进。",
            public_notes=["正在检查人物口吻、称呼和章节推进是否统一。"],
        )
        execution.set_status_message("Reviewer 正在审校口吻、时间线与情绪递进。")
        try:
            result = execution.story_agents.review_chapter_draft(
                execution.state["project"],
                chapter,
                execution.state["writer_result"].payload,
                on_stream=self._stream_callback(
                    execution,
                    reviewer_run,
                    live_status_message="Reviewer 正在审校口吻、时间线与情绪递进。",
                ),
            )
        except Exception as exc:
            execution.fail_agent_run(reviewer_run, error_message=str(exc))
            raise
        reviewer_run = execution.complete_agent_run(reviewer_run, response=result)
        execution.state["reviewer_result"] = result
        execution.state["reviewer_run"] = reviewer_run
        return "draft_decision_gate"

    def _draft_decision_gate(self, execution: WorkflowExecution) -> str:
        reviewer_result: StructuredAgentResponse = execution.state["reviewer_result"]
        writer_run: AgentRun = execution.state["writer_run"]
        reviewer_run: AgentRun = execution.state["reviewer_run"]
        chapter: Chapter = execution.state["chapter"]
        decision = reviewer_result.payload.get("decision", "accept")
        revised_blocks = reviewer_result.payload.get("revised_narrative_blocks") or []
        if decision == "accept" or not self._should_require_manual_intervention(
            reviewer_result,
            has_revised_payload=bool(revised_blocks),
            chapter=chapter,
        ):
            writer_run.adoption_state = "superseded"
            reviewer_run.adoption_state = "applied"
            return "persist_draft"
        writer_run.adoption_state = "rejected"
        reviewer_run.adoption_state = "applied"
        execution.state["intervention_type"] = decision
        return "create_intervention"

    def _persist_draft(self, execution: WorkflowExecution) -> str | None:
        execution.set_status_message("Reviewer 已收束正文，正在写入章节成稿。")
        chapter: Chapter = execution.state["chapter"]
        writer_result: StructuredAgentResponse = execution.state["writer_result"]
        reviewer_result: StructuredAgentResponse = execution.state["reviewer_result"]
        writer_run: AgentRun = execution.state["writer_run"]
        reviewer_run: AgentRun = execution.state["reviewer_run"]
        revised_blocks = self._resolve_draft_blocks_to_persist(writer_result, reviewer_result)
        if not revised_blocks:
            raise ValueError("Reviewer did not return revised narrative blocks")
        changed_blocks = self._apply_narrative_blocks_with_protection(execution, chapter, revised_blocks)

        chapter.continuity_notes = resolve_continuity_notes(
            reviewer_result.payload,
            default_note="Reviewer 未返回连续性提示。",
        )
        chapter.status = "drafted"
        chapter.source_story_bible_revision_id = self._resolve_story_bible_revision_id(execution, chapter.project)
        revision = create_content_revision(
            chapter,
            execution.db,
            revision_kind="draft",
            created_by="agent",
            source_job_id=execution.job.id,
            summary=f"Reviewer applied chapter draft for chapter {chapter.order_index}.",
            story_bible_revision_id=chapter.source_story_bible_revision_id,
        )
        for block in changed_blocks:
            block.source_revision_id = revision.id
        revision.payload = snapshot_chapter_payload(chapter)
        execution.result_summary = {
            "chapter_id": chapter.id,
            "narrative_block_count": len(revised_blocks),
            "review_notes": reviewer_result.payload.get("issues", []),
            "story_bible_revision_id": chapter.source_story_bible_revision_id,
            "content_revision_id": revision.id,
            "apply_mode": reviewer_result.payload.get("apply_mode", "apply_revisions"),
            "model_ids": {
                "writer": writer_run.model_id,
                "reviewer": reviewer_run.model_id,
            },
            "trace_count": 2,
        }
        execution.db.flush()
        return None

    @staticmethod
    def _resolve_draft_blocks_to_persist(
        writer_result: StructuredAgentResponse,
        reviewer_result: StructuredAgentResponse,
    ) -> list[str]:
        writer_blocks = list(writer_result.payload.get("narrative_blocks") or [])
        reviewer_blocks = list(reviewer_result.payload.get("revised_narrative_blocks") or [])
        apply_mode = str(reviewer_result.payload.get("apply_mode") or "apply_revisions")
        writer_flags = StoryAgentPipeline._detect_narrative_quality_flags(writer_blocks)
        reviewer_flags = StoryAgentPipeline._detect_narrative_quality_flags(reviewer_blocks)
        if apply_mode == "preserve_writer" and writer_blocks:
            if writer_flags and reviewer_blocks and len(reviewer_flags) < len(writer_flags):
                return reviewer_blocks
            return writer_blocks
        return reviewer_blocks or writer_blocks

    def _writer_scenes_step(self, execution: WorkflowExecution) -> str:
        chapter: Chapter = execution.state["chapter"]
        writer_run = execution.begin_agent_run(
            step_key="writer_scenes",
            agent_name="writer",
            model_id=getattr(execution.story_agents, "writer_model", None),
            input_summary=f"Structure scenes for chapter {chapter.order_index}: {chapter.title}.",
            prompt_preview=f"Split chapter {chapter.title} into a flexible set of scenes with objectives, tone, and dialogue.",
            output_summary="正在拆分 Scene 卡与对白节奏。",
            public_notes=["正在把章节正文拆成有明确目标的场景。"],
        )
        execution.set_status_message("Writer 正在拆分 Scene 卡与对白节奏。")
        try:
            result = execution.story_agents.write_chapter_scenes(
                execution.state["project"],
                chapter,
                execution.state["previous_chapters"],
                extra_guidance=execution.state.get("extra_guidance", ""),
                on_stream=self._stream_callback(
                    execution,
                    writer_run,
                    live_status_message="Writer 正在拆分 Scene 卡与对白节奏。",
                ),
            )
        except Exception as exc:
            execution.fail_agent_run(writer_run, error_message=str(exc))
            raise
        writer_run = execution.complete_agent_run(writer_run, response=result)
        execution.state["writer_result"] = result
        execution.state["writer_run"] = writer_run
        return "reviewer_scenes"

    def _reviewer_scenes_step(self, execution: WorkflowExecution) -> str:
        chapter: Chapter = execution.state["chapter"]
        reviewer_run = execution.begin_agent_run(
            step_key="reviewer_scenes",
            agent_name="reviewer",
            model_id=getattr(execution.story_agents, "reviewer_model", None),
            input_summary=f"Review scenes for chapter {chapter.order_index}: {chapter.title}.",
            prompt_preview=f"Review the structured scenes for chapter {chapter.title} and decide whether to accept, rewrite, or fall back to planning.",
            output_summary="正在审校场景衔接、对白有效性与节奏压力。",
            public_notes=["正在检查场景衔接、口吻与对白是否彼此咬合。"],
        )
        execution.set_status_message("Reviewer 正在审校场景衔接、对白有效性与节奏压力。")
        try:
            result = execution.story_agents.review_chapter_scenes(
                execution.state["project"],
                chapter,
                execution.state["writer_result"].payload,
                on_stream=self._stream_callback(
                    execution,
                    reviewer_run,
                    live_status_message="Reviewer 正在审校场景衔接、对白有效性与节奏压力。",
                ),
            )
        except Exception as exc:
            execution.fail_agent_run(reviewer_run, error_message=str(exc))
            raise
        reviewer_run = execution.complete_agent_run(reviewer_run, response=result)
        execution.state["reviewer_result"] = result
        execution.state["reviewer_run"] = reviewer_run
        return "scenes_decision_gate"

    def _scenes_decision_gate(self, execution: WorkflowExecution) -> str:
        reviewer_result: StructuredAgentResponse = execution.state["reviewer_result"]
        writer_run: AgentRun = execution.state["writer_run"]
        reviewer_run: AgentRun = execution.state["reviewer_run"]
        chapter: Chapter = execution.state["chapter"]
        decision = reviewer_result.payload.get("decision", "accept")
        revised_scenes = reviewer_result.payload.get("revised_scenes") or []
        if decision == "accept" or not self._should_require_manual_intervention(
            reviewer_result,
            has_revised_payload=bool(revised_scenes),
            chapter=chapter,
        ):
            writer_run.adoption_state = "superseded"
            reviewer_run.adoption_state = "applied"
            return "persist_scenes"
        writer_run.adoption_state = "rejected"
        reviewer_run.adoption_state = "applied"
        execution.state["intervention_type"] = decision
        return "create_intervention"

    def _persist_scenes(self, execution: WorkflowExecution) -> str | None:
        execution.set_status_message("Reviewer 已收束场景结构，正在回填 Scene 卡。")
        chapter: Chapter = execution.state["chapter"]
        writer_result: StructuredAgentResponse = execution.state["writer_result"]
        reviewer_result: StructuredAgentResponse = execution.state["reviewer_result"]
        writer_run: AgentRun = execution.state["writer_run"]
        reviewer_run: AgentRun = execution.state["reviewer_run"]
        revised_scenes = reviewer_result.payload.get("revised_scenes") or writer_result.payload.get("scenes") or []
        if not revised_scenes:
            raise ValueError("Reviewer did not return revised scenes")
        changed_scenes, changed_dialogues = self._apply_scenes_with_protection(execution, chapter, revised_scenes)

        chapter.continuity_notes = resolve_continuity_notes(
            reviewer_result.payload,
            default_note="Reviewer 未返回场景连续性提示。",
        )
        chapter.status = "scenes_ready"
        chapter.source_story_bible_revision_id = self._resolve_story_bible_revision_id(execution, chapter.project)
        revision = create_content_revision(
            chapter,
            execution.db,
            revision_kind="scenes",
            created_by="agent",
            source_job_id=execution.job.id,
            summary=f"Reviewer applied scene structure for chapter {chapter.order_index}.",
            story_bible_revision_id=chapter.source_story_bible_revision_id,
        )
        for scene in changed_scenes:
            scene.source_revision_id = revision.id
        for dialogue in changed_dialogues:
            dialogue.source_revision_id = revision.id
        revision.payload = snapshot_chapter_payload(chapter)
        execution.result_summary = {
            "chapter_id": chapter.id,
            "scene_count": len(revised_scenes),
            "review_notes": reviewer_result.payload.get("issues", []),
            "story_bible_revision_id": chapter.source_story_bible_revision_id,
            "content_revision_id": revision.id,
            "model_ids": {
                "writer": writer_run.model_id,
                "reviewer": reviewer_run.model_id,
            },
            "trace_count": 2,
        }
        execution.db.flush()
        return None

    def _create_intervention(self, execution: WorkflowExecution) -> str | None:
        execution.set_status_message("Reviewer 认为本轮需要你确认后再继续。")
        chapter: Chapter = execution.state["chapter"]
        reviewer_result: StructuredAgentResponse = execution.state["reviewer_result"]
        reviewer_run: AgentRun = execution.state["reviewer_run"]
        intervention_type = execution.state["intervention_type"]
        intervention = execution.create_intervention(
            chapter=chapter,
            reviewer_run=reviewer_run,
            intervention_type=intervention_type,
            reviewer_notes=reviewer_result.payload.get("decision_reason") or "Reviewer requested user confirmation.",
            suggested_guidance=reviewer_result.payload.get("suggested_guidance", ""),
        )
        chapter.continuity_notes = resolve_continuity_notes(
            reviewer_result.payload,
            default_note="Reviewer 需要你的确认后继续。",
        )
        execution.final_status = "awaiting_user"
        execution.result_summary = {
            "chapter_id": chapter.id,
            "review_notes": reviewer_result.payload.get("issues", []),
            "model_ids": {
                "writer": execution.state["writer_run"].model_id,
                "reviewer": reviewer_run.model_id,
            },
            "pending_intervention_id": intervention.id,
            "trace_count": 2,
        }
        execution.db.flush()
        return None

    def _load_scene_context(self, execution: WorkflowExecution) -> str:
        execution.set_status_message("正在读取场景、出场角色与视觉锚点。")
        scene = (
            execution.db.query(Scene)
            .options(
                selectinload(Scene.chapter)
                .selectinload(Chapter.project)
                .selectinload(Project.owned_characters)
                .selectinload(Character.visual_profile)
            )
            .options(
                selectinload(Scene.chapter)
                .selectinload(Chapter.project)
                .selectinload(Project.owned_characters)
                .selectinload(Character.reference_images)
            )
            .options(
                selectinload(Scene.chapter)
                .selectinload(Chapter.project)
                .selectinload(Project.linked_characters)
                .selectinload(Character.visual_profile)
            )
            .options(
                selectinload(Scene.chapter)
                .selectinload(Chapter.project)
                .selectinload(Project.linked_characters)
                .selectinload(Character.reference_images)
            )
            .options(selectinload(Scene.illustrations))
            .filter(Scene.id == execution.job.scene_id)
            .first()
        )
        if not scene:
            raise ValueError("Scene not found")

        project = scene.chapter.project
        cast_lookup = {character.name: character for character in project.characters}
        cast_characters = [cast_lookup[name] for name in scene.cast_names if name in cast_lookup]
        execution.state["scene"] = scene
        execution.state["project"] = project
        execution.state["cast_characters"] = cast_characters
        execution.state["extra_guidance"] = execution.job.input_snapshot.get("extra_guidance", "")
        return "visual_prompt"

    def _visual_prompt_step(self, execution: WorkflowExecution) -> str:
        scene: Scene = execution.state["scene"]
        prompt_run = execution.begin_agent_run(
            step_key="visual_prompt",
            agent_name="visual_prompt",
            model_id=getattr(execution.story_agents, "visual_model", None),
            input_summary=f"Build a visual prompt for scene {scene.title}.",
            prompt_preview=f"Generate a cinematic illustration prompt for scene {scene.title} with cast and visual anchors.",
            output_summary="正在锁定镜头语言、时段氛围与角色视觉锚点。",
            public_notes=["正在把角色视觉锚点压到同一张剧照里。"],
        )
        execution.set_status_message("Visual Prompt 正在锁定镜头语言、时段氛围与角色视觉锚点。")
        try:
            result = execution.story_agents.build_visual_prompt(
                execution.state["project"],
                scene,
                execution.state["cast_characters"],
                extra_guidance=execution.state.get("extra_guidance", ""),
                on_stream=self._stream_callback(
                    execution,
                    prompt_run,
                    live_status_message="Visual Prompt 正在锁定镜头语言、时段氛围与角色视觉锚点。",
                ),
            )
        except Exception as exc:
            execution.fail_agent_run(prompt_run, error_message=str(exc))
            raise
        prompt_run = execution.complete_agent_run(
            prompt_run,
            response=result,
            adoption_state="applied",
        )
        execution.state["prompt_result"] = result
        execution.state["prompt_run"] = prompt_run
        return "image_generation"

    def _image_generation_step(self, execution: WorkflowExecution) -> str:
        scene: Scene = execution.state["scene"]
        prompt = execution.state["prompt_result"].payload["prompt_text"]
        candidate_count = int(execution.job.input_snapshot.get("candidate_count", 2))
        image_run = execution.begin_agent_run(
            step_key="image_generation",
            agent_name="image_generation",
            model_id=getattr(execution.story_agents, "image_model", None),
            input_summary=f"Render {candidate_count} illustration candidates for scene {scene.title}.",
            prompt_preview=f"Render scene {scene.title} into {candidate_count} cinematic stills using the approved prompt.",
            output_summary="正在向图像模型提交渲染请求。",
            public_notes=["正在渲染候选剧照并尽量保持角色一致性。"],
        )
        execution.set_status_message("Image Generation 正在渲染剧照候选。")
        try:
            result = execution.story_agents.generate_scene_illustrations(
                execution.state["project"],
                scene,
                execution.state["cast_characters"],
                prompt_text=prompt,
                candidate_count=candidate_count,
                extra_guidance=execution.state.get("extra_guidance", ""),
                on_stream=self._stream_callback(
                    execution,
                    image_run,
                    live_status_message="Image Generation 正在渲染剧照候选。",
                ),
            )
        except Exception as exc:
            execution.fail_agent_run(image_run, error_message=str(exc))
            raise
        image_run = execution.complete_agent_run(
            image_run,
            response=result,
            adoption_state="applied",
        )
        execution.state["image_result"] = result
        execution.state["image_run"] = image_run
        return "persist_assets"

    def _persist_scene_assets(self, execution: WorkflowExecution) -> str | None:
        execution.set_status_message("剧照候选已返回，正在写入资产库。")
        scene: Scene = execution.state["scene"]
        project: Project = execution.state["project"]
        prompt_result: StructuredAgentResponse = execution.state["prompt_result"]
        image_result: StructuredAgentResponse = execution.state["image_result"]
        prompt = prompt_result.payload["prompt_text"]
        scene.visual_prompt = prompt

        created_ids = []
        existing_max_candidate_index = max((item.candidate_index for item in scene.illustrations), default=0)
        canonical_illustration = next((item for item in scene.illustrations if item.is_canonical), None)
        reference_feedback = {
            "used_scene_canonical": canonical_illustration is not None,
            "canonical_illustration_id": canonical_illustration.id if canonical_illustration else None,
            "canonical_candidate_index": canonical_illustration.candidate_index if canonical_illustration else None,
            "extra_guidance": execution.state.get("extra_guidance", ""),
        }
        generated_images = image_result.payload.get("generated_images") or []
        if not generated_images:
            raise ValueError("Image generation did not return any candidate assets")

        for index, generated in enumerate(generated_images, start=1):
            payload_bytes = generated["payload_bytes"] if isinstance(generated, dict) else generated.payload_bytes
            media_type = generated.get("media_type") if isinstance(generated, dict) else generated.media_type
            revised_prompt = (
                generated.get("revised_prompt", "")
                if isinstance(generated, dict)
                else generated.revised_prompt
            )
            image_path, thumb_path = execution.asset_store.save_generated_image(
                category="illustrations",
                basename=f"scene_{scene.id}_candidate_{index}",
                payload=payload_bytes,
                media_type=media_type,
            )
            asset = IllustrationAsset(
                project=project,
                scene=scene,
                prompt_text=revised_prompt or prompt,
                file_path=image_path,
                thumbnail_path=thumb_path,
                status="completed",
                candidate_index=existing_max_candidate_index + index,
                is_canonical=False,
            )
            execution.db.add(asset)
            execution.db.flush()
            created_ids.append(asset.id)

        execution.result_summary = {
            "scene_id": scene.id,
            "illustration_ids": created_ids,
            "prompt_preview": prompt,
            "model_ids": {
                "visual_prompt": execution.state["prompt_run"].model_id,
                "image_generation": execution.state["image_run"].model_id,
            },
            "reference_feedback": image_result.payload.get("reference_feedback") or reference_feedback,
            "trace_count": 2,
        }
        return None

    def _load_export_context(self, execution: WorkflowExecution) -> str:
        execution.set_status_message("正在汇总作品正文、角色页与插图素材。")
        export_id = int(execution.job.input_snapshot["export_id"])
        export_package = (
            execution.db.query(ExportPackage)
            .options(
                selectinload(ExportPackage.project)
                .selectinload(Project.owned_characters)
                .selectinload(Character.reference_images),
                selectinload(ExportPackage.project)
                .selectinload(Project.linked_characters)
                .selectinload(Character.reference_images),
                selectinload(ExportPackage.project)
                .selectinload(Project.chapters)
                .selectinload(Chapter.narrative_blocks),
                selectinload(ExportPackage.project)
                .selectinload(Project.chapters)
                .selectinload(Chapter.scenes)
                .selectinload(Scene.dialogue_blocks),
                selectinload(ExportPackage.project)
                .selectinload(Project.chapters)
                .selectinload(Chapter.scenes)
                .selectinload(Scene.illustrations),
            )
            .filter(ExportPackage.id == export_id)
            .first()
        )
        if not export_package:
            raise ValueError("Export package not found")
        execution.state["export_package"] = export_package
        return "persist_export"

    def _persist_export(self, execution: WorkflowExecution) -> str | None:
        execution.set_status_message("正在合成 PDF 与 DOCX 导出包。")
        export_package: ExportPackage = execution.state["export_package"]
        export_package.status = "processing"
        export_project_bundle(export_package.project, export_package, execution.asset_store)
        export_package.status = "completed"
        export_package.completed_at = datetime.now(UTC)
        execution.result_summary = {"export_id": export_package.id}
        return None
