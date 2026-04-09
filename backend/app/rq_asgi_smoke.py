from __future__ import annotations

import argparse
import asyncio
import json
import random
import string
import time

import httpx


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def wait_for_job(client: httpx.AsyncClient, token: str, job_id: int, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_payload = None
    while time.time() < deadline:
        response = await client.get(f"/api/jobs/{job_id}", headers=auth_headers(token))
        response.raise_for_status()
        last_payload = response.json()
        print(
            json.dumps(
                {
                    "job_id": job_id,
                    "status": last_payload["status"],
                    "progress": last_payload["progress"],
                    "error_message": last_payload["error_message"],
                    "result": last_payload["result"],
                },
                ensure_ascii=False,
            )
        )
        if last_payload["status"] in {"completed", "failed", "awaiting_user"}:
            return last_payload
        await asyncio.sleep(2)
    raise RuntimeError(f"job {job_id} did not reach a terminal state in time: {last_payload}")


async def run_flow(timeout: float) -> None:
    from .main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    email = f"rq-asgi-smoke-{int(time.time())}-{''.join(random.choices(string.ascii_lowercase, k=4))}@example.com"

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=120.0) as client:
        response = await client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "supersecret",
                "pen_name": "QueueSmoke",
            },
        )
        response.raise_for_status()
        token = response.json()["token"]
        headers = auth_headers(token)

        response = await client.post(
            "/api/projects",
            headers=headers,
            json={
                "title": "Redis Queue ASGI Smoke",
                "genre": "都市悬疑",
                "tone": "克制、电影感、紧绷",
                "era": "当代",
                "target_chapter_count": 2,
                "target_length": "2章，测试节奏",
                "logline": "用于验证 Redis + RQ worker 是否通过真实业务链路跑通。",
            },
        )
        response.raise_for_status()
        project_id = response.json()["id"]

        response = await client.post(
            f"/api/projects/{project_id}/characters",
            headers=headers,
            data={
                "name": "沈砚",
                "role": "深夜电台主持人",
                "personality": "克制、敏锐、情绪压在行动后面",
                "goal": "查清午夜来电背后的真实意图",
                "speech_style": "短句、留白多、追问时锋利",
                "appearance": "深色外套，偏瘦，眼神疲惫但稳定",
                "relationships": "与旧搭档互不信任却仍被迫合作",
            },
        )
        response.raise_for_status()

        response = await client.post(
            f"/api/projects/{project_id}/generate/outline",
            headers=headers,
            json={},
        )
        response.raise_for_status()
        outline_job = await wait_for_job(client, token, response.json()["id"], timeout)
        if outline_job["status"] != "completed":
            raise RuntimeError(f"outline failed: {json.dumps(outline_job, ensure_ascii=False)}")

        response = await client.get(f"/api/projects/{project_id}", headers=headers)
        response.raise_for_status()
        chapter_id = response.json()["chapters"][0]["id"]

        response = await client.post(
            f"/api/chapters/{chapter_id}/generate-draft",
            headers=headers,
            json={},
        )
        response.raise_for_status()
        draft_job = await wait_for_job(client, token, response.json()["id"], timeout)
        if draft_job["status"] != "completed":
            raise RuntimeError(f"draft failed: {json.dumps(draft_job, ensure_ascii=False)}")

    print("rq asgi smoke ok")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an ASGI smoke test that uses the real RQ + Redis worker.")
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(run_flow(args.timeout))
    except Exception as exc:  # pragma: no cover - manual smoke utility
        print(f"rq asgi smoke failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
