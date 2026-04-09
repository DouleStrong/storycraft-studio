import base64
import json

import httpx
import pytest
from pydantic import BaseModel

from app.models import (
    Chapter,
    Character,
    CharacterReferenceImage,
    CharacterVisualProfile,
    IllustrationAsset,
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
