from __future__ import annotations

import argparse
import asyncio
import json
import os
import time

import httpx
from sqlalchemy import text

from .config import Settings, load_settings
from .database import create_engine_and_session_factory


def freeze_runtime_environment(settings: Settings) -> dict[str, str]:
    return {
        "STORY_PLATFORM_SKIP_DOTENV": "1",
        "STORY_PLATFORM_DB_URL": settings.database_url,
        "STORY_PLATFORM_STORAGE_DIR": str(settings.storage_dir),
        "STORY_PLATFORM_EXPORT_DIR": str(settings.export_dir),
        "OPENAI_BASE_URL": settings.openai_base_url or "",
        "OPENAI_API_KEY": settings.openai_api_key or "",
        "OPENAI_MODEL": settings.openai_model,
        "STORY_AGENT_PLANNER_MODEL": settings.story_agent_planner_model or "",
        "STORY_AGENT_WRITER_MODEL": settings.story_agent_writer_model or "",
        "STORY_AGENT_REVIEWER_MODEL": settings.story_agent_reviewer_model or "",
        "STORY_AGENT_VISUAL_MODEL": settings.story_agent_visual_model or "",
        "STORY_AGENT_IMAGE_MODEL": settings.story_agent_image_model or "",
        "STORY_AGENT_IMAGE_SIZE": settings.story_agent_image_size,
        "STORY_AGENT_TIMEOUT_SECONDS": str(settings.story_agent_timeout_seconds),
        "STORY_REVIEW_INTERVENTION_MIN_SEVERITY": settings.story_review_intervention_min_severity,
        "STORY_PLATFORM_QUEUE_BACKEND": "inline",
    }


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def resolve_project_auth(project_id: int) -> tuple[int, str]:
    settings = load_settings()
    engine, session_factory = create_engine_and_session_factory(settings)
    try:
        with session_factory() as session:
            row = session.execute(
                text(
                    """
                    select projects.owner_id, users.access_token
                    from projects
                    join users on users.id = projects.owner_id
                    where projects.id = :project_id
                    """
                ),
                {"project_id": project_id},
            ).first()
            if not row:
                raise RuntimeError(f"Project {project_id} was not found in the current database.")
            if not row.access_token:
                raise RuntimeError(f"Project owner for project {project_id} does not have an active access token.")
            return int(row.owner_id), str(row.access_token)
    finally:
        engine.dispose()


async def wait_for_job(client: httpx.AsyncClient, token: str, job_id: int, timeout: float) -> dict:
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        response = await client.get(f"/api/jobs/{job_id}", headers=auth_headers(token))
        response.raise_for_status()
        latest = response.json()
        print(
            "JOB_STATUS",
            json.dumps(
                {
                    "status": latest["status"],
                    "progress": latest["progress"],
                    "status_message": latest["status_message"],
                    "error_message": latest["error_message"],
                    "result": latest["result"],
                },
                ensure_ascii=False,
            ),
        )
        if latest["status"] in {"completed", "failed", "awaiting_user"}:
            return latest
        await asyncio.sleep(0.25)
    raise RuntimeError(f"Job {job_id} did not reach a terminal state in time: {latest}")


async def run_export_delivery_smoke(project_id: int, formats: list[str], timeout: float) -> dict:
    settings = load_settings()
    os.environ.update(freeze_runtime_environment(settings))

    # Import after freezing the environment so create_app uses the inline queue backend.
    from .main import create_app

    _, token = resolve_project_auth(project_id)

    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=120.0) as client:
        response = await client.post(
            f"/api/projects/{project_id}/exports",
            headers=auth_headers(token),
            json={"formats": formats},
        )
        response.raise_for_status()
        job = response.json()
        print("JOB_CREATED", json.dumps(job, ensure_ascii=False))

        result = await wait_for_job(client, token, int(job["id"]), timeout)
        if result["status"] != "completed":
            raise RuntimeError(f"Export job did not complete successfully: {json.dumps(result, ensure_ascii=False)}")

        export_id = int(result["result"]["export_id"])
        export_response = await client.get(f"/api/exports/{export_id}", headers=auth_headers(token))
        export_response.raise_for_status()
        export_payload = export_response.json()
        print("EXPORT", json.dumps(export_payload, ensure_ascii=False))

        downloads = []
        for file_info in export_payload["files"]:
            url = file_info.get("url")
            if not url:
                continue
            download = await client.get(url)
            download.raise_for_status()
            downloads.append(
                {
                    "format": file_info["format"],
                    "status_code": download.status_code,
                    "bytes": len(download.content),
                }
            )
            print("DOWNLOAD", json.dumps(downloads[-1], ensure_ascii=False))

        return {"job": job, "result": result, "export": export_payload, "downloads": downloads}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trigger a real export delivery smoke against the current Postgres runtime and verify downloads."
    )
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--formats", nargs="+", default=["pdf", "docx"])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = asyncio.run(run_export_delivery_smoke(args.project_id, args.formats, args.timeout))
    except Exception as exc:  # pragma: no cover - manual smoke utility
        print(f"export delivery smoke failed: {exc}")
        return 1

    summary = {
        "project_id": args.project_id,
        "export_id": result["export"]["id"],
        "quality_status": result["export"]["delivery_summary"]["quality_status"],
        "downloads": result["downloads"],
    }
    print("export delivery smoke ok")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
