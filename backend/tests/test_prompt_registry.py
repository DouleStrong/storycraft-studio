import base64
import json

import httpx

from app.prompt_registry import LangfusePromptRegistry


def test_langfuse_prompt_registry_fetches_chat_prompt_and_compiles_variables():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "name": "writer_draft",
                "version": 7,
                "type": "chat",
                "prompt": [
                    {"role": "system", "content": "系统提示：{{project_title}}"},
                    {"role": "user", "content": "上下文：{{context_json}}"},
                ],
                "config": {"model": "gpt-4o-mini"},
            },
        )

    registry = LangfusePromptRegistry(
        base_url="http://langfuse.local",
        public_key="pk-test",
        secret_key="sk-test",
        prompt_label="staging",
        cache_ttl_seconds=120,
        http_client=httpx.Client(
            base_url="http://langfuse.local",
            transport=httpx.MockTransport(handler),
        ),
    )

    result = registry.resolve_messages(
        "writer_draft",
        variables={
            "project_title": "长街回声",
            "context_json": json.dumps({"chapter": "第一章"}, ensure_ascii=False),
        },
        fallback_messages=[{"role": "system", "content": "fallback"}],
    )

    assert result.source == "langfuse"
    assert result.version == 7
    assert result.label == "staging"
    assert result.messages[0]["content"] == "系统提示：长街回声"
    assert "第一章" in result.messages[1]["content"]
    assert requests[0].url.path == "/api/public/v2/prompts/writer_draft"
    assert requests[0].url.params["label"] == "staging"
    auth_header = requests[0].headers["Authorization"]
    assert auth_header.startswith("Basic ")
    assert base64.b64decode(auth_header.removeprefix("Basic ")).decode("utf-8") == "pk-test:sk-test"


def test_langfuse_prompt_registry_falls_back_to_local_messages_when_request_fails():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    registry = LangfusePromptRegistry(
        base_url="http://langfuse.local",
        public_key="pk-test",
        secret_key="sk-test",
        prompt_label="production",
        cache_ttl_seconds=120,
        http_client=httpx.Client(
            base_url="http://langfuse.local",
            transport=httpx.MockTransport(handler),
        ),
    )

    fallback_messages = [{"role": "system", "content": "local fallback"}]
    result = registry.resolve_messages(
        "writer_draft",
        variables={"project_title": "长街回声"},
        fallback_messages=fallback_messages,
    )

    assert result.source == "fallback"
    assert result.messages == fallback_messages
    assert result.error_message
