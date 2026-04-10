import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

from app.models import (
    Chapter,
    Character,
    CharacterReferenceImage,
    CharacterVisualProfile,
    IllustrationAsset,
    NarrativeBlock,
    Project,
    Scene,
    StoryBible,
)
from app.providers import LLMProviderError, OpenAICompatibleImageClient, OpenAICompatibleTextClient


class EchoPayload(BaseModel):
    ok: bool
    channel: str


ONE_PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4HWP4DwQACfsD"
    "fQ6OeuQAAAAASUVORK5CYII="
)


def test_openai_client_sends_auth_header_and_parses_structured_json():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"ok": true, "channel": "chat"}',
                        }
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 9, "total_tokens": 21},
            },
        )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    result = client.complete_json(
        agent_name="smoke",
        model="gpt-4o-mini",
        response_model=EchoPayload,
        messages=[
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": "Return ok/channel."},
        ],
    )

    assert requests[0].headers["Authorization"] == "Bearer test-key"
    assert requests[0].url.path == "/v1/chat/completions"
    assert result.payload == {"ok": True, "channel": "chat"}
    assert result.trace["agent"] == "smoke"
    assert result.trace["attempts"] == 1


def test_openai_client_repairs_invalid_json_once_before_failing():
    call_count = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        call_count["count"] += 1
        if call_count["count"] == 1:
            content = "not valid json at all"
        else:
            content = '{"ok": true, "channel": "repair"}'
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 6, "total_tokens": 13},
            },
        )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    result = client.complete_json(
        agent_name="repair-test",
        model="gpt-4o-mini",
        response_model=EchoPayload,
        messages=[
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": "Return ok/channel."},
        ],
    )

    assert call_count["count"] == 2
    assert result.payload["channel"] == "repair"
    assert result.trace["attempts"] == 2


def test_openai_client_surfaces_provider_error_messages():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "bad token"}},
        )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    with pytest.raises(LLMProviderError, match="bad token"):
        client.complete_json(
            agent_name="auth-test",
            model="gpt-4o-mini",
            response_model=EchoPayload,
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": "Return ok/channel."},
            ],
        )


def test_openai_client_wraps_transport_errors_as_provider_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failed", request=request)

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    with pytest.raises(LLMProviderError, match="dns failed"):
        client.complete_json(
            agent_name="transport-test",
            model="gpt-4o-mini",
            response_model=EchoPayload,
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": "Return ok/channel."},
            ],
        )


def test_openai_client_retries_transport_errors_once_before_failing():
    call_count = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["count"] += 1
        if call_count["count"] == 1:
            raise httpx.ConnectError("dns failed", request=request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok": true, "channel": "retry"}'}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
            },
        )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    result = client.complete_json(
        agent_name="transport-retry",
        model="gpt-4o-mini",
        response_model=EchoPayload,
        messages=[
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": "Return ok/channel."},
        ],
    )

    assert call_count["count"] == 2
    assert result.payload == {"ok": True, "channel": "retry"}


def test_openai_image_client_decodes_base64_images_and_sends_generation_request():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"b64_json": ONE_PIXEL_PNG_BASE64, "revised_prompt": "scene still one"},
                    {"b64_json": ONE_PIXEL_PNG_BASE64, "revised_prompt": "scene still two"},
                ],
                "usage": {"total_tokens": 0},
            },
        )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = OpenAICompatibleImageClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=20,
        default_model="gpt-image-1",
        http_client=http_client,
    )

    result = client.generate_images(
        model="gpt-image-1",
        prompt="cinematic still",
        candidate_count=2,
        size="1024x1024",
    )

    assert requests[0].headers["Authorization"] == "Bearer test-key"
    assert requests[0].url.path == "/v1/images/generations"
    sent_json = json.loads(requests[0].content.decode("utf-8"))
    assert sent_json["model"] == "gpt-image-1"
    assert sent_json["prompt"] == "cinematic still"
    assert sent_json["n"] == 2
    assert len(result["images"]) == 2
    assert result["images"][0].payload_bytes == base64.b64decode(ONE_PIXEL_PNG_BASE64)
    assert result["trace"]["model"] == "gpt-image-1"


