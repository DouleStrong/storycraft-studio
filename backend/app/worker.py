from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from redis import Redis
from rq import Queue, Worker

from .config import load_settings, review_intervention_min_severity
from .database import create_engine_and_session_factory
from .migrations import run_migrations
from .models import GenerationJob
from .providers import StoryAgentPipeline
from .storage import LocalAssetStore
from .workflow import WorkflowRunner

_workflow_runner: WorkflowRunner | None = None


def get_workflow_runner() -> WorkflowRunner:
    global _workflow_runner

    if _workflow_runner is not None:
        return _workflow_runner

    settings = load_settings()
    if settings.database_url.startswith("sqlite:///") and not settings.allow_sqlite:
        raise RuntimeError(
            "SQLite runtime support has been disabled. Configure STORY_PLATFORM_DB_URL to PostgreSQL before starting the worker."
        )
    if settings.database_url.startswith("sqlite:///"):
        db_path = settings.database_url.removeprefix("sqlite:///")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    run_migrations(settings)
    engine, session_factory = create_engine_and_session_factory(settings)
    asset_store = LocalAssetStore(settings.storage_dir, settings.export_dir)
    asset_store.storage_dir.mkdir(parents=True, exist_ok=True)
    asset_store.export_dir.mkdir(parents=True, exist_ok=True)

    _workflow_runner = WorkflowRunner(
        session_factory,
        asset_store,
        StoryAgentPipeline.from_settings(settings),
        review_intervention_min_severity=review_intervention_min_severity(settings),
    )
    return _workflow_runner


def run_generation_job(job_id: int) -> None:
    try:
        get_workflow_runner().run_job(job_id)
    except Exception as exc:
        _mark_job_failed(job_id, exc)
        raise


def _mark_job_failed(job_id: int, exc: Exception) -> None:
    settings = load_settings()
    engine, session_factory = create_engine_and_session_factory(settings)

    with session_factory() as db:
        job = db.get(GenerationJob, job_id)
        if not job:
            return
        job.status = "failed"
        job.error_message = str(exc)
        job.status_message = "Worker failed before the workflow could complete"
        job.completed_at = datetime.now(UTC)
        db.commit()

    engine.dispose()


def main() -> None:
    settings = load_settings()
    connection = Redis.from_url(settings.redis_url)
    queues = [Queue(settings.story_queue_name, connection=connection)]
    Worker(queues, connection=connection).work()


if __name__ == "__main__":
    main()
