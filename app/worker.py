from __future__ import annotations

import importlib


def _load_backend_worker_module():
    providers_module = importlib.import_module("backend.app.providers")
    workflow_module = importlib.import_module("backend.app.workflow")
    worker_module = importlib.import_module("backend.app.worker")
    importlib.reload(providers_module)
    importlib.reload(workflow_module)
    return importlib.reload(worker_module)


def run_generation_job(job_id: int):
    return _load_backend_worker_module().run_generation_job(job_id)


def main():
    return _load_backend_worker_module().main()


__all__ = ["main", "run_generation_job"]


if __name__ == "__main__":
    main()