def test_openai_image_client_wraps_transport_errors_as_provider_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failed", request=request)

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = OpenAICompatibleImageClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=20,
        default_model="gpt-image-1",
        http_client=http_client,
    )

    with pytest.raises(LLMProviderError, match="dns failed"):
        client.generate_images(
            model="gpt-image-1",
            prompt="cinematic still",
            candidate_count=1,
            size="1024x1024",
        )


def test_openai_image_client_retries_transport_errors_once_before_failing():
    call_count = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["count"] += 1
        if call_count["count"] == 1:
            raise httpx.ConnectError("dns failed", request=request)
        return httpx.Response(
            200,
            json={
                "data": [{"b64_json": ONE_PIXEL_PNG_BASE64, "revised_prompt": "retry success"}],
                "usage": {"total_tokens": 0},
            },
        )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = OpenAICompatibleImageClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=20,
        default_model="gpt-image-1",
        http_client=http_client,
    )

    result = client.generate_images(
        model="gpt-image-1",
        prompt="cinematic still",
        candidate_count=1,
        size="1024x1024",
    )

    assert call_count["count"] == 2
    assert len(result["images"]) == 1


def test_openai_image_client_falls_back_to_single_image_requests_when_provider_only_allows_n_one():
    requests = []
    call_count = {"count": 0}
    progress_events = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_json = json.loads(request.content.decode("utf-8"))
        requests.append(sent_json)
        call_count["count"] += 1
        if call_count["count"] == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "[Bad Request] Validation error for body application/json: Input doesn't match one of allowed values of enum: [1]"
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": ONE_PIXEL_PNG_BASE64,
                        "revised_prompt": f"single candidate {call_count['count'] - 1}",
                    }
                ],
                "usage": {"total_tokens": 0},
            },
        )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = OpenAICompatibleImageClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=20,
        default_model="flux-schnell",
        http_client=http_client,
    )

    result = client.generate_images(
        model="flux-schnell",
        prompt="cinematic still",
        candidate_count=3,
        size="1024x1024",
        on_progress=progress_events.append,
    )

    assert [item["n"] for item in requests] == [3, 1, 1, 1]
    assert len(result["images"]) == 3
    assert result["trace"]["model"] == "flux-schnell"
    assert result["trace"]["fallback"] == "single-candidate-requests"
    assert any("改为顺序渲染" in event["text"] for event in progress_events)
    assert any("第 1/3 张候选" in event["text"] for event in progress_events)
    assert any("第 3/3 张候选已完成" in event["text"] for event in progress_events)


def test_openai_image_client_falls_back_to_chat_completion_image_links_when_images_endpoint_is_unavailable():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/v1/images/generations":
            return httpx.Response(
                404,
                text="404 page not found",
                headers={"content-type": "text/plain; charset=utf-8"},
            )
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "![image1](https://example.com/generated/image-1.jpeg) [下载1](https://example.com/generated/image-1.jpeg)"
                            }
                        }
                    ],
                    "usage": {"total_tokens": 12},
                },
            )
        if request.url.path == "/generated/image-1.jpeg":
            return httpx.Response(
                200,
                content=base64.b64decode(ONE_PIXEL_PNG_BASE64),
                headers={"content-type": "image/png"},
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = OpenAICompatibleImageClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=20,
        default_model="flux-schnell",
        http_client=http_client,
    )

    result = client.generate_images(
        model="flux-schnell",
        prompt="cinematic still",
        candidate_count=1,
        size="1024x1024",
    )

    assert requests == [
        ("POST", "/v1/images/generations"),
        ("POST", "/v1/chat/completions"),
        ("GET", "/generated/image-1.jpeg"),
    ]
    assert len(result["images"]) == 1
    assert result["images"][0].payload_bytes == base64.b64decode(ONE_PIXEL_PNG_BASE64)
    assert result["trace"]["model"] == "flux-schnell"
    assert result["trace"]["fallback"] == "chat-completions-image-links"
    assert result["trace"]["endpoint"] == "chat/completions"


