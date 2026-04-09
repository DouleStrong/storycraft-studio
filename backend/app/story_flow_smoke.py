from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
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
        if last_payload["status"] in {"completed", "failed"}:
            return last_payload
        await asyncio.sleep(0.25)
    raise RuntimeError(f"job {job_id} did not finish in time: {last_payload}")


async def run_flow(chapter_count: int, candidate_count: int, timeout: float) -> dict:
    with tempfile.TemporaryDirectory(prefix="storycraft-real-smoke-") as tmpdir:
        os.environ["STORY_PLATFORM_SKIP_DOTENV"] = "1"
        os.environ["STORY_PLATFORM_ALLOW_SQLITE"] = "1"
        os.environ["STORY_PLATFORM_DB_URL"] = f"sqlite:///{tmpdir}/storycraft_smoke.db"
        os.environ["STORY_PLATFORM_STORAGE_DIR"] = f"{tmpdir}/storage"
        os.environ["STORY_PLATFORM_EXPORT_DIR"] = f"{tmpdir}/exports"
        os.environ["STORY_PLATFORM_QUEUE_BACKEND"] = "inline"

        from app.main import create_app

        app = create_app()
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            email = f"smoke-{int(time.time())}@example.com"
            register = await client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": "supersecret",
                    "pen_name": "SmokeAuthor",
                },
            )
            register.raise_for_status()
            token = register.json()["token"]

            project_response = await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "Midnight Frequency",
                    "genre": "Urban suspense short drama",
                    "tone": "restrained, cinematic, emotionally tense",
                    "era": "Contemporary",
                    "target_length": f"{chapter_count} chapters",
                    "logline": "A late-night radio host receives a call from a missing witness and is forced to reopen an old case with a former partner.",
                },
            )
            project_response.raise_for_status()
            project = project_response.json()
            project_id = project["id"]

            character_response = await client.post(
                f"/api/projects/{project_id}/characters",
                headers=auth_headers(token),
                data={
                    "name": "Shen Yan",
                    "role": "Late-night radio host",
                    "personality": "calm, observant, emotionally stubborn",
                    "goal": "Find the truth behind the midnight caller and confirm whether the missing witness is alive",
                    "speech_style": "short sentences, dry understatement, deliberate pauses",
                    "appearance": "lean frame, dark coat, tired eyes, steady gaze",
                    "relationships": "still affected by a former partner he no longer trusts; unexpectedly protective toward the caller",
                },
            )
            character_response.raise_for_status()
            character = character_response.json()

            outline_job = await client.post(
                f"/api/projects/{project_id}/generate/outline",
                headers=auth_headers(token),
                json={"chapter_count": chapter_count},
            )
            outline_job.raise_for_status()
            outline_result = await wait_for_job(client, token, outline_job.json()["id"], timeout)
            if outline_result["status"] != "completed":
                raise RuntimeError(f"outline failed: {json.dumps(outline_result, ensure_ascii=False)}")

            project_detail = await client.get(f"/api/projects/{project_id}", headers=auth_headers(token))
            project_detail.raise_for_status()
            first_chapter = project_detail.json()["chapters"][0]
            chapter_id = first_chapter["id"]

            draft_job = await client.post(
                f"/api/chapters/{chapter_id}/generate-draft",
                headers=auth_headers(token),
                json={},
            )
            draft_job.raise_for_status()
            draft_result = await wait_for_job(client, token, draft_job.json()["id"], timeout)
            if draft_result["status"] != "completed":
                raise RuntimeError(f"draft failed: {json.dumps(draft_result, ensure_ascii=False)}")

            scenes_job = await client.post(
                f"/api/chapters/{chapter_id}/generate-scenes",
                headers=auth_headers(token),
                json={},
            )
            scenes_job.raise_for_status()
            scenes_result = await wait_for_job(client, token, scenes_job.json()["id"], timeout)
            if scenes_result["status"] != "completed":
                raise RuntimeError(f"scenes failed: {json.dumps(scenes_result, ensure_ascii=False)}")

            project_with_scenes = await client.get(f"/api/projects/{project_id}", headers=auth_headers(token))
            project_with_scenes.raise_for_status()
            first_scene = project_with_scenes.json()["chapters"][0]["scenes"][0]
            scene_id = first_scene["id"]

            illustration_job = await client.post(
                f"/api/scenes/{scene_id}/generate-illustrations",
                headers=auth_headers(token),
                json={"candidate_count": candidate_count},
            )
            illustration_job.raise_for_status()
            illustration_result = await wait_for_job(client, token, illustration_job.json()["id"], timeout)
            if illustration_result["status"] != "completed":
                raise RuntimeError(f"illustrations failed: {json.dumps(illustration_result, ensure_ascii=False)}")

            final_project_response = await client.get(f"/api/projects/{project_id}", headers=auth_headers(token))
            final_project_response.raise_for_status()
            final_project = final_project_response.json()
            final_chapter = final_project["chapters"][0]
            final_scene = final_chapter["scenes"][0]

            return {
                "character_visual_profile_present": bool(character.get("visual_profile")),
                "model_ids": {
                    "outline": outline_result["result"].get("model_ids", {}),
                    "draft": draft_result["result"].get("model_ids", {}),
                    "scenes": scenes_result["result"].get("model_ids", {}),
                    "illustrations": illustration_result["result"].get("model_ids", {}),
                },
                "chapter_titles": [chapter["title"] for chapter in final_project["chapters"]],
                "draft_block_preview": final_chapter["narrative_blocks"][0]["content"][:240],
                "continuity_note_preview": (final_chapter.get("continuity_notes") or [""])[0][:240],
                "scene_count": len(final_chapter["scenes"]),
                "scene_title": final_scene["title"],
                "visual_prompt_preview": (final_scene.get("visual_prompt") or "")[:320],
                "illustration_count": len(final_scene["illustrations"]),
            }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a real StoryCraft Studio flow smoke against the configured text provider.")
    parser.add_argument("--chapter-count", type=int, default=3)
    parser.add_argument("--candidate-count", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=90.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        result = asyncio.run(run_flow(args.chapter_count, args.candidate_count, args.timeout))
    except Exception as exc:  # pragma: no cover - manual smoke utility
        print(f"story flow smoke failed: {exc}", file=sys.stderr)
        return 1

    print("story flow smoke ok")
    print(f"character visual profile present: {result['character_visual_profile_present']}")
    print(f"model ids: {json.dumps(result['model_ids'], ensure_ascii=False)}")
    print(f"chapter titles: {json.dumps(result['chapter_titles'], ensure_ascii=False)}")
    print(f"draft block preview: {json.dumps(result['draft_block_preview'], ensure_ascii=False)}")
    print(f"continuity note preview: {json.dumps(result['continuity_note_preview'], ensure_ascii=False)}")
    print(f"scene count: {result['scene_count']}")
    print(f"scene title: {json.dumps(result['scene_title'], ensure_ascii=False)}")
    print(f"visual prompt preview: {json.dumps(result['visual_prompt_preview'], ensure_ascii=False)}")
    print(f"illustration count: {result['illustration_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
