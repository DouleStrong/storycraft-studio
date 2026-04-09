from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.database import Base, create_engine_and_session_factory
from app.models import GenerationJob, User


def configure_sqlite_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "runtime"
    base_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("STORY_PLATFORM_SKIP_DOTENV", "1")
    monkeypatch.setenv("STORY_PLATFORM_ALLOW_SQLITE", "1")
    monkeypatch.setenv("STORY_PLATFORM_DB_URL", f"sqlite:///{base_dir / 'worker.db'}")
    monkeypatch.setenv("STORY_PLATFORM_STORAGE_DIR", str(base_dir / "storage"))
    monkeypatch.setenv("STORY_PLATFORM_EXPORT_DIR", str(base_dir / "exports"))
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")


def test_worker_module_imports_cleanly():
    worker_module = importlib.import_module("app.worker")
    assert hasattr(worker_module, "run_generation_job")
    assert hasattr(worker_module, "main")


def test_project_root_can_import_app_worker_for_rq_resolution():
    project_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "-c", "import importlib; importlib.import_module('app.worker'); print('ok')"],
        cwd=project_root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_run_generation_job_marks_job_failed_when_worker_bootstrap_crashes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    configure_sqlite_env(monkeypatch, tmp_path)

    from app.config import load_settings

    settings = load_settings()
    engine, session_factory = create_engine_and_session_factory(settings)
    Base.metadata.create_all(engine)

    with session_factory() as db:
        user = User(
            email="worker-failure@example.com",
            password_hash="hashed",
            pen_name="故障作者",
            access_token="worker-token",
        )
        db.add(user)
        db.flush()

        job = GenerationJob(
            user=user,
            job_type="outline",
            status="queued",
            progress=0,
            input_snapshot={},
        )
        db.add(job)
        db.commit()
        job_id = job.id

    worker_module = importlib.import_module("app.worker")
    worker_module._workflow_runner = None

    def boom():
        raise RuntimeError("worker bootstrap exploded")

    monkeypatch.setattr(worker_module, "get_workflow_runner", boom)

    with pytest.raises(RuntimeError, match="worker bootstrap exploded"):
        worker_module.run_generation_job(job_id)

    with session_factory() as db:
        refreshed = db.get(GenerationJob, job_id)
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert refreshed.error_message is not None
        assert "worker bootstrap exploded" in refreshed.error_message
        assert "Worker failed before the workflow could complete" in refreshed.status_message