def test_visual_prompt_request_includes_canonical_scene_reference_and_extra_guidance():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "public_notes": ["锁定镜头与角色一致性。"],
                                    "prompt_text": "cinematic prompt",
                                    "style_tags": ["cinematic"],
                                    "shot_notes": ["medium close-up"],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    }
                ],
                "usage": {"prompt_tokens": 21, "completion_tokens": 17, "total_tokens": 38},
            },
        )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    text_client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    from app.providers import StoryAgentPipeline

    project = Project(
        title="长街回声",
        genre="悬疑成长",
        tone="冷静、克制、人物驱动",
        era="近未来",
        target_chapter_count=8,
        target_length="8章",
        logline="广播里不断响起未来新闻。",
    )
    project.story_bible = StoryBible(
        world_notes="旧城区的广播会提前播报未来。",
        style_notes="克制、人物驱动。",
        writing_rules=["保持人物一致性"],
    )

    character = Character(
        name="林听",
        role="广播站修复师",
        personality="敏锐、克制",
        goal="找回失踪姐姐",
        speech_style="短句、留白多",
        appearance="黑色短发，深色风衣",
        relationships="与顾昼互相试探",
    )
    character.visual_profile = CharacterVisualProfile(
        visual_anchor="黑色短发、深色风衣、警觉眼神",
        signature_palette="深青、雾银、暖白",
        silhouette_notes="偏瘦轮廓",
        wardrobe_notes="深色风衣与旧式设备包",
        atmosphere_notes="压低情绪波动，保留锋利感",
    )
    character.reference_images = [
        CharacterReferenceImage(filename="linting-ref.png", path="/tmp/linting-ref.png"),
    ]
    project.owned_characters = [character]

    chapter = Chapter(
        order_index=1,
        title="轨道偏移",
        summary="第一次异常广播响起。",
        chapter_goal="让林听意识到广播不是故障。",
        hook="播报提到了尚未发生的事故。",
    )
    scene = Scene(
        title="旧楼档案室",
        scene_type="INT",
        location="旧楼档案室",
        time_of_day="NIGHT",
        cast_names=["林听"],
        objective="确认第一条异常广播的来源。",
        emotional_tone="压抑而锋利",
        visual_prompt="旧版 prompt",
    )
    scene.illustrations = [
        IllustrationAsset(
            candidate_index=2,
            prompt_text="approved canonical still with restrained editorial realism",
            file_path="/tmp/canonical.png",
            thumbnail_path="/tmp/canonical-thumb.png",
            is_canonical=True,
        )
    ]
    chapter.scenes = [scene]
    project.chapters = [chapter]

    pipeline = StoryAgentPipeline(
        client=text_client,
        image_client=None,
        default_model="gpt-4o-mini",
    )

    pipeline.build_visual_prompt(
        project,
        scene,
        [character],
        extra_guidance="保留主图里的冷青色灯光，但让表情更克制",
    )

    request_payload = json.loads(requests[0].content.decode("utf-8"))
    combined_messages = "\n".join(str(item.get("content", "")) for item in request_payload["messages"])
    assert "canonical_scene_illustration" in combined_messages
    assert "approved canonical still with restrained editorial realism" in combined_messages
    assert "保留主图里的冷青色灯光" in combined_messages
    assert "reference_images" in combined_messages


