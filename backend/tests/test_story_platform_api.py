import asyncio
import base64
import os
import time
from pathlib import Path

import httpx
import pytest

from app.models import AgentRun, GenerationJob, User
from app.providers import StructuredAgentResponse


TEST_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\x1dc`\x00\x00"
    b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)

VALID_GENERATED_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4HWP4DwQACfsDfQ6OeuQAAAAASUVORK5CYII="
)


class FakeStoryAgents:
    image_model = "fake-image"

    def build_character_profile(self, project, character, on_stream=None):
        return StructuredAgentResponse(
            payload={
                "signature_line": f"{character.name}每次沉默，都是在为下一句更重的话蓄力。",
                "visual_anchor": f"{character.name}保持{character.appearance}的核心辨识度，并强化{character.role}的职业锋利感。",
                "signature_palette": "深青、雾银、暖白",
                "silhouette_notes": f"轮廓重点突出{character.appearance.split('，')[0]}与角色身份。",
                "wardrobe_notes": f"服装延续{character.appearance}，并呼应角色目标“{character.goal}”。",
                "atmosphere_notes": f"镜头氛围围绕{character.personality}展开，口吻保持{character.speech_style}。",
            },
            raw_text="{}",
            trace={"agent": "visual-profile", "model": "fake-visual", "attempts": 1},
        )

    def plan_outline(self, project, chapter_count, extra_guidance="", anchor_chapter=None, on_stream=None):
        chapters = []
        for index in range(chapter_count):
            chapter_no = index + 1
            chapters.append(
                {
                    "order_index": chapter_no,
                    "title": f"第{chapter_no}章·轨道偏移",
                    "summary": f"第{chapter_no}章围绕《{project.title}》的核心矛盾继续推进，人物关系与真相线并行加压。",
                    "chapter_goal": f"把第{chapter_no}章的人物抉择与外部危机绑定起来。",
                    "hook": f"在第{chapter_no}章结尾留下新的因果悬念，而不是重复上一章的疑问。",
                }
            )
        return StructuredAgentResponse(
            payload={
                "story_bible_updates": {
                    "world_notes": f"《{project.title}》发生在{project.era}，重点描写制度缝隙中的个人选择。",
                    "style_notes": f"{project.tone}，强调角色压抑情绪与行动后果。",
                    "writing_rules": ["冲突必须由角色选择推动", "每章结尾保留牵引力", "对白服务人物关系变化"],
                },
                "chapters": chapters,
            },
            raw_text="{}",
            trace={"agent": "planner", "model": "fake-planner", "attempts": 1},
        )

    def write_chapter_draft(self, project, chapter, previous_chapters, extra_guidance="", on_stream=None):
        previous_count = len(previous_chapters)
        return StructuredAgentResponse(
            payload={
                "narrative_blocks": [
                    f"{chapter.summary}。这是基于{project.tone}推进的初稿版本，前序章节数量为{previous_count}。",
                    f"这一章里，人物行动必须服务“{chapter.chapter_goal}”，并让关系张力自然外显。",
                    f"章末收束到“{chapter.hook}”，但保留人物情绪余波，而不是只抛设问。",
                ]
            },
            raw_text="{}",
            trace={"agent": "writer", "model": "fake-writer", "attempts": 1},
        )

    def review_chapter_draft(self, project, chapter, draft_payload, on_stream=None):
        revised = [f"[审校后] {item}" for item in draft_payload["narrative_blocks"]]
        return StructuredAgentResponse(
            payload={
                "issues": ["第二段情绪递进还可以更具体。"],
                "continuity_notes": [
                    f"Reviewer：确保第{chapter.order_index}章延续既定口吻，不要让人物忽然解释过度。",
                    "Reviewer：保持称呼稳定，并让悬念与角色动机直接相关。",
                ],
                "revised_narrative_blocks": revised,
            },
            raw_text="{}",
            trace={"agent": "reviewer", "model": "fake-reviewer", "attempts": 1},
        )

    def write_chapter_scenes(self, project, chapter, previous_chapters, extra_guidance="", on_stream=None):
        return StructuredAgentResponse(
            payload={
                "scenes": [
                    {
                        "title": "旧楼档案室",
                        "scene_type": "INT",
                        "location": "旧楼档案室",
                        "time_of_day": "NIGHT",
                        "cast_names": ["林听", "顾昼"],
                        "objective": "让角色确认线索并暴露彼此的试探。",
                        "emotional_tone": "压抑而锋利",
                        "dialogues": [
                            {"speaker": "林听", "parenthetical": "压低声音", "content": "你把线索藏得太深了。"},
                            {"speaker": "顾昼", "parenthetical": "没有回头", "content": "我只是比你更早知道代价。"},
                        ],
                    },
                    {
                        "title": "凌晨街口",
                        "scene_type": "EXT",
                        "location": "广播站外街口",
                        "time_of_day": "DAWN",
                        "cast_names": ["林听", "沈苒"],
                        "objective": "让同盟关系第一次显出裂口。",
                        "emotional_tone": "疲惫又克制",
                        "dialogues": [
                            {"speaker": "沈苒", "parenthetical": "看向空街", "content": "你不是不相信我，你是不敢太早相信任何人。"},
                        ],
                    },
                    {
                        "title": "临时指挥点",
                        "scene_type": "INT",
                        "location": "废弃商场监控室",
                        "time_of_day": "MORNING",
                        "cast_names": ["林听", "顾昼", "沈苒"],
                        "objective": "让三人决定下一步主动出击的方向。",
                        "emotional_tone": "冷静但逼近失控",
                        "dialogues": [
                            {"speaker": "林听", "parenthetical": "", "content": "这次不等他们来找我们。"},
                        ],
                    },
                ]
            },
            raw_text="{}",
            trace={"agent": "writer", "model": "fake-writer", "attempts": 1},
        )

    def review_chapter_scenes(self, project, chapter, scenes_payload, on_stream=None):
        revised_scenes = []
        for scene in scenes_payload["scenes"]:
            revised_scene = dict(scene)
            revised_scene["objective"] = f"[审校后] {scene['objective']}"
            revised_scenes.append(revised_scene)
        return StructuredAgentResponse(
            payload={
                "issues": ["第二场的情绪过渡需要更清晰。"],
                "continuity_notes": [
                    f"Reviewer：第{chapter.order_index}章场景衔接应维持相同时间压力。",
                ],
                "revised_scenes": revised_scenes,
            },
            raw_text="{}",
            trace={"agent": "reviewer", "model": "fake-reviewer", "attempts": 1},
        )

    def build_visual_prompt(self, project, scene, characters, extra_guidance="", on_stream=None):
        cast_summary = " | ".join(character.name for character in characters) or "角色保持既有设定"
        guidance_suffix = f", guidance={extra_guidance}" if extra_guidance else ""
        return StructuredAgentResponse(
            payload={
                "prompt_text": (
                    f"{project.title} cinematic still, {scene.location}, {scene.time_of_day}, "
                    f"tone={scene.emotional_tone}, cast={cast_summary}, restrained editorial realism{guidance_suffix}"
                ),
                "style_tags": ["cinematic", "editorial", "restrained"],
                "shot_notes": ["保持角色视觉锚点一致", "避免过度奇观化"],
            },
            raw_text="{}",
            trace={"agent": "visual-prompt", "model": "fake-visual", "attempts": 1},
        )

    def generate_scene_illustrations(
        self,
        project,
        scene,
        characters,
        *,
        prompt_text,
        candidate_count,
        extra_guidance="",
        on_stream=None,
    ):
        if on_stream is not None:
            on_stream({"text": f"正在为 {scene.title} 渲染 {candidate_count} 张剧照候选。"})
        return StructuredAgentResponse(
            payload={
                "generated_images": [
                    {
                        "payload_bytes": VALID_GENERATED_PNG_BYTES,
                        "media_type": "image/png",
                        "revised_prompt": f"{prompt_text} / candidate {index}",
                    }
                    for index in range(1, candidate_count + 1)
                ],
                "public_notes": [
                    "正在保持角色外貌锚点和场景气压。",
                    "已把剧照候选交给资产存储层。",
                ],
                "reference_feedback": {
                    "used_scene_canonical": any(item.is_canonical for item in scene.illustrations),
                    "canonical_illustration_id": next((item.id for item in scene.illustrations if item.is_canonical), None),
                    "canonical_candidate_index": next((item.candidate_index for item in scene.illustrations if item.is_canonical), None),
                    "extra_guidance": extra_guidance,
                },
            },
            raw_text="",
            trace={"agent": "image-generation", "model": "fake-image", "attempts": 1},
        )


class SparseReviewNotesAgents(FakeStoryAgents):
    def review_chapter_draft(self, project, chapter, draft_payload, on_stream=None):
        revised = [f"[reviewed] {item}" for item in draft_payload["narrative_blocks"]]
        return StructuredAgentResponse(
            payload={
                "issues": ["Keep the character naming consistent."],
                "continuity_notes": [],
                "revised_narrative_blocks": revised,
            },
            raw_text="{}",
            trace={"agent": "reviewer", "model": "fake-reviewer", "attempts": 1},
        )

    def review_chapter_scenes(self, project, chapter, scenes_payload, on_stream=None):
        return StructuredAgentResponse(
            payload={
                "issues": ["Clarify the pressure from scene to scene."],
                "continuity_notes": [],
                "revised_scenes": scenes_payload["scenes"],
            },
            raw_text="{}",
            trace={"agent": "reviewer", "model": "fake-reviewer", "attempts": 1},
        )


class InterventionStoryAgents(FakeStoryAgents):
    def __init__(self):
        self.draft_retry_seen = False

    def review_chapter_draft(self, project, chapter, draft_payload, on_stream=None):
        if not self.draft_retry_seen:
            return StructuredAgentResponse(
                payload={
                    "issues": ["The emotional turn lands too abruptly."],
                    "continuity_notes": ["Reviewer：The chapter needs a more deliberate emotional turn."],
                    "decision": "rewrite_writer",
                    "decision_reason": "The first pass skips an important relationship beat.",
                    "suggested_guidance": "Add a more explicit emotional transition before the chapter hook.",
                    "revised_narrative_blocks": [],
                },
                raw_text="{}",
                trace={"agent": "reviewer", "model": "fake-reviewer", "attempts": 1},
            )

        return StructuredAgentResponse(
            payload={
                "issues": [],
                "continuity_notes": ["Reviewer：The emotional turn is now grounded in character motivation."],
                "decision": "accept",
                "decision_reason": "The rewrite addresses the missing emotional bridge.",
                "suggested_guidance": "",
                "revised_narrative_blocks": [f"[accepted] {item}" for item in draft_payload["narrative_blocks"]],
            },
            raw_text="{}",
            trace={"agent": "reviewer", "model": "fake-reviewer", "attempts": 1},
        )


class ModerateAutoApplyStoryAgents(FakeStoryAgents):
    def review_chapter_draft(self, project, chapter, draft_payload, on_stream=None):
        return StructuredAgentResponse(
            payload={
                "issues": ["The emotional bridge could be more explicit before the hook."],
                "continuity_notes": ["Reviewer：已自动补强情绪过渡，不需要打断作者继续创作。"],
                "decision": "rewrite_writer",
                "severity": "moderate",
                "decision_reason": "The draft needs a clearer emotional landing, but the issue is safely fixable in the same pass.",
                "suggested_guidance": "Only escalate when the chapter cannot be safely repaired in one review pass.",
                "revised_narrative_blocks": [f"[auto-reviewed] {item}" for item in draft_payload["narrative_blocks"]],
            },
            raw_text="{}",
            trace={"agent": "reviewer", "model": "fake-reviewer", "attempts": 1},
        )


class CanonicalFeedbackAgents(FakeStoryAgents):
    def build_visual_prompt(self, project, scene, characters, extra_guidance="", on_stream=None):
        canonical = next((item for item in scene.illustrations if item.is_canonical), None)
        prompt_segments = [
            f"{project.title} cinematic still",
            scene.location,
            scene.time_of_day,
            f"tone={scene.emotional_tone}",
        ]
        if canonical:
            prompt_segments.append(f"reference={canonical.prompt_text}")
        if extra_guidance:
            prompt_segments.append(f"guidance={extra_guidance}")
        return StructuredAgentResponse(
            payload={
                "prompt_text": " | ".join(prompt_segments),
                "style_tags": ["cinematic", "continuity-aware"],
                "shot_notes": ["优先继承主图里的角色识别度"],
                "public_notes": ["正在参考已选主图，控制下一轮镜头一致性。"],
            },
            raw_text="{}",
            trace={"agent": "visual-prompt", "model": "fake-visual", "attempts": 1},
        )


class ExplodingImageAgents(FakeStoryAgents):
    def generate_scene_illustrations(
        self,
        project,
        scene,
        characters,
        *,
        prompt_text,
        candidate_count,
        extra_guidance="",
        on_stream=None,
    ):
        if on_stream is not None:
            on_stream({"text": "正在尝试连接图像模型。", "progress": 74})
        raise RuntimeError("image provider exploded")


class ProbeTaskQueue:
    def __init__(self, probe_result=None):
        self.enqueued_job_ids = []
        self.probe_result = probe_result

    def enqueue(self, job_id):
        self.enqueued_job_ids.append(job_id)

    def probe(self, job_id):
        return self.probe_result


def create_client(tmp_path, monkeypatch, story_agents=None, task_queue=None):
    base_dir = tmp_path / "runtime"
    monkeypatch.setenv("STORY_PLATFORM_SKIP_DOTENV", "1")
    monkeypatch.setenv("STORY_PLATFORM_ALLOW_SQLITE", "1")
    monkeypatch.setenv("STORY_PLATFORM_DB_URL", f"sqlite:///{base_dir / 'story.db'}")
    monkeypatch.setenv("STORY_PLATFORM_STORAGE_DIR", str(base_dir / "storage"))
    monkeypatch.setenv("STORY_PLATFORM_EXPORT_DIR", str(base_dir / "exports"))
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("STORY_AGENT_PLANNER_MODEL", raising=False)
    monkeypatch.delenv("STORY_AGENT_WRITER_MODEL", raising=False)
    monkeypatch.delenv("STORY_AGENT_REVIEWER_MODEL", raising=False)
    monkeypatch.delenv("STORY_AGENT_VISUAL_MODEL", raising=False)
    monkeypatch.delenv("STORY_AGENT_TIMEOUT_SECONDS", raising=False)

    from app.main import create_app

    return create_app(story_agents=story_agents, task_queue=task_queue)


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


async def register_user(client, email="author@example.com", password="supersecret", pen_name="青灯"):
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "pen_name": pen_name},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["token"]
    return payload


async def wait_for_job(client, token, job_id, timeout=8):
    deadline = time.time() + timeout
    last_payload = None
    while time.time() < deadline:
        response = await client.get(f"/api/jobs/{job_id}", headers=auth_headers(token))
        assert response.status_code == 200, response.text
        last_payload = response.json()
        if last_payload["status"] in {"completed", "failed"}:
            return last_payload
        await asyncio.sleep(0.1)
    raise AssertionError(f"job {job_id} did not complete in time: {last_payload}")


async def wait_for_terminal_job(client, token, job_id, timeout=8):
    deadline = time.time() + timeout
    last_payload = None
    while time.time() < deadline:
        response = await client.get(f"/api/jobs/{job_id}", headers=auth_headers(token))
        assert response.status_code == 200, response.text
        last_payload = response.json()
        if last_payload["status"] in {"completed", "failed", "awaiting_user"}:
            return last_payload
        await asyncio.sleep(0.1)
    raise AssertionError(f"job {job_id} did not reach a terminal state in time: {last_payload}")


@pytest.mark.anyio
async def test_user_can_register_login_and_create_project(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)

        login = await client.post(
            "/api/auth/login",
            json={"email": "author@example.com", "password": "supersecret"},
        )
        assert login.status_code == 200, login.text
        token = login.json()["token"]

        create_project = await client.post(
            "/api/projects",
            headers=auth_headers(token),
            json={
                "title": "夜色折叠时",
                "genre": "都市悬疑",
                "tone": "克制、电影感、带悬念",
                "era": "当代",
                "target_length": "12章",
                "logline": "一名失忆摄影师与地下情报贩子在城市迷局中追索真相。",
            },
        )
        assert create_project.status_code == 201, create_project.text
        project = create_project.json()
        assert project["title"] == "夜色折叠时"
        assert project["status"] == "draft"

        projects = await client.get("/api/projects", headers=auth_headers(token))
        assert projects.status_code == 200, projects.text
        assert len(projects.json()) == 1


@pytest.mark.anyio
async def test_outline_defaults_to_project_target_chapter_count(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=FakeStoryAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        create_project = await client.post(
            "/api/projects",
            headers=auth_headers(token),
            json={
                "title": "站台尽头的回声",
                "genre": "都市悬疑",
                "tone": "克制、夜行感强",
                "era": "当代",
                "target_chapter_count": 4,
                "target_length": "4章，短剧节奏",
                "logline": "失踪列车员留下的录音，把主角重新拉回一座被封存的旧站台。",
            },
        )
        assert create_project.status_code == 201, create_project.text

        outline_job = await client.post(
            f"/api/projects/{create_project.json()['id']}/generate/outline",
            headers=auth_headers(token),
            json={},
        )
        assert outline_job.status_code == 202, outline_job.text
        outline_result = await wait_for_job(client, token, outline_job.json()["id"])
        assert outline_result["status"] == "completed", outline_result
        assert outline_result["result"]["chapter_count"] == 4

        project_detail = await client.get(
            f"/api/projects/{create_project.json()['id']}",
            headers=auth_headers(token),
        )
        assert project_detail.status_code == 200, project_detail.text
        assert len(project_detail.json()["chapters"]) == 4


@pytest.mark.anyio
async def test_missing_llm_configuration_keeps_character_creation_but_fails_jobs(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "没有钥匙的夜晚",
                    "genre": "都市悬疑",
                    "tone": "克制、压迫感强",
                    "era": "当代",
                    "target_length": "6章",
                    "logline": "一次失败的追索，让主角意识到自己正处在别人设计的剧场里。",
                },
            )
        ).json()

        create_character = await client.post(
            f"/api/projects/{project['id']}/characters",
            headers=auth_headers(token),
            data={
                "name": "钟迟",
                "role": "夜班记者",
                "personality": "敏锐、寡言、压着情绪走",
                "goal": "查清一宗看似普通的坠楼案",
                "speech_style": "短句、克制、追问时锋利",
                "appearance": "深色外套，黑眼圈明显，肩背总有一点绷着",
                "relationships": "与警方线人若即若离，与同事长期互相提防",
            },
        )
        assert create_character.status_code == 201, create_character.text
        assert create_character.json()["visual_profile"] is None

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={"chapter_count": 3},
            )
        ).json()
        outline_result = await wait_for_job(client, token, outline_job["id"])
        assert outline_result["status"] == "failed", outline_result
        assert "OPENAI_BASE_URL" in outline_result["error_message"]


@pytest.mark.anyio
async def test_job_detail_syncs_failed_queue_probe_back_to_database(tmp_path, monkeypatch):
    probe_queue = ProbeTaskQueue(
        probe_result={
            "status": "failed",
            "error_message": "Invalid attribute name: run_generation_job",
            "status_message": "RQ worker failed before the workflow could start.",
        }
    )
    app = create_client(tmp_path, monkeypatch, story_agents=FakeStoryAgents(), task_queue=probe_queue)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        create_project = await client.post(
            "/api/projects",
            headers=auth_headers(token),
            json={
                "title": "故障回声",
                "genre": "都市悬疑",
                "tone": "克制、电影感",
                "era": "当代",
                "target_chapter_count": 3,
                "target_length": "3章，短剧节奏",
                "logline": "一次本该顺利的生成任务，被错误地困在了排队状态里。",
            },
        )
        assert create_project.status_code == 201, create_project.text

        outline_job = await client.post(
            f"/api/projects/{create_project.json()['id']}/generate/outline",
            headers=auth_headers(token),
            json={},
        )
        assert outline_job.status_code == 202, outline_job.text
        job_id = outline_job.json()["id"]

        detail = await client.get(f"/api/jobs/{job_id}", headers=auth_headers(token))
        assert detail.status_code == 200, detail.text
        payload = detail.json()
        assert payload["status"] == "failed"
        assert "run_generation_job" in payload["error_message"]
        assert "RQ worker failed before the workflow could start." in payload["status_message"]


@pytest.mark.anyio
async def test_failed_image_generation_marks_agent_run_failed(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=ExplodingImageAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "图像失败回显",
                    "genre": "校园悬疑",
                    "tone": "克制、压抑",
                    "era": "当代",
                    "target_chapter_count": 2,
                    "target_length": "2章，测试节奏",
                    "logline": "一次剧照生成失败，需要准确回显到 agent trace。",
                },
            )
        ).json()

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        outline_result = await wait_for_job(client, token, outline_job["id"])
        assert outline_result["status"] == "completed"

        project_detail = await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        chapter_id = project_detail.json()["chapters"][0]["id"]

        scenes_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-scenes",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        scenes_result = await wait_for_job(client, token, scenes_job["id"])
        assert scenes_result["status"] == "completed"

        project_detail = await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        scene_id = project_detail.json()["chapters"][0]["scenes"][0]["id"]

        illustration_job = (
            await client.post(
                f"/api/scenes/{scene_id}/generate-illustrations",
                headers=auth_headers(token),
                json={"candidate_count": 2},
            )
        ).json()
        illustration_result = await wait_for_job(client, token, illustration_job["id"])
        assert illustration_result["status"] == "failed"
        assert "image provider exploded" in illustration_result["error_message"]

        detail = await client.get(f"/api/jobs/{illustration_job['id']}", headers=auth_headers(token))
        payload = detail.json()
        image_run = next(run for run in payload["agent_runs"] if run["step_key"] == "image_generation")
        assert image_run["status"] == "failed"
        assert "image provider exploded" in image_run["error_message"]
        assert "正在尝试连接图像模型" in image_run["stream_text"]


@pytest.mark.anyio
async def test_chapter_lock_endpoint_can_unlock(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=FakeStoryAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "雪夜来信",
                    "genre": "悬疑",
                    "tone": "冷静、压抑",
                    "era": "当代",
                    "target_chapter_count": 2,
                    "target_length": "2章",
                    "logline": "一封迟到十年的信在雪夜被送回原地址。",
                },
            )
        ).json()

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        outline_result = await wait_for_job(client, token, outline_job["id"])
        assert outline_result["status"] == "completed", outline_result

        project_detail = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        chapter_id = project_detail["chapters"][0]["id"]

        lock_response = await client.patch(
            f"/api/chapters/{chapter_id}/lock",
            headers=auth_headers(token),
            json={"locked": True},
        )
        assert lock_response.status_code == 200, lock_response.text
        assert lock_response.json()["is_locked"] is True

        unlock_response = await client.patch(
            f"/api/chapters/{chapter_id}/lock",
            headers=auth_headers(token),
            json={"locked": False},
        )
        assert unlock_response.status_code == 200, unlock_response.text
        assert unlock_response.json()["is_locked"] is False


@pytest.mark.anyio
async def test_global_character_library_can_attach_the_same_character_to_multiple_projects(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=FakeStoryAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project_alpha = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "暮色站台",
                    "genre": "悬疑",
                    "tone": "冷静、电影感",
                    "era": "当代",
                    "target_chapter_count": 4,
                    "target_length": "4章",
                    "logline": "一段被删改的站台监控，牵出两代人的秘密。",
                },
            )
        ).json()
        project_beta = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "冬夜回声",
                    "genre": "都市悬疑",
                    "tone": "克制、压抑",
                    "era": "当代",
                    "target_chapter_count": 3,
                    "target_length": "3章",
                    "logline": "一次深夜电台连线，让旧案重新浮出水面。",
                },
            )
        ).json()

        create_character = await client.post(
            "/api/characters",
            headers=auth_headers(token),
            data={
                "name": "林听",
                "role": "广播站修复师",
                "personality": "敏锐、克制、嘴硬心软",
                "goal": "找回失踪姐姐的线索",
                "speech_style": "短句、留白多、偶尔一针见血",
                "appearance": "黑色短发，偏瘦，常穿深色风衣，眼神警觉",
                "relationships": "与顾昼互相试探，与沈苒互相信任",
            },
        )
        assert create_character.status_code == 201, create_character.text
        character = create_character.json()
        assert character["linked_project_ids"] == []

        attach_alpha = await client.post(
            f"/api/projects/{project_alpha['id']}/characters/attach",
            headers=auth_headers(token),
            json={"character_id": character["id"]},
        )
        assert attach_alpha.status_code == 200, attach_alpha.text
        assert attach_alpha.json()["linked_project_ids"] == [project_alpha["id"]]

        attach_beta = await client.post(
            f"/api/projects/{project_beta['id']}/characters/attach",
            headers=auth_headers(token),
            json={"character_id": character["id"]},
        )
        assert attach_beta.status_code == 200, attach_beta.text
        assert attach_beta.json()["linked_project_ids"] == [project_alpha["id"], project_beta["id"]]

        library_payload = await client.get("/api/characters", headers=auth_headers(token))
        assert library_payload.status_code == 200, library_payload.text
        library_character = next(item for item in library_payload.json() if item["id"] == character["id"])
        assert library_character["linked_project_ids"] == [project_alpha["id"], project_beta["id"]]

        alpha_detail = await client.get(f"/api/projects/{project_alpha['id']}", headers=auth_headers(token))
        beta_detail = await client.get(f"/api/projects/{project_beta['id']}", headers=auth_headers(token))
        assert alpha_detail.status_code == 200, alpha_detail.text
        assert beta_detail.status_code == 200, beta_detail.text
        assert [item["name"] for item in alpha_detail.json()["characters"]] == ["林听"]
        assert [item["name"] for item in beta_detail.json()["characters"]] == ["林听"]


@pytest.mark.anyio
async def test_detaching_character_from_project_keeps_global_library_entry(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=FakeStoryAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "月台失真",
                    "genre": "悬疑",
                    "tone": "冷静、克制",
                    "era": "当代",
                    "target_chapter_count": 2,
                    "target_length": "2章",
                    "logline": "一盘失真的录音带让一位修复师重新面对旧案。",
                },
            )
        ).json()

        create_character = await client.post(
            f"/api/projects/{project['id']}/characters",
            headers=auth_headers(token),
            data={
                "name": "顾昼",
                "role": "旧案调查记者",
                "personality": "克制、警惕、情绪压得很深",
                "goal": "找出被人为掩埋的报道源头",
                "speech_style": "短句、冷一点、会忽然逼问",
                "appearance": "深色大衣，轮廓清瘦，眼神带疲态",
                "relationships": "与林听互相试探又不得不合作",
            },
        )
        assert create_character.status_code == 201, create_character.text
        character = create_character.json()
        assert character["linked_project_ids"] == [project["id"]]

        detach_response = await client.delete(
            f"/api/projects/{project['id']}/characters/{character['id']}",
            headers=auth_headers(token),
        )
        assert detach_response.status_code == 204, detach_response.text

        project_detail = await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        assert project_detail.status_code == 200, project_detail.text
        assert project_detail.json()["characters"] == []

        library_payload = await client.get("/api/characters", headers=auth_headers(token))
        assert library_payload.status_code == 200, library_payload.text
        detached_character = next(item for item in library_payload.json() if item["id"] == character["id"])
        assert detached_character["linked_project_ids"] == []


@pytest.mark.anyio
async def test_generation_pipeline_creates_story_assets_and_export_bundle(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=FakeStoryAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "长街回声",
                    "genre": "悬疑成长",
                    "tone": "冷静、克制、人物驱动",
                    "era": "近未来",
                    "target_length": "8章",
                    "logline": "旧城区的广播里不断响起未来新闻，三名主角被迫联手破解时间裂隙。",
                },
            )
        ).json()

        create_character = await client.post(
            f"/api/projects/{project['id']}/characters",
            headers=auth_headers(token),
            files={"reference_image": ("lead.png", TEST_PNG_BYTES, "image/png")},
            data={
                "name": "林听",
                "role": "广播站修复师",
                "personality": "敏锐、克制、嘴硬心软",
                "goal": "找回失踪姐姐的线索",
                "speech_style": "短句、留白多、偶尔一针见血",
                "appearance": "黑色短发，偏瘦，常穿深色风衣，眼神警觉",
                "relationships": "与顾昼互相试探，与沈苒互相信任",
            },
        )
        assert create_character.status_code == 201, create_character.text
        character = create_character.json()
        assert character["visual_profile"]["signature_palette"] == "深青、雾银、暖白"
        assert character["reference_images"]

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={"chapter_count": 4},
            )
        ).json()
        outline_result = await wait_for_job(client, token, outline_job["id"])
        assert outline_result["status"] == "completed", outline_result
        assert outline_result["result"]["model_ids"]["planner"] == "fake-planner"

        project_detail = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        assert len(project_detail["chapters"]) == 4
        assert project_detail["story_bible"]["writing_rules"] == [
            "冲突必须由角色选择推动",
            "每章结尾保留牵引力",
            "对白服务人物关系变化",
        ]
        chapter_id = project_detail["chapters"][0]["id"]

        draft_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-draft",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        draft_result = await wait_for_job(client, token, draft_job["id"])
        assert draft_result["status"] == "completed", draft_result
        assert draft_result["result"]["model_ids"]["writer"] == "fake-writer"
        assert draft_result["result"]["model_ids"]["reviewer"] == "fake-reviewer"

        scenes_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-scenes",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        scenes_result = await wait_for_job(client, token, scenes_job["id"])
        assert scenes_result["status"] == "completed", scenes_result

        refreshed_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        first_chapter = refreshed_project["chapters"][0]
        assert first_chapter["narrative_blocks"]
        assert first_chapter["narrative_blocks"][0]["content"].startswith("[审校后]")
        assert first_chapter["continuity_notes"][0].startswith("Reviewer：")
        assert len(first_chapter["scenes"]) == 3
        assert first_chapter["scenes"][0]["objective"].startswith("[审校后]")
        scene_id = first_chapter["scenes"][0]["id"]

        illustrations_job = (
            await client.post(
                f"/api/scenes/{scene_id}/generate-illustrations",
                headers=auth_headers(token),
                json={"candidate_count": 2},
            )
        ).json()
        illustrations_result = await wait_for_job(client, token, illustrations_job["id"])
        assert illustrations_result["status"] == "completed", illustrations_result
        assert illustrations_result["result"]["model_ids"]["visual_prompt"] == "fake-visual"
        assert illustrations_result["result"]["model_ids"]["image_generation"] == "fake-image"
        assert illustrations_result["result"]["trace_count"] == 2

        refreshed_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        scene = refreshed_project["chapters"][0]["scenes"][0]
        assert len(scene["illustrations"]) == 2
        assert "restrained editorial realism" in scene["visual_prompt"]
        illustration_id = scene["illustrations"][0]["id"]

        mark_canonical = await client.post(
            f"/api/illustrations/{illustration_id}/canonical",
            headers=auth_headers(token),
            json={},
        )
        assert mark_canonical.status_code == 200, mark_canonical.text
        assert mark_canonical.json()["is_canonical"] is True

        export_job = (
            await client.post(
                f"/api/projects/{project['id']}/exports",
                headers=auth_headers(token),
                json={"formats": ["pdf", "docx"]},
            )
        ).json()
        export_result = await wait_for_job(client, token, export_job["id"])
        assert export_result["status"] == "completed", export_result

        export_payload = await client.get(
            f"/api/exports/{export_result['result']['export_id']}",
            headers=auth_headers(token),
        )
        assert export_payload.status_code == 200, export_payload.text
        export_info = export_payload.json()
        generated_formats = {item["format"] for item in export_info["files"]}
        assert generated_formats == {"pdf", "docx"}
        assert export_info["delivery_summary"]["chapter_count"] == 4
        assert export_info["delivery_summary"]["quality_status"] == "passed"
        pdf_info = next(item for item in export_info["files"] if item["format"] == "pdf")
        assert pdf_info["page_count"] >= 1
        assert pdf_info["quality_check"]["status"] == "passed"
        for file_info in export_info["files"]:
            assert Path(file_info["path"]).exists()


@pytest.mark.anyio
async def test_scene_illustration_regeneration_uses_canonical_feedback_and_continues_candidate_index(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=CanonicalFeedbackAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "长街回声",
                    "genre": "悬疑成长",
                    "tone": "冷静、克制、人物驱动",
                    "era": "近未来",
                    "target_length": "8章",
                    "logline": "旧城区的广播里不断响起未来新闻，三名主角被迫联手破解时间裂隙。",
                },
            )
        ).json()

        await client.post(
            f"/api/projects/{project['id']}/characters",
            headers=auth_headers(token),
            files={"reference_image": ("lead.png", TEST_PNG_BYTES, "image/png")},
            data={
                "name": "林听",
                "role": "广播站修复师",
                "personality": "敏锐、克制、嘴硬心软",
                "goal": "找回失踪姐姐的线索",
                "speech_style": "短句、留白多、偶尔一针见血",
                "appearance": "黑色短发，偏瘦，常穿深色风衣，眼神警觉",
                "relationships": "与顾昼互相试探，与沈苒互相信任",
            },
        )

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={"chapter_count": 2},
            )
        ).json()
        assert (await wait_for_job(client, token, outline_job["id"]))["status"] == "completed"

        project_detail = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        chapter_id = project_detail["chapters"][0]["id"]

        draft_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-draft",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        assert (await wait_for_job(client, token, draft_job["id"]))["status"] == "completed"

        scenes_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-scenes",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        assert (await wait_for_job(client, token, scenes_job["id"]))["status"] == "completed"

        refreshed = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        scene_id = refreshed["chapters"][0]["scenes"][0]["id"]

        first_illustrations_job = (
            await client.post(
                f"/api/scenes/{scene_id}/generate-illustrations",
                headers=auth_headers(token),
                json={"candidate_count": 2},
            )
        ).json()
        first_illustrations_result = await wait_for_job(client, token, first_illustrations_job["id"])
        assert first_illustrations_result["status"] == "completed", first_illustrations_result

        refreshed = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        first_scene = refreshed["chapters"][0]["scenes"][0]
        canonical_id = first_scene["illustrations"][0]["id"]

        mark_canonical = await client.post(
            f"/api/illustrations/{canonical_id}/canonical",
            headers=auth_headers(token),
            json={},
        )
        assert mark_canonical.status_code == 200, mark_canonical.text

        second_illustrations_job = (
            await client.post(
                f"/api/scenes/{scene_id}/generate-illustrations",
                headers=auth_headers(token),
                json={
                    "candidate_count": 1,
                    "extra_guidance": "保留主图里的冷青色灯光，但让人物表情更克制",
                },
            )
        ).json()
        second_illustrations_result = await wait_for_job(client, token, second_illustrations_job["id"])
        assert second_illustrations_result["status"] == "completed", second_illustrations_result
        assert second_illustrations_result["result"]["reference_feedback"]["used_scene_canonical"] is True
        assert second_illustrations_result["result"]["reference_feedback"]["canonical_illustration_id"] == canonical_id

        final_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        scene = final_project["chapters"][0]["scenes"][0]
        candidate_indexes = [item["candidate_index"] for item in scene["illustrations"]]
        assert candidate_indexes == [1, 2, 3]
        assert "reference=" in scene["visual_prompt"]
        assert "guidance=保留主图里的冷青色灯光" in scene["visual_prompt"]


@pytest.mark.anyio
async def test_user_can_delete_saved_assets_and_workspace_history(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=FakeStoryAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "长夏的尾声",
                    "genre": "青春成长",
                    "tone": "细腻、克制、带一点暖意",
                    "era": "当代",
                    "target_length": "10章",
                    "logline": "两个即将毕业的年轻人，在最后一个暑假里完成各自的告别。",
                },
            )
        ).json()
        cover_path = Path(project["cover_image_path"])
        assert cover_path.exists()

        create_character = await client.post(
            f"/api/projects/{project['id']}/characters",
            headers=auth_headers(token),
            files={"reference_image": ("lead.png", TEST_PNG_BYTES, "image/png")},
            data={
                "name": "盛夏",
                "role": "即将毕业的编导生",
                "personality": "敏感、倔强、观察力强",
                "goal": "在离校前拍完自己的毕业短片",
                "speech_style": "说话克制，偶尔突然锋利",
                "appearance": "黑发、浅色衬衫、总背着旧相机包",
                "relationships": "与周屿互相欣赏又互相拉扯",
            },
        )
        assert create_character.status_code == 201, create_character.text
        character = create_character.json()
        character_id = character["id"]
        reference_path = Path(character["reference_images"][0]["path"])
        assert reference_path.exists()

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={"chapter_count": 2},
            )
        ).json()
        outline_result = await wait_for_job(client, token, outline_job["id"])
        assert outline_result["status"] == "completed", outline_result

        project_detail = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        chapter_id = project_detail["chapters"][0]["id"]

        draft_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-draft",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        draft_result = await wait_for_job(client, token, draft_job["id"])
        assert draft_result["status"] == "completed", draft_result

        scenes_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-scenes",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        scenes_result = await wait_for_job(client, token, scenes_job["id"])
        assert scenes_result["status"] == "completed", scenes_result

        refreshed_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        scene_id = refreshed_project["chapters"][0]["scenes"][0]["id"]

        illustrations_job = (
            await client.post(
                f"/api/scenes/{scene_id}/generate-illustrations",
                headers=auth_headers(token),
                json={"candidate_count": 2},
            )
        ).json()
        illustrations_result = await wait_for_job(client, token, illustrations_job["id"])
        assert illustrations_result["status"] == "completed", illustrations_result

        refreshed_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        scene = refreshed_project["chapters"][0]["scenes"][0]
        illustration = scene["illustrations"][0]
        illustration_id = illustration["id"]
        illustration_path = Path(illustration["path"])
        illustration_thumb_path = Path(illustration["thumbnail_url"].replace("/media/storage/", str((tmp_path / "runtime" / "storage").resolve()) + "/"))
        assert illustration_path.exists()
        assert illustration_thumb_path.exists()

        export_job = (
            await client.post(
                f"/api/projects/{project['id']}/exports",
                headers=auth_headers(token),
                json={"formats": ["pdf", "docx"]},
            )
        ).json()
        export_result = await wait_for_job(client, token, export_job["id"])
        assert export_result["status"] == "completed", export_result
        export_id = export_result["result"]["export_id"]

        export_payload = await client.get(
            f"/api/exports/{export_id}",
            headers=auth_headers(token),
        )
        assert export_payload.status_code == 200, export_payload.text
        export_paths = [Path(item["path"]) for item in export_payload.json()["files"]]
        assert all(path.exists() for path in export_paths)

        delete_job = await client.delete(
            f"/api/jobs/{outline_job['id']}",
            headers=auth_headers(token),
        )
        assert delete_job.status_code == 204, delete_job.text

        detail_after_job_delete = await client.get(
            f"/api/projects/{project['id']}",
            headers=auth_headers(token),
        )
        assert detail_after_job_delete.status_code == 200, detail_after_job_delete.text
        remaining_job_ids = {item["id"] for item in detail_after_job_delete.json()["jobs"]}
        assert outline_job["id"] not in remaining_job_ids

        delete_illustration = await client.delete(
            f"/api/illustrations/{illustration_id}",
            headers=auth_headers(token),
        )
        assert delete_illustration.status_code == 204, delete_illustration.text
        assert not illustration_path.exists()
        assert not illustration_thumb_path.exists()

        detail_after_illustration_delete = await client.get(
            f"/api/projects/{project['id']}",
            headers=auth_headers(token),
        )
        assert detail_after_illustration_delete.status_code == 200, detail_after_illustration_delete.text
        remaining_illustration_ids = {
            item["id"]
            for item in detail_after_illustration_delete.json()["chapters"][0]["scenes"][0]["illustrations"]
        }
        assert illustration_id not in remaining_illustration_ids

        delete_export = await client.delete(
            f"/api/exports/{export_id}",
            headers=auth_headers(token),
        )
        assert delete_export.status_code == 204, delete_export.text
        assert all(not path.exists() for path in export_paths)

        export_after_delete = await client.get(
            f"/api/exports/{export_id}",
            headers=auth_headers(token),
        )
        assert export_after_delete.status_code == 404

        delete_character = await client.delete(
            f"/api/characters/{character_id}",
            headers=auth_headers(token),
        )
        assert delete_character.status_code == 204, delete_character.text
        assert not reference_path.exists()

        detail_after_character_delete = await client.get(
            f"/api/projects/{project['id']}",
            headers=auth_headers(token),
        )
        assert detail_after_character_delete.status_code == 200, detail_after_character_delete.text
        remaining_character_ids = {item["id"] for item in detail_after_character_delete.json()["characters"]}
        assert character_id not in remaining_character_ids

        delete_project = await client.delete(
            f"/api/projects/{project['id']}",
            headers=auth_headers(token),
        )
        assert delete_project.status_code == 204, delete_project.text
        assert not cover_path.exists()

        project_after_delete = await client.get(
            f"/api/projects/{project['id']}",
            headers=auth_headers(token),
        )
        assert project_after_delete.status_code == 404

        projects_after_delete = await client.get("/api/projects", headers=auth_headers(token))
        assert projects_after_delete.status_code == 200, projects_after_delete.text
        assert projects_after_delete.json() == []


@pytest.mark.anyio
async def test_reviewer_issues_backfill_continuity_notes_when_missing(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=SparseReviewNotesAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "Signal After Midnight",
                    "genre": "Urban suspense",
                    "tone": "tight, restrained, character-driven",
                    "era": "Contemporary",
                    "target_length": "5 chapters",
                    "logline": "A radio host and his former partner chase the source of a call that should not exist.",
                },
            )
        ).json()

        create_character = await client.post(
            f"/api/projects/{project['id']}/characters",
            headers=auth_headers(token),
            data={
                "name": "Shen Yan",
                "role": "Radio host",
                "personality": "calm, sharp, private",
                "goal": "Verify whether the missing witness is still alive",
                "speech_style": "short lines with deliberate pauses",
                "appearance": "dark coat, tired eyes, still posture",
                "relationships": "keeps distance from his former partner but still depends on him",
            },
        )
        assert create_character.status_code == 201, create_character.text

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={"chapter_count": 2},
            )
        ).json()
        outline_result = await wait_for_job(client, token, outline_job["id"])
        assert outline_result["status"] == "completed", outline_result

        project_detail = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        chapter_id = project_detail["chapters"][0]["id"]

        draft_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-draft",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        draft_result = await wait_for_job(client, token, draft_job["id"])
        assert draft_result["status"] == "completed", draft_result

        refreshed_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        first_chapter = refreshed_project["chapters"][0]
        assert first_chapter["continuity_notes"] == ["Reviewer：Keep the character naming consistent."]

        scenes_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-scenes",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        scenes_result = await wait_for_job(client, token, scenes_job["id"])
        assert scenes_result["status"] == "completed", scenes_result

        refreshed_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        first_chapter = refreshed_project["chapters"][0]
        assert first_chapter["continuity_notes"] == ["Reviewer：Clarify the pressure from scene to scene."]


@pytest.mark.anyio
async def test_reviewer_intervention_pauses_job_and_can_be_retried(tmp_path, monkeypatch):
    agents = InterventionStoryAgents()
    app = create_client(tmp_path, monkeypatch, story_agents=agents)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "午夜桥面",
                    "genre": "都市悬疑",
                    "tone": "紧绷、克制、人物驱动",
                    "era": "当代",
                    "target_chapter_count": 3,
                    "target_length": "3章，短剧节奏",
                    "logline": "一通深夜语音把主角重新带回案发桥面。",
                },
            )
        ).json()

        create_character = await client.post(
            f"/api/projects/{project['id']}/characters",
            headers=auth_headers(token),
            data={
                "name": "顾行",
                "role": "事故调查记者",
                "personality": "克制、谨慎、情绪压在行动后面",
                "goal": "查清桥面事故背后的删改记录",
                "speech_style": "短句、少解释、提问锋利",
                "appearance": "深色外套，身形偏瘦，面部总带疲惫感",
                "relationships": "与前搭档长期失和，却依然保留复杂信任",
            },
        )
        assert create_character.status_code == 201, create_character.text

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        outline_result = await wait_for_job(client, token, outline_job["id"])
        assert outline_result["status"] == "completed", outline_result

        project_detail = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        chapter_id = project_detail["chapters"][0]["id"]

        draft_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-draft",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        draft_result = await wait_for_terminal_job(client, token, draft_job["id"])
        assert draft_result["status"] == "awaiting_user", draft_result
        assert draft_result["pending_interventions"], draft_result
        assert draft_result["agent_runs"], draft_result
        intervention = draft_result["pending_interventions"][0]
        assert intervention["intervention_type"] == "rewrite_writer"

        agents.draft_retry_seen = True
        retry_response = await client.post(
            f"/api/review-interventions/{intervention['id']}/retry",
            headers=auth_headers(token),
            json={"extra_guidance": "先补角色关系拉扯，再落章节钩子。"},
        )
        assert retry_response.status_code == 202, retry_response.text

        retried_job = await wait_for_terminal_job(client, token, retry_response.json()["id"])
        assert retried_job["status"] == "completed", retried_job

        refreshed_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        first_chapter = refreshed_project["chapters"][0]
        assert first_chapter["narrative_blocks"], refreshed_project
        assert first_chapter["narrative_blocks"][0]["content"].startswith("[accepted]")


@pytest.mark.anyio
async def test_moderate_reviewer_decisions_are_auto_applied_without_manual_intervention(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=ModerateAutoApplyStoryAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "侧幕之后",
                    "genre": "都市情感悬疑",
                    "tone": "克制、带暗流、人物关系先行",
                    "era": "当代",
                    "target_chapter_count": 2,
                    "target_length": "2章，短剧节奏",
                    "logline": "一场失控的直播后，两位旧友被迫重新站到同一盏追光灯下。",
                },
            )
        ).json()

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        outline_result = await wait_for_job(client, token, outline_job["id"])
        assert outline_result["status"] == "completed", outline_result

        project_detail = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        chapter_id = project_detail["chapters"][0]["id"]

        draft_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-draft",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        draft_result = await wait_for_terminal_job(client, token, draft_job["id"])
        assert draft_result["status"] == "completed", draft_result
        assert draft_result["pending_interventions"] == [], draft_result

        refreshed_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        first_chapter = refreshed_project["chapters"][0]
        assert first_chapter["narrative_blocks"][0]["content"].startswith("[auto-reviewed]")
        assert first_chapter["continuity_notes"] == ["Reviewer：已自动补强情绪过渡，不需要打断作者继续创作。"]


@pytest.mark.anyio
async def test_story_bible_patch_creates_revision_and_new_jobs_bind_latest_revision(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=FakeStoryAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "雾港备忘录",
                    "genre": "都市悬疑",
                    "tone": "克制、低照度、人物先行",
                    "era": "当代",
                    "target_chapter_count": 3,
                    "target_length": "3章，短剧节奏",
                    "logline": "一份遗失的口供录音，把三位旧识重新拖回雾港码头。",
                },
            )
        ).json()

        initial_story_bible = await client.get(
            f"/api/projects/{project['id']}/story-bible",
            headers=auth_headers(token),
        )
        assert initial_story_bible.status_code == 200, initial_story_bible.text
        initial_revision_id = initial_story_bible.json()["current_revision"]["id"]

        patched_story_bible = await client.patch(
            f"/api/projects/{project['id']}/story-bible",
            headers=auth_headers(token),
            json={
                "world_notes": "故事发生在海雾常年的旧港城，所有关键冲突都与旧码头的封存档案有关。",
                "style_notes": "控制解释密度，让角色动作先于结论。",
                "writing_rules": ["称呼必须稳定", "每章至少推进一条伏笔", "避免上帝视角直给答案"],
                "addressing_rules": "林听始终称顾昼为“顾昼”，不改用别称。",
                "timeline_rules": "全篇时间跨度控制在七天内。",
            },
        )
        assert patched_story_bible.status_code == 200, patched_story_bible.text
        assert patched_story_bible.json()["current_revision"]["id"] > initial_revision_id

        revision_list = await client.get(
            f"/api/projects/{project['id']}/story-bible/revisions",
            headers=auth_headers(token),
        )
        assert revision_list.status_code == 200, revision_list.text
        revisions = revision_list.json()
        assert len(revisions) >= 2
        assert revisions[0]["id"] == patched_story_bible.json()["current_revision"]["id"]

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        outline_result = await wait_for_job(client, token, outline_job["id"])
        assert outline_result["status"] == "completed", outline_result
        assert outline_result["result"]["story_bible_revision_id"] == patched_story_bible.json()["current_revision"]["id"]

        project_detail = await client.get(
            f"/api/projects/{project['id']}",
            headers=auth_headers(token),
        )
        assert project_detail.status_code == 200, project_detail.text
        chapter = project_detail.json()["chapters"][0]
        assert chapter["source_story_bible_revision_id"] == patched_story_bible.json()["current_revision"]["id"]


@pytest.mark.anyio
async def test_user_edited_narrative_block_is_preserved_and_revision_can_be_restored(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=FakeStoryAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "桥面回音",
                    "genre": "都市悬疑",
                    "tone": "冷静、压抑、人物驱动",
                    "era": "当代",
                    "target_chapter_count": 2,
                    "target_length": "2章，短剧节奏",
                    "logline": "一次桥面事故后，主角在被删改的通联记录里找到了第二条真相线。",
                },
            )
        ).json()

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        assert (await wait_for_job(client, token, outline_job["id"]))["status"] == "completed"

        project_detail = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        chapter_id = project_detail["chapters"][0]["id"]

        draft_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-draft",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        draft_result = await wait_for_job(client, token, draft_job["id"])
        assert draft_result["status"] == "completed", draft_result

        refreshed_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        first_block = refreshed_project["chapters"][0]["narrative_blocks"][0]
        original_content = first_block["content"]

        edited_block = await client.patch(
            f"/api/narrative-blocks/{first_block['id']}",
            headers=auth_headers(token),
            json={
                "content": "这是作者手动改写后的第一段，必须保留这层迟疑和遮掩。",
                "is_locked": True,
            },
        )
        assert edited_block.status_code == 200, edited_block.text
        assert edited_block.json()["is_user_edited"] is True
        assert edited_block.json()["is_locked"] is True

        regenerated_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-draft",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        regenerated_result = await wait_for_job(client, token, regenerated_job["id"])
        assert regenerated_result["status"] == "completed", regenerated_result

        final_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        final_block = final_project["chapters"][0]["narrative_blocks"][0]
        assert final_block["content"] == "这是作者手动改写后的第一段，必须保留这层迟疑和遮掩。"
        assert final_block["is_locked"] is True
        assert final_block["is_user_edited"] is True

        revisions_response = await client.get(
            f"/api/chapters/{chapter_id}/revisions",
            headers=auth_headers(token),
        )
        assert revisions_response.status_code == 200, revisions_response.text
        revisions = revisions_response.json()
        assert len(revisions) >= 2
        assert revisions[0]["created_by"] in {"agent", "user"}

        oldest_revision_id = revisions[-1]["id"]
        restore_response = await client.post(
            f"/api/chapters/{chapter_id}/revisions/{oldest_revision_id}/restore",
            headers=auth_headers(token),
        )
        assert restore_response.status_code == 200, restore_response.text

        restored_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        restored_block = restored_project["chapters"][0]["narrative_blocks"][0]
        assert restored_block["content"] == original_content


@pytest.mark.anyio
async def test_revision_diff_endpoints_expose_story_bible_and_chapter_changes(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=FakeStoryAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "雾潮归档",
                    "genre": "都市悬疑",
                    "tone": "压抑、克制、镜头感强",
                    "era": "当代",
                    "target_chapter_count": 2,
                    "target_length": "2章，紧凑推进",
                    "logline": "一段被人刻意剪断的录音，把旧港的三位证人重新拖回同一夜。",
                },
            )
        ).json()

        initial_story_bible = await client.get(
            f"/api/projects/{project['id']}/story-bible",
            headers=auth_headers(token),
        )
        assert initial_story_bible.status_code == 200, initial_story_bible.text
        initial_revision_id = initial_story_bible.json()["current_revision"]["id"]

        patched_story_bible = await client.patch(
            f"/api/projects/{project['id']}/story-bible",
            headers=auth_headers(token),
            json={
                "world_notes": "旧港潮位反复异常，所有关键冲突都绕着封存录音和临时管制区展开。",
                "style_notes": "动作先于解释，所有关键答案必须在人物对抗里显出来。",
                "writing_rules": ["动作先行", "称呼稳定", "悬念必须落到人物选择"],
                "addressing_rules": "林听始终叫顾昼“顾昼”，不改称呼。",
                "timeline_rules": "全篇故事控制在四十八小时内。",
            },
        )
        assert patched_story_bible.status_code == 200, patched_story_bible.text
        current_revision_id = patched_story_bible.json()["current_revision"]["id"]

        story_bible_diff = await client.get(
            f"/api/projects/{project['id']}/story-bible/revisions/{initial_revision_id}/diff",
            headers=auth_headers(token),
        )
        assert story_bible_diff.status_code == 200, story_bible_diff.text
        diff_payload = story_bible_diff.json()
        assert diff_payload["base_revision"]["id"] == current_revision_id
        assert diff_payload["target_revision"]["id"] == initial_revision_id
        assert diff_payload["summary"]["changed_field_count"] >= 3
        changed_fields = {item["field"]: item for item in diff_payload["fields"] if item["changed"]}
        assert "world_notes" in changed_fields
        assert "writing_rules" in changed_fields

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        assert (await wait_for_job(client, token, outline_job["id"]))["status"] == "completed"

        project_detail = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        chapter_id = project_detail["chapters"][0]["id"]

        draft_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-draft",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        assert (await wait_for_job(client, token, draft_job["id"]))["status"] == "completed"

        refreshed_project = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        first_block = refreshed_project["chapters"][0]["narrative_blocks"][0]
        edited_block = await client.patch(
            f"/api/narrative-blocks/{first_block['id']}",
            headers=auth_headers(token),
            json={"content": "这是作者手改的版本，会把犹疑与停顿写得更重。"},
        )
        assert edited_block.status_code == 200, edited_block.text

        chapter_revisions = await client.get(
            f"/api/chapters/{chapter_id}/revisions",
            headers=auth_headers(token),
        )
        assert chapter_revisions.status_code == 200, chapter_revisions.text
        revisions = chapter_revisions.json()
        oldest_revision_id = revisions[-1]["id"]

        chapter_diff = await client.get(
            f"/api/chapters/{chapter_id}/revisions/{oldest_revision_id}/diff",
            headers=auth_headers(token),
        )
        assert chapter_diff.status_code == 200, chapter_diff.text
        chapter_diff_payload = chapter_diff.json()
        assert chapter_diff_payload["base"]["kind"] == "live"
        assert chapter_diff_payload["target"]["revision_id"] == oldest_revision_id
        assert chapter_diff_payload["overview"]["narrative_blocks"]["changed"] >= 1
        assert chapter_diff_payload["overview"]["scene_count_delta"] >= 0
        assert any(change["status"] == "changed" for change in chapter_diff_payload["narrative_block_changes"])


@pytest.mark.anyio
async def test_project_can_create_snapshot_and_duplicate_without_copying_job_history(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=FakeStoryAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "回潮之前",
                    "genre": "都市悬疑",
                    "tone": "克制、潮湿、低饱和",
                    "era": "当代",
                    "target_chapter_count": 2,
                    "target_length": "2章，试运行",
                    "logline": "一场涨潮前的失联，把几位旧友逼回已经封港的海边小城。",
                },
            )
        ).json()

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        assert (await wait_for_job(client, token, outline_job["id"]))["status"] == "completed"

        project_detail = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        chapter_id = project_detail["chapters"][0]["id"]
        draft_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-draft",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        assert (await wait_for_job(client, token, draft_job["id"]))["status"] == "completed"

        snapshot_response = await client.post(
            f"/api/projects/{project['id']}/snapshots",
            headers=auth_headers(token),
            json={"label": "重写前备份"},
        )
        assert snapshot_response.status_code == 201, snapshot_response.text
        snapshot = snapshot_response.json()
        assert snapshot["project_id"] == project["id"]
        assert snapshot["chapter_count"] == 2

        list_snapshots = await client.get(
            f"/api/projects/{project['id']}/snapshots",
            headers=auth_headers(token),
        )
        assert list_snapshots.status_code == 200, list_snapshots.text
        assert list_snapshots.json()[0]["id"] == snapshot["id"]

        duplicate_response = await client.post(
            f"/api/projects/{project['id']}/duplicate",
            headers=auth_headers(token),
            json={"title": "回潮之前·分支稿"},
        )
        assert duplicate_response.status_code == 201, duplicate_response.text
        duplicate = duplicate_response.json()
        assert duplicate["title"] == "回潮之前·分支稿"
        assert duplicate["id"] != project["id"]
        assert duplicate["jobs"] == []
        assert len(duplicate["chapters"]) == 2
        assert duplicate["chapters"][0]["narrative_blocks"]


@pytest.mark.anyio
async def test_failed_job_can_be_retried_from_job_detail(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=ExplodingImageAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "重试回声",
                    "genre": "悬疑",
                    "tone": "冷静、低照度",
                    "era": "当代",
                    "target_chapter_count": 2,
                    "target_length": "2章",
                    "logline": "一条失败的图像任务应该允许作者从原位重试。",
                },
            )
        ).json()

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        assert (await wait_for_job(client, token, outline_job["id"]))["status"] == "completed"

        project_detail = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        chapter_id = project_detail["chapters"][0]["id"]
        scenes_job = (
            await client.post(
                f"/api/chapters/{chapter_id}/generate-scenes",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        assert (await wait_for_job(client, token, scenes_job["id"]))["status"] == "completed"

        refreshed = (
            await client.get(f"/api/projects/{project['id']}", headers=auth_headers(token))
        ).json()
        scene_id = refreshed["chapters"][0]["scenes"][0]["id"]
        failed_job = (
            await client.post(
                f"/api/scenes/{scene_id}/generate-illustrations",
                headers=auth_headers(token),
                json={"candidate_count": 1},
            )
        ).json()
        failed_result = await wait_for_job(client, token, failed_job["id"])
        assert failed_result["status"] == "failed"

        retry_response = await client.post(
            f"/api/jobs/{failed_job['id']}/retry",
            headers=auth_headers(token),
        )
        assert retry_response.status_code == 202, retry_response.text
        retried_job = retry_response.json()
        assert retried_job["job_type"] == failed_job["job_type"]
        assert retried_job["scene_id"] == scene_id
        assert retried_job["id"] != failed_job["id"]
@pytest.mark.anyio
async def test_job_stream_endpoint_emits_processing_trace_updates(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch)
    with app.state.session_factory() as db:
        user = User(
            email="stream@example.com",
            password_hash="hashed",
            pen_name="流式作者",
            access_token="stream-token",
        )
        db.add(user)
        db.flush()

        job = GenerationJob(
            user=user,
            job_type="chapter_draft",
            status="processing",
            progress=38,
            status_message="Writer 正在梳理冲突与情绪落点",
            input_snapshot={},
        )
        db.add(job)
        db.flush()

        db.add(
            AgentRun(
                job=job,
                project_id=None,
                chapter_id=None,
                scene_id=None,
                sequence=1,
                step_key="writer_draft",
                agent_name="writer",
                status="processing",
                adoption_state="proposed",
                model_id="fake-writer",
                input_summary="Write the next chapter draft with a visible collaboration log.",
                prompt_preview="Expose public_notes first so the author can follow the creative direction.",
                output_summary="正在组织正文段落",
                stream_text='{"public_notes":["先把角色冲突落到可表演的动作上"',
                public_notes=["先把角色冲突落到可表演的动作上"],
            )
        )
        db.commit()
        job_id = job.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=5.0) as client:
        async with client.stream("GET", f"/api/jobs/{job_id}/stream?once=1", headers=auth_headers("stream-token")) as response:
            assert response.status_code == 200, await response.aread()
            body = ""
            async for chunk in response.aiter_text():
                body += chunk
                if "event: job" in body:
                    break

        assert "\"status\":\"processing\"" in body
        assert "Writer 正在梳理冲突与情绪落点" in body


@pytest.mark.anyio
async def test_completed_job_detail_includes_live_stage_state(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch, story_agents=FakeStoryAgents())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await register_user(client)
        token = auth["token"]

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(token),
                json={
                    "title": "夜港调频",
                    "genre": "都市悬疑",
                    "tone": "克制、潮湿、人物先行",
                    "era": "当代",
                    "target_chapter_count": 2,
                    "target_length": "2章，短剧节奏",
                    "logline": "一段凌晨电台信号，把旧港里互相试探的三个人逼进同一张时间网。",
                },
            )
        ).json()

        outline_job = (
            await client.post(
                f"/api/projects/{project['id']}/generate/outline",
                headers=auth_headers(token),
                json={},
            )
        ).json()
        outline_result = await wait_for_job(client, token, outline_job["id"])
        assert outline_result["status"] == "completed", outline_result

        job_detail = await client.get(
            f"/api/jobs/{outline_job['id']}",
            headers=auth_headers(token),
        )
        assert job_detail.status_code == 200, job_detail.text
        payload = job_detail.json()
        live_state = payload["result"]["live_state"]
        assert live_state["current_stage"] == "complete"
        assert live_state["current_step"] == "complete"
        assert live_state["current_step_label"] == "工作流完成"
        stage_keys = [item["stage"] for item in live_state["stages"]]
        assert stage_keys == ["queued", "context", "generate", "review", "persist", "complete"]
        completed_stages = {item["stage"] for item in live_state["stage_history"] if item["status"] == "completed"}
        assert {"queued", "context", "generate", "persist", "complete"}.issubset(completed_stages)


@pytest.mark.anyio
async def test_project_access_is_limited_to_owner(tmp_path, monkeypatch):
    app = create_client(tmp_path, monkeypatch)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        owner = await register_user(client, email="owner@example.com", pen_name="Owner")
        stranger = await register_user(client, email="stranger@example.com", pen_name="Other")

        project = (
            await client.post(
                "/api/projects",
                headers=auth_headers(owner["token"]),
                json={
                    "title": "私有故事",
                    "genre": "悬疑",
                    "tone": "冷冽",
                    "era": "当代",
                    "target_length": "6章",
                    "logline": "这是一个私有项目。",
                },
            )
        ).json()

        forbidden = await client.get(
            f"/api/projects/{project['id']}",
            headers=auth_headers(stranger["token"]),
        )
        assert forbidden.status_code == 404