def test_writer_draft_request_includes_story_rules_style_memory_and_quality_constraints():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "public_notes": ["先用具体动作开章，再把关系压力压进对白。"],
                                    "narrative_blocks": [
                                        "第一段",
                                        "第二段",
                                        "第三段",
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    }
                ],
                "usage": {"prompt_tokens": 31, "completion_tokens": 18, "total_tokens": 49},
            },
        )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    text_client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    from app.providers import StoryAgentPipeline

    project = Project(
        title="回声停在四点半",
        genre="都市悬疑",
        tone="克制、冷静、人物压强强",
        era="当代",
        target_chapter_count=6,
        target_length="6章短剧感",
        logline="一通旧案来电把深夜主播重新拖回失踪案。",
    )
    project.story_bible = StoryBible(
        world_notes="旧城区广播站里藏着没有结案的事故。",
        style_notes="近距离贴人，不要把情绪说满。",
        writing_rules=["每章必须有可执行动作", "不要把冲突写成空泛感受"],
        addressing_rules="林听始终称顾昼为顾昼，不叫顾警官。",
        timeline_rules="第一夜到第二天清晨之间不能突然跳过白天调查。",
    )

    previous_chapter = Chapter(
        order_index=1,
        title="失真频段",
        summary="异常广播第一次响起。",
        chapter_goal="让林听意识到来电不是恶作剧。",
        hook="录音里出现了尚未发生的车祸时间。",
        status="drafted",
    )
    previous_chapter.narrative_blocks = [
        NarrativeBlock(
            order_index=1,
            content="林听把耳机摘下来时，指尖还压着那句没来得及播出去的道歉。",
            is_locked=True,
            is_user_edited=True,
        ),
        NarrativeBlock(
            order_index=2,
            content="她没有立刻回头，只先看了一眼玻璃里的自己，像在确认刚才那阵发冷是不是错觉。",
        ),
    ]

    current_chapter = Chapter(
        order_index=2,
        title="回声倒灌",
        summary="顾昼带着旧案照片再次出现，迫使林听正面回应那通来电。",
        chapter_goal="让林听在自保和追查之间做出第一次主动选择。",
        hook="顾昼说，来电里提到的女孩昨晚已经失踪了。",
        status="planned",
    )

    character = Character(
        name="林听",
        role="深夜主播",
        personality="敏感、克制、强撑冷静",
        goal="查清来电来源，确认失踪者是否还活着",
        speech_style="短句，问话时更锋利",
        appearance="短发，深色外套，常年熬夜留下的疲惫感",
        relationships="与顾昼旧账未清，彼此都不肯先示弱",
        signature_line="我不是怕真相，我是怕它来得太晚。",
    )
    project.owned_characters = [character]
    project.chapters = [previous_chapter, current_chapter]

    pipeline = StoryAgentPipeline(
        client=text_client,
        image_client=None,
        default_model="gpt-4o-mini",
    )

    pipeline.write_chapter_draft(
        project,
        current_chapter,
        [previous_chapter],
        extra_guidance="把林听的嘴硬和动作迟疑同时写出来。",
    )

    request_payload = json.loads(requests[0].content.decode("utf-8"))
    combined_messages = "\n".join(str(item.get("content", "")) for item in request_payload["messages"])
    assert "addressing_rules" in combined_messages
    assert "timeline_rules" in combined_messages
    assert "style_memory" in combined_messages
    assert "林听把耳机摘下来时" in combined_messages
    assert "避免以下套话" in combined_messages
    assert "每段必须承担明确的戏剧功能" in combined_messages
    assert "extra_guidance" in combined_messages


def test_reviewer_draft_request_requires_minimal_edits_and_voice_preservation():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "public_notes": ["优先检查称呼和口吻，不在无必要时重写整段。"],
                                    "issues": [],
                                    "continuity_notes": ["Reviewer：这一章的口吻与上一章一致。"],
                                    "decision": "accept",
                                    "severity": "minor",
                                    "decision_reason": "整体可用，仅需最小修订。",
                                    "suggested_guidance": "",
                                    "revised_narrative_blocks": ["原文保持不变。"],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    }
                ],
                "usage": {"prompt_tokens": 27, "completion_tokens": 19, "total_tokens": 46},
            },
        )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    text_client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    from app.providers import StoryAgentPipeline

    project = Project(
        title="凌晨来电",
        genre="都市悬疑",
        tone="克制、压抑、人物驱动",
        era="当代",
        target_chapter_count=4,
        target_length="4章",
        logline="失踪证人的来电把主播拉回旧案。",
    )
    project.story_bible = StoryBible(
        world_notes="深夜节目会收到无法解释的旧案录音。",
        style_notes="保持贴身视角与留白，不要把人物情绪说满。",
        writing_rules=["避免直给总结句"],
        addressing_rules="人名保持固定称呼。",
        timeline_rules="一夜内完成第一轮调查。",
    )
    chapter = Chapter(
        order_index=1,
        title="第一通来电",
        summary="主播在直播中接到奇怪来电。",
        chapter_goal="让他意识到来电指向旧案。",
        hook="来电者说出了只有失踪证人才知道的细节。",
    )
    project.chapters = [chapter]

    pipeline = StoryAgentPipeline(
        client=text_client,
        image_client=None,
        default_model="gpt-4o-mini",
    )

    pipeline.review_chapter_draft(
        project,
        chapter,
        {
            "public_notes": ["先落动作，再收束情绪。"],
            "narrative_blocks": [
                "他把推子往下压了一格，先让自己的呼吸声从耳返里消失。",
                "来电人的第一句话没头没尾，却正好碰在那件旧案最不该被提起的细节上。",
            ],
        },
    )

    request_payload = json.loads(requests[0].content.decode("utf-8"))
    combined_messages = "\n".join(str(item.get("content", "")) for item in request_payload["messages"])
    assert "最小必要改动" in combined_messages
    assert "保留 Writer 原有的句法节奏、措辞锋利度和段落功能" in combined_messages
    assert "不要为了看起来更顺而整段改写" in combined_messages


def test_reviewer_draft_request_includes_quality_flags_for_cliche_detection():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "public_notes": ["优先清理正文里的套话和抽象总结。"],
                                    "issues": ["正文出现高频套话。"],
                                    "continuity_notes": ["Reviewer：已把抽象套话换成更具体的动作反应。"],
                                    "decision": "accept",
                                    "severity": "minor",
                                    "decision_reason": "问题可在当前轮次修正。",
                                    "suggested_guidance": "",
                                    "apply_mode": "apply_revisions",
                                    "revised_narrative_blocks": ["修订后正文。"],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    }
                ],
                "usage": {"prompt_tokens": 33, "completion_tokens": 20, "total_tokens": 53},
            },
        )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    text_client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    from app.providers import StoryAgentPipeline

    project = Project(
        title="雾港夜线",
        genre="都市悬疑",
        tone="克制、贴身、关系压强强",
        era="当代",
        target_chapter_count=4,
        target_length="4章",
        logline="一通旧案来电让旧搭档再次站到同一条调查线索上。",
    )
    project.story_bible = StoryBible(
        world_notes="广播里反复出现旧案录音。",
        style_notes="不要写空泛氛围，要落在动作与反应上。",
        writing_rules=["减少抽象总结"],
        addressing_rules="称呼稳定，不要乱切。",
        timeline_rules="一夜内推进第一轮调查。",
    )
    chapter = Chapter(
        order_index=1,
        title="旧声回流",
        summary="主持人在直播中接到旧案来电。",
        chapter_goal="让他意识到自己无法继续装作无事发生。",
        hook="来电者提到了尚未公开的细节。",
    )
    project.chapters = [chapter]

    pipeline = StoryAgentPipeline(
        client=text_client,
        image_client=None,
        default_model="gpt-4o-mini",
    )

    pipeline.review_chapter_draft(
        project,
        chapter,
        {
            "public_notes": ["先压气氛，再落冲突。"],
            "narrative_blocks": [
                "来电显示亮起的一瞬间，他心中一紧，空气仿佛凝固，某种说不清的感觉又回来了。",
            ],
        },
    )

    request_payload = json.loads(requests[0].content.decode("utf-8"))
    combined_messages = "\n".join(str(item.get("content", "")) for item in request_payload["messages"])
    assert "quality_flags" in combined_messages
    assert "心中一紧" in combined_messages
    assert "quality_flags 非空时不要使用 preserve_writer" in combined_messages


def test_story_agent_pipeline_prefers_langfuse_prompt_registry_messages_for_writer_draft():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "public_notes": ["按 Langfuse prompt 生成。"],
                                    "narrative_blocks": ["第一段", "第二段"],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            },
        )

    class FakePromptRegistry:
        def __init__(self):
            self.calls = []

        def resolve_messages(self, name, *, variables, fallback_messages):
            self.calls.append(
                {
                    "name": name,
                    "variables": variables,
                    "fallback_messages": fallback_messages,
                }
            )
            return SimpleNamespace(
                messages=[
                    {"role": "system", "content": "LANGFUSE SYSTEM WRITER"},
                    {"role": "user", "content": f"LANGFUSE USER {variables['chapter_title']}"},
                ],
                source="langfuse",
                version=3,
                label="staging",
                error_message="",
            )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    text_client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    from app.providers import StoryAgentPipeline

    project = Project(
        title="回声停在四点半",
        genre="都市悬疑",
        tone="克制、冷静、人物压强强",
        era="当代",
        target_chapter_count=6,
        target_length="6章短剧感",
        logline="一通旧案来电把深夜主播重新拖回失踪案。",
    )
    chapter = Chapter(
        order_index=2,
        title="回声倒灌",
        summary="顾昼带着旧案照片再次出现。",
        chapter_goal="让林听做出第一次主动选择。",
        hook="来电里的人已经失踪。",
        status="planned",
    )

    prompt_registry = FakePromptRegistry()
    pipeline = StoryAgentPipeline(
        client=text_client,
        image_client=None,
        default_model="gpt-4o-mini",
        prompt_registry=prompt_registry,
    )

    pipeline.write_chapter_draft(project, chapter, [])

    assert prompt_registry.calls
    assert prompt_registry.calls[0]["name"] == "writer_draft"
    assert prompt_registry.calls[0]["variables"]["chapter_title"] == "回声倒灌"
    request_payload = json.loads(requests[0].content.decode("utf-8"))
    assert request_payload["messages"][1]["content"] == "LANGFUSE SYSTEM WRITER"
    assert request_payload["messages"][2]["content"] == "LANGFUSE USER 回声倒灌"


def test_story_agent_pipeline_falls_back_to_local_writer_prompt_when_registry_errors():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "public_notes": ["使用本地 fallback prompt。"],
                                    "narrative_blocks": ["第一段", "第二段"],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            },
        )

    class BrokenPromptRegistry:
        def resolve_messages(self, name, *, variables, fallback_messages):
            raise RuntimeError(f"prompt registry unavailable for {name}")

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    text_client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    from app.providers import StoryAgentPipeline

    project = Project(
        title="回声停在四点半",
        genre="都市悬疑",
        tone="克制、冷静、人物压强强",
        era="当代",
        target_chapter_count=6,
        target_length="6章短剧感",
        logline="一通旧案来电把深夜主播重新拖回失踪案。",
    )
    chapter = Chapter(
        order_index=2,
        title="回声倒灌",
        summary="顾昼带着旧案照片再次出现。",
        chapter_goal="让林听做出第一次主动选择。",
        hook="来电里的人已经失踪。",
        status="planned",
    )

    pipeline = StoryAgentPipeline(
        client=text_client,
        image_client=None,
        default_model="gpt-4o-mini",
        prompt_registry=BrokenPromptRegistry(),
    )

    pipeline.write_chapter_draft(project, chapter, [])

    request_payload = json.loads(requests[0].content.decode("utf-8"))
    combined_messages = "\n".join(str(item.get("content", "")) for item in request_payload["messages"])
    assert "每段必须承担明确的戏剧功能" in combined_messages


def test_story_agent_pipeline_prefers_langfuse_prompt_registry_messages_for_visual_profile():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "public_notes": ["按 Langfuse prompt 生成视觉档案。"],
                                    "signature_line": "她每一次停顿都像在重新计价风险。",
                                    "visual_anchor": "黑色短发，旧风衣，警觉眼神",
                                    "signature_palette": "深青、旧银、暖白",
                                    "silhouette_notes": "偏瘦轮廓",
                                    "wardrobe_notes": "旧风衣与录音包",
                                    "atmosphere_notes": "保留压抑与锋利",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 18, "completion_tokens": 12, "total_tokens": 30},
            },
        )

    class FakePromptRegistry:
        def __init__(self):
            self.calls = []

        def resolve_messages(self, name, *, variables, fallback_messages):
            self.calls.append({"name": name, "variables": variables})
            return SimpleNamespace(
                messages=[
                    {"role": "system", "content": "LANGFUSE SYSTEM VISUAL PROFILE"},
                    {"role": "user", "content": f"LANGFUSE USER {variables['character_name']}"},
                ],
                source="langfuse",
                version=8,
                label="staging",
                error_message="",
            )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    text_client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    from app.providers import StoryAgentPipeline

    project = Project(
        title="长街回声",
        genre="悬疑成长",
        tone="冷静、克制、人物驱动",
        era="近未来",
        target_chapter_count=8,
        target_length="8章",
        logline="广播里不断响起未来新闻。",
    )
    character = Character(
        name="林听",
        role="广播站修复师",
        personality="敏锐、克制",
        goal="找回失踪姐姐",
        speech_style="短句、留白多",
        appearance="黑色短发，深色风衣",
        relationships="与顾昼互相试探",
    )

    prompt_registry = FakePromptRegistry()
    pipeline = StoryAgentPipeline(
        client=text_client,
        image_client=None,
        default_model="gpt-4o-mini",
        prompt_registry=prompt_registry,
    )

    pipeline.build_character_profile(project, character)

    assert prompt_registry.calls
    assert prompt_registry.calls[0]["name"] == "visual_profile"
    assert prompt_registry.calls[0]["variables"]["character_name"] == "林听"
    request_payload = json.loads(requests[0].content.decode("utf-8"))
    assert request_payload["messages"][1]["content"] == "LANGFUSE SYSTEM VISUAL PROFILE"
    assert request_payload["messages"][2]["content"] == "LANGFUSE USER 林听"


def test_story_agent_pipeline_prefers_langfuse_prompt_registry_messages_for_writer_scenes():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "public_notes": ["按 Langfuse prompt 拆场。"],
                                    "scenes": [
                                        {
                                            "title": "旧楼档案室",
                                            "scene_type": "INT",
                                            "location": "旧楼档案室",
                                            "time_of_day": "NIGHT",
                                            "cast_names": ["林听"],
                                            "objective": "确认第一条异常广播的来源。",
                                            "emotional_tone": "压抑而锋利",
                                            "dialogues": [
                                                {
                                                    "speaker": "林听",
                                                    "parenthetical": "",
                                                    "content": "这不是故障。",
                                                }
                                            ],
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 16, "completion_tokens": 14, "total_tokens": 30},
            },
        )

    class FakePromptRegistry:
        def __init__(self):
            self.calls = []

        def resolve_messages(self, name, *, variables, fallback_messages):
            self.calls.append({"name": name, "variables": variables})
            return SimpleNamespace(
                messages=[
                    {"role": "system", "content": "LANGFUSE SYSTEM WRITER SCENES"},
                    {"role": "user", "content": f"LANGFUSE USER {variables['chapter_title']}"},
                ],
                source="langfuse",
                version=5,
                label="staging",
                error_message="",
            )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    text_client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    from app.providers import StoryAgentPipeline

    project = Project(
        title="长街回声",
        genre="悬疑成长",
        tone="冷静、克制、人物驱动",
        era="近未来",
        target_chapter_count=8,
        target_length="8章",
        logline="广播里不断响起未来新闻。",
    )
    chapter = Chapter(
        order_index=1,
        title="轨道偏移",
        summary="第一次异常广播响起。",
        chapter_goal="让林听意识到广播不是故障。",
        hook="播报提到了尚未发生的事故。",
    )

    prompt_registry = FakePromptRegistry()
    pipeline = StoryAgentPipeline(
        client=text_client,
        image_client=None,
        default_model="gpt-4o-mini",
        prompt_registry=prompt_registry,
    )

    pipeline.write_chapter_scenes(project, chapter, [])

    assert prompt_registry.calls
    assert prompt_registry.calls[0]["name"] == "writer_scenes"
    assert prompt_registry.calls[0]["variables"]["chapter_title"] == "轨道偏移"
    request_payload = json.loads(requests[0].content.decode("utf-8"))
    assert request_payload["messages"][1]["content"] == "LANGFUSE SYSTEM WRITER SCENES"
    assert request_payload["messages"][2]["content"] == "LANGFUSE USER 轨道偏移"


def test_story_agent_pipeline_prefers_langfuse_prompt_registry_messages_for_reviewer_scenes():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "public_notes": ["按 Langfuse prompt 审校场景。"],
                                    "issues": [],
                                    "continuity_notes": ["场景关系成立。"],
                                    "decision": "accept",
                                    "severity": "minor",
                                    "decision_reason": "结构可用。",
                                    "suggested_guidance": "",
                                    "revised_scenes": [
                                        {
                                            "title": "旧楼档案室",
                                            "scene_type": "INT",
                                            "location": "旧楼档案室",
                                            "time_of_day": "NIGHT",
                                            "cast_names": ["林听"],
                                            "objective": "确认第一条异常广播的来源。",
                                            "emotional_tone": "压抑而锋利",
                                            "dialogues": [
                                                {
                                                    "speaker": "林听",
                                                    "parenthetical": "",
                                                    "content": "这不是故障。",
                                                }
                                            ],
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 16, "completion_tokens": 14, "total_tokens": 30},
            },
        )

    class FakePromptRegistry:
        def __init__(self):
            self.calls = []

        def resolve_messages(self, name, *, variables, fallback_messages):
            self.calls.append({"name": name, "variables": variables})
            return SimpleNamespace(
                messages=[
                    {"role": "system", "content": "LANGFUSE SYSTEM REVIEWER SCENES"},
                    {"role": "user", "content": f"LANGFUSE USER {variables['chapter_title']}"},
                ],
                source="langfuse",
                version=6,
                label="staging",
                error_message="",
            )

    http_client = httpx.Client(
        base_url="https://example.com/v1",
        transport=httpx.MockTransport(handler),
    )
    text_client = OpenAICompatibleTextClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        timeout_seconds=15,
        default_model="gpt-4o-mini",
        http_client=http_client,
    )

    from app.providers import StoryAgentPipeline

    project = Project(
        title="长街回声",
        genre="悬疑成长",
        tone="冷静、克制、人物驱动",
        era="近未来",
        target_chapter_count=8,
        target_length="8章",
        logline="广播里不断响起未来新闻。",
    )
    chapter = Chapter(
        order_index=1,
        title="轨道偏移",
        summary="第一次异常广播响起。",
        chapter_goal="让林听意识到广播不是故障。",
        hook="播报提到了尚未发生的事故。",
    )

    scenes_payload = {
        "scenes": [
            {
                "title": "旧楼档案室",
                "scene_type": "INT",
                "location": "旧楼档案室",
                "time_of_day": "NIGHT",
                "cast_names": ["林听"],
                "objective": "确认第一条异常广播的来源。",
                "emotional_tone": "压抑而锋利",
                "dialogues": [{"speaker": "林听", "parenthetical": "", "content": "这不是故障。"}],
            }
        ]
    }

    prompt_registry = FakePromptRegistry()
    pipeline = StoryAgentPipeline(
        client=text_client,
        image_client=None,
        default_model="gpt-4o-mini",
        prompt_registry=prompt_registry,
    )

    pipeline.review_chapter_scenes(project, chapter, scenes_payload)

    assert prompt_registry.calls
    assert prompt_registry.calls[0]["name"] == "reviewer_scenes"
    assert prompt_registry.calls[0]["variables"]["chapter_title"] == "轨道偏移"
    request_payload = json.loads(requests[0].content.decode("utf-8"))
    assert request_payload["messages"][1]["content"] == "LANGFUSE SYSTEM REVIEWER SCENES"
    assert request_payload["messages"][2]["content"] == "LANGFUSE USER 轨道偏移"
