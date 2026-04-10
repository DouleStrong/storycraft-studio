from __future__ import annotations

import base64
import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .models import Chapter, Character, IllustrationAsset, Project, Scene
from .prompt_registry import LangfusePromptRegistry, PromptResolution


class LLMProviderError(RuntimeError):
    pass


class LLMConfigurationError(LLMProviderError):
    pass


class StructuredOutputError(LLMProviderError):
    pass


@dataclass(slots=True)
class StructuredAgentResponse:
    payload: dict[str, Any]
    raw_text: str
    trace: dict[str, Any]
    input_summary: str = ""
    prompt_preview: str = ""
    output_summary: str = ""


def _model_json_schema(model_class: type[BaseModel]) -> dict[str, Any]:
    if hasattr(model_class, "model_json_schema"):
        return model_class.model_json_schema()
    return model_class.schema()


def _validate_model_payload(model_class: type[BaseModel], payload: Any) -> dict[str, Any]:
    if hasattr(model_class, "model_validate"):
        model = model_class.model_validate(payload)
        return model.model_dump()
    model = model_class.parse_obj(payload)
    return model.dict()


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _extract_json_candidate(text: str) -> str:
    stripped = _strip_markdown_fences(text)
    if not stripped:
        raise StructuredOutputError("Model returned an empty response.")

    try:
        json.loads(stripped)
        return stripped
    except json.JSONDecodeError:
        pass

    object_start = stripped.find("{")
    object_end = stripped.rfind("}")
    array_start = stripped.find("[")
    array_end = stripped.rfind("]")

    candidates: list[str] = []
    if object_start != -1 and object_end != -1 and object_end > object_start:
        candidates.append(stripped[object_start : object_end + 1])
    if array_start != -1 and array_end != -1 and array_end > array_start:
        candidates.append(stripped[array_start : array_end + 1])

    for candidate in candidates:
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            continue

    raise StructuredOutputError("Model response did not contain valid JSON.")


def _content_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        text_parts = []
        for item in value:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
            elif isinstance(item, dict) and "content" in item:
                text_parts.append(str(item["content"]))
            else:
                text_parts.append(str(item))
        return "".join(text_parts)
    if value is None:
        return ""
    return str(value)


def _raise_provider_transport_error(exc: httpx.HTTPError, *, action: str) -> None:
    raise LLMProviderError(f"{action} failed: {exc}") from exc


def _run_with_transport_retry(
    *,
    action: str,
    operation: Callable[[], Any],
    attempts: int = 2,
    delay_seconds: float = 0.35,
) -> Any:
    last_exc: httpx.HTTPError | None = None
    for attempt_index in range(attempts):
        try:
            return operation()
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt_index == attempts - 1:
                break
            time.sleep(delay_seconds * (attempt_index + 1))
    assert last_exc is not None
    _raise_provider_transport_error(last_exc, action=action)


class OpenAICompatibleTextClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: int,
        default_model: str,
        http_client: httpx.Client | None = None,
    ):
        if not base_url:
            raise LLMConfigurationError("OPENAI_BASE_URL is not configured.")
        if not api_key:
            raise LLMConfigurationError("OPENAI_API_KEY is not configured.")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.default_model = default_model
        self._client = http_client or httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            trust_env=False,
        )

    def list_models(self) -> list[dict[str, Any]]:
        response = _run_with_transport_retry(
            action="Listing provider models",
            operation=lambda: self._client.get("/models", headers=self._headers),
        )
        payload = self._read_json_response(response)
        return payload.get("data", [])

    def complete_json(
        self,
        *,
        agent_name: str,
        model: str | None,
        response_model: type[BaseModel],
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1800,
        on_stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> StructuredAgentResponse:
        selected_model = model or self.default_model
        schema_json = json.dumps(_model_json_schema(response_model), ensure_ascii=False, indent=2)
        base_messages = [
            {
                "role": "system",
                "content": (
                    "Return valid JSON only. Do not wrap the JSON in markdown fences. "
                    "Do not include explanation before or after the JSON."
                ),
            },
            *messages,
        ]

        original_response = ""
        validation_error = ""
        usage: dict[str, Any] | None = None
        attempts = 0

        for attempt_index in range(2):
            attempts = attempt_index + 1
            if attempt_index == 0:
                request_messages = [
                    *base_messages,
                    {"role": "system", "content": f"Target JSON schema:\n{schema_json}"},
                ]
            else:
                request_messages = [
                    {
                        "role": "system",
                        "content": (
                            "You repair invalid JSON. Return valid JSON only, matching the requested schema exactly."
                        ),
                    },
                    {"role": "user", "content": f"Schema:\n{schema_json}"},
                    {"role": "user", "content": f"Previous invalid response:\n{original_response}"},
                    {"role": "user", "content": f"Validation error:\n{validation_error}"},
                ]

            raw_text, usage = self._chat_completion(
                model=selected_model,
                messages=request_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                on_stream=on_stream,
            )

            try:
                parsed_payload = json.loads(_extract_json_candidate(raw_text))
                validated = _validate_model_payload(response_model, parsed_payload)
                return StructuredAgentResponse(
                    payload=validated,
                    raw_text=raw_text,
                    trace={
                        "agent": agent_name,
                        "model": selected_model,
                        "attempts": attempts,
                        "repair_used": attempt_index == 1,
                        "usage": usage or {},
                        "stream_text": self._trim_stream_text(raw_text),
                    },
                )
            except (json.JSONDecodeError, ValidationError, StructuredOutputError, ValueError) as exc:
                original_response = raw_text
                validation_error = str(exc)
                if attempt_index == 1:
                    raise StructuredOutputError(
                        f"{agent_name} returned invalid structured output after repair: {exc}"
                    ) from exc

        raise StructuredOutputError(f"{agent_name} did not return valid JSON.")

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        on_stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if on_stream is not None:
            try:
                return self._chat_completion_stream(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    on_stream=on_stream,
                )
            except LLMProviderError:
                pass

        response = _run_with_transport_retry(
            action="Chat completion request",
            operation=lambda: self._client.post(
                "/chat/completions",
                headers=self._headers,
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            ),
        )
        payload = self._read_json_response(response)
        try:
            message_content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("Provider response did not include a completion message.") from exc

        return _content_to_text(message_content).strip(), payload.get("usage", {})

    def _chat_completion_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        on_stream: Callable[[dict[str, Any]], None],
    ) -> tuple[str, dict[str, Any]]:
        def perform_stream() -> tuple[str, dict[str, Any]]:
            usage: dict[str, Any] = {}
            chunks: list[str] = []
            with self._client.stream(
                "POST",
                "/chat/completions",
                headers=self._headers,
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
            ) as response:
                if response.is_error:
                    raise LLMProviderError(f"Provider returned HTTP {response.status_code}: {response.text[:200]}")

                for raw_line in response.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    if data == "[DONE]":
                        break
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    if isinstance(payload.get("usage"), dict):
                        usage = payload["usage"]

                    choices = payload.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    delta_text = _content_to_text(delta.get("content"))
                    if not delta_text:
                        continue
                    chunks.append(delta_text)
                    on_stream(
                        {
                            "delta": delta_text,
                            "text": self._trim_stream_text("".join(chunks)),
                        }
                    )
            return "".join(chunks).strip(), usage

        return _run_with_transport_retry(
            action="Streaming chat completion request",
            operation=perform_stream,
        )

    @staticmethod
    def _trim_stream_text(text: str, limit: int = 4000) -> str:
        if len(text) <= limit:
            return text
        return text[-limit:]

    def _read_json_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMProviderError(f"Provider returned non-JSON response: {response.text[:200]}") from exc

        if response.is_error:
            raise LLMProviderError(self._error_message(payload))

        return payload

    @staticmethod
    def _error_message(payload: dict[str, Any]) -> str:
        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            return str(error_payload.get("message") or error_payload)
        return str(error_payload or payload)


@dataclass(slots=True)
class GeneratedImagePayload:
    payload_bytes: bytes
    media_type: str
    revised_prompt: str = ""


class OpenAICompatibleImageClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: int,
        default_model: str,
        http_client: httpx.Client | None = None,
    ):
        if not base_url:
            raise LLMConfigurationError("OPENAI_BASE_URL is not configured.")
        if not api_key:
            raise LLMConfigurationError("OPENAI_API_KEY is not configured.")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.default_model = default_model
        self._client = http_client or httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            trust_env=False,
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def generate_images(
        self,
        *,
        model: str | None,
        prompt: str,
        candidate_count: int,
        size: str,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        selected_model = model or self.default_model
        try:
            return self._generate_images_request(
                model=selected_model,
                prompt=prompt,
                candidate_count=candidate_count,
                size=size,
            )
        except LLMProviderError as exc:
            error_message = str(exc)
            if self._should_fallback_to_single_candidate_requests(error_message, candidate_count):
                if on_progress is not None:
                    on_progress(
                        {
                            "text": f"当前图像服务一次只接受 1 张候选，已改为顺序渲染 {candidate_count} 张剧照。",
                            "progress": 72,
                            "final": False,
                        }
                    )
                return self._generate_images_one_by_one(
                    model=selected_model,
                    prompt=prompt,
                    candidate_count=candidate_count,
                    size=size,
                    on_progress=on_progress,
                )

            if self._should_try_chat_completions_image_fallback(error_message):
                if on_progress is not None:
                    on_progress(
                        {
                            "text": "当前图像服务主图片接口不可用，已切换到兼容聊天出图通道继续渲染。",
                            "progress": 72,
                            "final": False,
                        }
                    )
                return self._generate_images_via_chat_completions(
                    model=selected_model,
                    prompt=prompt,
                    candidate_count=candidate_count,
                    on_progress=on_progress,
                )

            raise

    def _generate_images_request(
        self,
        *,
        model: str,
        prompt: str,
        candidate_count: int,
        size: str,
    ) -> dict[str, Any]:
        response = _run_with_transport_retry(
            action="Image generation request",
            operation=lambda: self._client.post(
                "/images/generations",
                headers=self._headers,
                json={
                    "model": model,
                    "prompt": prompt,
                    "n": candidate_count,
                    "size": size,
                    "response_format": "b64_json",
                },
            ),
        )
        payload = self._read_json_response(response)
        images = self._extract_images(payload, expected_count=candidate_count)
        return {
            "images": images[:candidate_count],
            "trace": {
                "agent": "image_generation",
                "model": model,
                "attempts": 1,
                "usage": payload.get("usage", {}),
                "endpoint": "images/generations",
            },
        }

    def _generate_images_one_by_one(
        self,
        *,
        model: str,
        prompt: str,
        candidate_count: int,
        size: str,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        images: list[GeneratedImagePayload] = []
        aggregated_usage: dict[str, Any] = {}
        for index in range(candidate_count):
            ordinal = index + 1
            if on_progress is not None:
                progress = min(94, 72 + int(index * 20 / max(candidate_count, 1)))
                on_progress(
                    {
                        "text": f"正在顺序渲染第 {ordinal}/{candidate_count} 张候选剧照。",
                        "progress": progress,
                        "final": False,
                    }
                )
            result = self._generate_images_request(
                model=model,
                prompt=prompt,
                candidate_count=1,
                size=size,
            )
            images.extend(result["images"])
            usage = result["trace"].get("usage", {})
            for key, value in usage.items():
                if isinstance(value, (int, float)):
                    aggregated_usage[key] = aggregated_usage.get(key, 0) + value
                else:
                    aggregated_usage[key] = value
            if on_progress is not None:
                progress = min(95, 72 + int((ordinal) * 20 / max(candidate_count, 1)))
                on_progress(
                    {
                        "text": f"第 {ordinal}/{candidate_count} 张候选已完成，继续处理其余候选。",
                        "progress": progress,
                        "final": ordinal == candidate_count,
                    }
                )

        return {
            "images": images[:candidate_count],
            "trace": {
                "agent": "image_generation",
                "model": model,
                "attempts": candidate_count,
                "usage": aggregated_usage,
                "fallback": "single-candidate-requests",
                "endpoint": "images/generations",
            },
        }

    def _generate_images_via_chat_completions(
        self,
        *,
        model: str,
        prompt: str,
        candidate_count: int,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        images: list[GeneratedImagePayload] = []
        aggregated_usage: dict[str, Any] = {}

        for index in range(candidate_count):
            ordinal = index + 1
            if on_progress is not None:
                progress = min(94, 72 + int(index * 20 / max(candidate_count, 1)))
                on_progress(
                    {
                        "text": f"正在通过兼容聊天通道渲染第 {ordinal}/{candidate_count} 张候选剧照。",
                        "progress": progress,
                        "final": False,
                    }
                )

            result = self._generate_single_image_via_chat_completion(model=model, prompt=prompt)
            images.append(result["image"])
            usage = result.get("usage", {})
            for key, value in usage.items():
                if isinstance(value, (int, float)):
                    aggregated_usage[key] = aggregated_usage.get(key, 0) + value
                else:
                    aggregated_usage[key] = value

            if on_progress is not None:
                progress = min(95, 72 + int(ordinal * 20 / max(candidate_count, 1)))
                on_progress(
                    {
                        "text": f"兼容聊天通道已完成第 {ordinal}/{candidate_count} 张候选剧照。",
                        "progress": progress,
                        "final": ordinal == candidate_count,
                    }
                )

        return {
            "images": images[:candidate_count],
            "trace": {
                "agent": "image_generation",
                "model": model,
                "attempts": candidate_count,
                "usage": aggregated_usage,
                "fallback": "chat-completions-image-links",
                "endpoint": "chat/completions",
            },
        }

    def _generate_single_image_via_chat_completion(self, *, model: str, prompt: str) -> dict[str, Any]:
        response = _run_with_transport_retry(
            action="Image chat fallback request",
            operation=lambda: self._client.post(
                "/chat/completions",
                headers=self._headers,
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Generate one image for the following prompt and return the generated image result.\n\n"
                                f"{prompt}"
                            ),
                        }
                    ],
                    "max_tokens": 400,
                },
            ),
        )
        payload = self._read_json_response(response)
        try:
            message_content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("Image chat fallback did not include a completion message.") from exc

        content_text = _content_to_text(message_content).strip()
        image_urls = self._extract_image_urls_from_text(content_text)
        if not image_urls:
            raise LLMProviderError("Image chat fallback did not return any downloadable image URLs.")

        payload_bytes, media_type = self._download_image(image_urls[0])
        return {
            "image": GeneratedImagePayload(payload_bytes=payload_bytes, media_type=media_type),
            "usage": payload.get("usage", {}),
        }

    def _extract_images(self, payload: dict[str, Any], *, expected_count: int) -> list[GeneratedImagePayload]:
        items = payload.get("data")
        if not isinstance(items, list) or not items:
            raise LLMProviderError("Image provider did not return any images.")

        images: list[GeneratedImagePayload] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            if item.get("b64_json"):
                payload_bytes = self._decode_base64_image(item["b64_json"])
                media_type = "image/png"
            elif item.get("url"):
                payload_bytes, media_type = self._download_image(item["url"])
            else:
                continue

            images.append(
                GeneratedImagePayload(
                    payload_bytes=payload_bytes,
                    media_type=media_type,
                    revised_prompt=str(item.get("revised_prompt") or ""),
                )
            )

        if len(images) < expected_count:
            raise LLMProviderError(
                f"Image provider returned {len(images)} images, expected at least {expected_count}."
            )
        return images

    @staticmethod
    def _should_fallback_to_single_candidate_requests(error_message: str, candidate_count: int) -> bool:
        if candidate_count <= 1:
            return False
        normalized = error_message.lower()
        return "allowed values of enum: [1]" in normalized or ("enum: [1]" in normalized and "validation error" in normalized)

    @staticmethod
    def _should_try_chat_completions_image_fallback(error_message: str) -> bool:
        normalized = error_message.lower()
        return (
            "404 page not found" in normalized
            or "invalid url" in normalized
            or "does not support /images/generations" in normalized
            or "non-json response: 404" in normalized
        )

    @staticmethod
    def _extract_image_urls_from_text(text: str) -> list[str]:
        patterns = [
            r"!\[[^\]]*\]\((https?://[^)\s]+)\)",
            r"\[[^\]]+\]\((https?://[^)\s]+)\)",
            r"(https?://[^\s)]+)",
        ]
        urls: list[str] = []
        for pattern in patterns:
            for match in re.findall(pattern, text):
                candidate = str(match).strip().rstrip(".,")
                if candidate and candidate not in urls:
                    urls.append(candidate)
        return urls

    @staticmethod
    def _decode_base64_image(raw_value: str) -> bytes:
        try:
            return base64.b64decode(raw_value)
        except ValueError as exc:
            raise LLMProviderError("Image provider returned invalid base64 image data.") from exc

    def _download_image(self, url: str) -> tuple[bytes, str]:
        response = _run_with_transport_retry(
            action="Image download",
            operation=lambda: self._client.get(url, headers=self._headers),
        )
        if response.is_error:
            raise LLMProviderError(
                f"Image provider returned HTTP {response.status_code} while downloading image: {response.text[:200]}"
            )
        return response.content, response.headers.get("content-type", "image/png")

    def _read_json_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMProviderError(f"Provider returned non-JSON response: {response.text[:200]}") from exc

        if response.is_error:
            raise LLMProviderError(self._error_message(payload))

        return payload

    @staticmethod
    def _error_message(payload: dict[str, Any]) -> str:
        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            return str(error_payload.get("message") or error_payload)
        return str(error_payload or payload)


class StoryBibleUpdateOutput(BaseModel):
    world_notes: str
    style_notes: str
    writing_rules: list[str] = Field(default_factory=list)


class PlannerChapterOutput(BaseModel):
    order_index: int
    title: str
    summary: str
    chapter_goal: str
    hook: str


class PlannerOutput(BaseModel):
    public_notes: list[str] = Field(default_factory=list)
    story_bible_updates: StoryBibleUpdateOutput
    chapters: list[PlannerChapterOutput] = Field(default_factory=list)


class WriterDraftOutput(BaseModel):
    public_notes: list[str] = Field(default_factory=list)
    narrative_blocks: list[str] = Field(default_factory=list)


class ReviewerDraftOutput(BaseModel):
    public_notes: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)
    decision: Literal["accept", "rewrite_writer", "fallback_planner"] = "accept"
    severity: Literal["minor", "moderate", "major", "critical"] = "minor"
    decision_reason: str = ""
    suggested_guidance: str = ""
    apply_mode: Literal["apply_revisions", "preserve_writer"] = "apply_revisions"
    revised_narrative_blocks: list[str] = Field(default_factory=list)


class DialogueOutput(BaseModel):
    speaker: str
    parenthetical: str = ""
    content: str


class SceneOutput(BaseModel):
    title: str
    scene_type: str
    location: str
    time_of_day: str
    cast_names: list[str] = Field(default_factory=list)
    objective: str
    emotional_tone: str
    dialogues: list[DialogueOutput] = Field(default_factory=list)


class WriterScenesOutput(BaseModel):
    public_notes: list[str] = Field(default_factory=list)
    scenes: list[SceneOutput] = Field(default_factory=list)


class ReviewerScenesOutput(BaseModel):
    public_notes: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)
    decision: Literal["accept", "rewrite_writer", "fallback_planner"] = "accept"
    severity: Literal["minor", "moderate", "major", "critical"] = "minor"
    decision_reason: str = ""
    suggested_guidance: str = ""
    revised_scenes: list[SceneOutput] = Field(default_factory=list)


class CharacterVisualProfileOutput(BaseModel):
    public_notes: list[str] = Field(default_factory=list)
    signature_line: str
    visual_anchor: str
    signature_palette: str
    silhouette_notes: str
    wardrobe_notes: str
    atmosphere_notes: str


class VisualPromptOutput(BaseModel):
    public_notes: list[str] = Field(default_factory=list)
    prompt_text: str
    style_tags: list[str] = Field(default_factory=list)
    shot_notes: list[str] = Field(default_factory=list)


class StoryAgentPipeline:
    def __init__(
        self,
        *,
        client: OpenAICompatibleTextClient | None,
        image_client: OpenAICompatibleImageClient | None,
        prompt_registry: LangfusePromptRegistry | None = None,
        default_model: str,
        planner_model: str | None = None,
        writer_model: str | None = None,
        reviewer_model: str | None = None,
        visual_model: str | None = None,
        image_model: str | None = None,
        image_size: str = "1536x1024",
    ):
        self.client = client
        self.image_client = image_client
        self.prompt_registry = prompt_registry
        self.default_model = default_model
        self.planner_model = planner_model or default_model
        self.writer_model = writer_model or default_model
        self.reviewer_model = reviewer_model or default_model
        self.visual_model = visual_model or default_model
        self.image_model = image_model or "gpt-image-1"
        self.image_size = image_size

    @classmethod
    def from_settings(cls, settings) -> "StoryAgentPipeline":
        client = None
        image_client = None
        prompt_registry = None
        if settings.openai_base_url and settings.openai_api_key:
            client = OpenAICompatibleTextClient(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
                timeout_seconds=settings.story_agent_timeout_seconds,
                default_model=settings.openai_model,
            )
            image_client = OpenAICompatibleImageClient(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
                timeout_seconds=settings.story_agent_timeout_seconds,
                default_model=settings.story_agent_image_model or "gpt-image-1",
            )
        if settings.langfuse_base_url and settings.langfuse_public_key and settings.langfuse_secret_key:
            prompt_registry = LangfusePromptRegistry(
                base_url=settings.langfuse_base_url,
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                prompt_label=settings.langfuse_prompt_label,
                cache_ttl_seconds=settings.langfuse_prompt_cache_ttl_seconds,
            )
        return cls(
            client=client,
            image_client=image_client,
            prompt_registry=prompt_registry,
            default_model=settings.openai_model,
            planner_model=settings.story_agent_planner_model,
            writer_model=settings.story_agent_writer_model,
            reviewer_model=settings.story_agent_reviewer_model,
            visual_model=settings.story_agent_visual_model,
            image_model=settings.story_agent_image_model,
            image_size=settings.story_agent_image_size,
        )

    def list_models(self) -> list[dict[str, Any]]:
        return self._require_client().list_models()

    @staticmethod
    def _trim_preview(text: str, limit: int = 320) -> str:
        stripped = " ".join(text.split())
        if len(stripped) <= limit:
            return stripped
        return stripped[: limit - 1].rstrip() + "…"

    def _attach_trace_hints(
        self,
        result: StructuredAgentResponse,
        *,
        input_summary: str,
        prompt_preview: str,
        output_summary: str,
    ) -> StructuredAgentResponse:
        result.input_summary = input_summary
        result.prompt_preview = self._trim_preview(prompt_preview)
        result.output_summary = self._trim_preview(output_summary)
        result.trace["input_summary"] = result.input_summary
        result.trace["prompt_preview"] = result.prompt_preview
        result.trace["output_summary"] = result.output_summary
        return result

    def _resolve_prompt_messages(
        self,
        *,
        prompt_name: str,
        variables: dict[str, Any],
        fallback_messages: list[dict[str, str]],
    ) -> PromptResolution:
        if not self.prompt_registry:
            return PromptResolution(
                name=prompt_name,
                messages=fallback_messages,
                source="fallback",
            )
        try:
            return self.prompt_registry.resolve_messages(
                prompt_name,
                variables=variables,
                fallback_messages=fallback_messages,
            )
        except Exception as exc:
            return PromptResolution(
                name=prompt_name,
                messages=fallback_messages,
                source="fallback",
                error_message=str(exc),
            )

    @staticmethod
    def _attach_prompt_resolution(result: StructuredAgentResponse, prompt_resolution: PromptResolution) -> None:
        prompt_name = getattr(prompt_resolution, "name", None)
        prompt_source = getattr(prompt_resolution, "source", None)
        prompt_version = getattr(prompt_resolution, "version", None)
        prompt_label = getattr(prompt_resolution, "label", None)
        prompt_config = getattr(prompt_resolution, "config", None)
        prompt_error = getattr(prompt_resolution, "error_message", None)

        if prompt_name:
            result.trace["prompt_name"] = prompt_name
        if prompt_source:
            result.trace["prompt_source"] = prompt_source
        if prompt_version is not None:
            result.trace["prompt_version"] = prompt_version
        if prompt_label:
            result.trace["prompt_label"] = prompt_label
        if prompt_config:
            result.trace["prompt_config"] = prompt_config
        if prompt_error:
            result.trace["prompt_registry_error"] = prompt_error

    def smoke_completion(self) -> StructuredAgentResponse:
        return self._complete_json(
            agent_name="smoke",
            model=self.default_model,
            response_model=VisualPromptOutput,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个只输出 JSON 的自检助手。",
                },
                {
                    "role": "user",
                    "content": "返回一个最小 JSON，字段为 prompt_text/style_tags/shot_notes。",
                },
            ],
            temperature=0,
            max_tokens=160,
        )

    def build_character_profile(
        self,
        project: Project,
        character: Character,
        *,
        on_stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> StructuredAgentResponse:
        context = {
            "project": self._project_context(project),
            "character": self._character_context(character),
        }
        prompt_variables = {
            "project_title": project.title,
            "character_name": character.name,
            "context_json": json.dumps(context, ensure_ascii=False, indent=2),
        }
        prompt_resolution = self._resolve_prompt_messages(
            prompt_name="visual_profile",
            variables=prompt_variables,
            fallback_messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 StoryCraft Studio 的 Visual Prompt Agent，负责根据角色资料生成稳定的视觉档案。"
                        "返回的 JSON 必须包含 public_notes，用 2-4 条短句向作者说明你正在强化哪些视觉一致性锚点。"
                        "这些 public_notes 会直接展示给作者，不要泄露系统提示词或安全策略。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请基于以下项目与角色上下文，输出角色视觉档案。"
                        "要兼顾外貌、职业、气质、口吻与目标感，适合后续跨章节写作和剧照生成。\n"
                        f"{prompt_variables['context_json']}"
                    ),
                },
            ],
        )
        result = self._complete_json(
            agent_name="visual-profile",
            model=self.visual_model,
            response_model=CharacterVisualProfileOutput,
            messages=prompt_resolution.messages,
            temperature=0.45,
            max_tokens=1200,
            on_stream=on_stream,
        )
        self._attach_prompt_resolution(result, prompt_resolution)
        return self._attach_trace_hints(
            result,
            input_summary=f"Build a visual profile for character {character.name} in project {project.title}.",
            prompt_preview=f"Generate a reusable visual profile for {character.name} using the current character and project context.",
            output_summary=result.payload.get("visual_anchor", ""),
        )

    def plan_outline(
        self,
        project: Project,
        chapter_count: int,
        *,
        extra_guidance: str = "",
        anchor_chapter: Chapter | None = None,
        on_stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> StructuredAgentResponse:
        context = {
            "project": self._project_context(project),
            "characters": [self._character_context(character) for character in project.characters],
            "requested_chapter_count": chapter_count,
            "extra_guidance": extra_guidance,
            "anchor_chapter": self._chapter_context(anchor_chapter, include_blocks=False, include_scenes=False)
            if anchor_chapter
            else None,
        }
        prompt_variables = {
            "project_title": project.title,
            "chapter_count": chapter_count,
            "extra_guidance": extra_guidance,
            "context_json": json.dumps(context, ensure_ascii=False, indent=2),
        }
        prompt_resolution = self._resolve_prompt_messages(
            prompt_name="planner",
            variables=prompt_variables,
            fallback_messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 StoryCraft Studio 的 Planner Agent。"
                        "你要为单用户创作平台生成灵活的章节故事大纲。"
                        "写作形态是混合叙事：既适合章节阅读，也能自然拆成场景。"
                        "禁止套用固定章法模板，必须让每章承担不同的推进功能。"
                        "返回 JSON 时先写 public_notes，用 3-5 条短句告诉作者你在怎样铺排冲突、人物关系和 hook。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请基于以下上下文，生成 story_bible_updates 和 chapters。"
                        "chapter_count 必须与请求一致；章节标题、summary、chapter_goal、hook 都要彼此区分，"
                        "并直接服务于人物关系、冲突升级和悬念牵引。\n"
                        f"{prompt_variables['context_json']}"
                    ),
                },
            ],
        )
        result = self._complete_json(
            agent_name="planner",
            model=self.planner_model,
            response_model=PlannerOutput,
            messages=prompt_resolution.messages,
            temperature=0.7,
            max_tokens=2600,
            on_stream=on_stream,
        )
        self._attach_prompt_resolution(result, prompt_resolution)
        chapter_titles = [item["title"] for item in result.payload.get("chapters", [])[:3]]
        return self._attach_trace_hints(
            result,
            input_summary=f"Plan {chapter_count} chapters for project {project.title}.",
            prompt_preview=f"Generate story bible updates and {chapter_count} distinct chapter plans for {project.title}.",
            output_summary=f"Planned chapters: {', '.join(chapter_titles)}" if chapter_titles else "No chapters planned.",
        )

    def write_chapter_draft(
        self,
        project: Project,
        chapter: Chapter,
        previous_chapters: list[Chapter],
        *,
        extra_guidance: str = "",
        on_stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> StructuredAgentResponse:
        quality_constraints = self._draft_quality_constraints(project, chapter, previous_chapters)
        context = {
            "project": self._project_context(project),
            "current_chapter": self._chapter_context(chapter, include_blocks=False, include_scenes=False),
            "previous_chapters": [
                self._chapter_context(item, include_blocks=False, include_scenes=False) for item in previous_chapters
            ],
            "recent_causal_chain": self._recent_causal_chain(previous_chapters),
            "characters": [self._character_context(character) for character in project.characters],
            "style_memory": self._style_memory(chapter, previous_chapters),
            "quality_constraints": quality_constraints,
            "extra_guidance": extra_guidance,
        }
        prompt_variables = {
            "project_title": project.title,
            "chapter_title": chapter.title,
            "chapter_order": chapter.order_index,
            "extra_guidance": extra_guidance,
            "context_json": json.dumps(context, ensure_ascii=False, indent=2),
            "quality_constraints_json": json.dumps(quality_constraints, ensure_ascii=False, indent=2),
        }
        prompt_resolution = self._resolve_prompt_messages(
            prompt_name="writer_draft",
            variables=prompt_variables,
            fallback_messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 StoryCraft Studio 的 Writer Agent。"
                        "请写出章节正文，风格偏短剧/网文式混合叙事。"
                        "正文必须以人物推动情节，保留镜头感，但不要写成死板的影视剧本格式。"
                        "每段必须承担明确的戏剧功能，不能只是同一种抒情或氛围铺陈。"
                        "你必须优先复用 style_memory 中已经被作者确认的叙事距离、句法节奏和人物压强。"
                        "如果项目整体以中文叙事为主，不要无故把主要角色称呼写成英文或拼音。"
                        "返回 JSON 时先写 public_notes，用 3-5 条短句告诉作者你准备怎样推进人物、冲突和章节钩子。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请根据以下上下文写出本章 narrative_blocks。"
                        "每一段都要可直接展示给用户，避免摘要式空话；"
                        "要延续项目 tone、人物口吻和前序因果。\n"
                        "你必须遵守以下写作约束：\n"
                        "- 每段必须承担明确的戏剧功能，例如开场画面、信息揭示、关系摩擦、动作决断、钩子收束。\n"
                        "- 至少一段通过具体动作推进，而不是只总结人物感受。\n"
                        "- 至少一段通过对白、潜台词或即时反应暴露人物关系变化。\n"
                        "- 避免以下套话：心头一紧、往事如潮水、未来的阴影、空气仿佛凝固、走向未知的深渊、某种说不清的感觉。\n"
                        "- 优先复用 style_memory 中的作者确认样本，不要把文风写成统一模板腔。\n"
                        f"{prompt_variables['context_json']}"
                    ),
                },
            ],
        )
        result = self._complete_json(
            agent_name="writer",
            model=self.writer_model,
            response_model=WriterDraftOutput,
            messages=prompt_resolution.messages,
            temperature=0.82,
            max_tokens=2600,
            on_stream=on_stream,
        )
        self._attach_prompt_resolution(result, prompt_resolution)
        return self._attach_trace_hints(
            result,
            input_summary=f"Write draft blocks for chapter {chapter.order_index}: {chapter.title}.",
            prompt_preview=f"Write narrative blocks for chapter {chapter.title} that continue the established tone and causal chain.",
            output_summary=(result.payload.get("narrative_blocks") or [""])[0],
        )

    def review_chapter_draft(
        self,
        project: Project,
        chapter: Chapter,
        draft_payload: dict[str, Any],
        *,
        on_stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> StructuredAgentResponse:
        quality_flags = self._detect_narrative_quality_flags(draft_payload.get("narrative_blocks", []))
        context = {
            "project": self._project_context(project),
            "chapter": self._chapter_context(chapter, include_blocks=False, include_scenes=False),
            "characters": [self._character_context(character) for character in project.characters],
            "draft_payload": draft_payload,
            "quality_flags": quality_flags,
        }
        prompt_variables = {
            "project_title": project.title,
            "chapter_title": chapter.title,
            "chapter_order": chapter.order_index,
            "context_json": json.dumps(context, ensure_ascii=False, indent=2),
            "quality_flags_json": json.dumps(quality_flags, ensure_ascii=False, indent=2),
        }
        prompt_resolution = self._resolve_prompt_messages(
            prompt_name="reviewer_draft",
            variables=prompt_variables,
            fallback_messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 StoryCraft Studio 的 Reviewer Agent。"
                        "请检查人物口吻、称呼、动机、时间线、节奏与章节目标是否统一。"
                        "你需要先识别问题，再给出一版可以直接回填的修订稿。"
                        "优先做最小必要改动。保留 Writer 原有的句法节奏、措辞锋利度和段落功能。"
                        "不要为了看起来更顺而整段改写；如果正文已经成立，应尽量保留原文，只做局部修补。"
                        "绝大多数 minor / moderate 问题都应该直接在 revised_narrative_blocks 中修好，并把 decision 设为 accept。"
                        "只有在 revised_narrative_blocks 无法安全修复结构性问题时，才允许使用 rewrite_writer 或 fallback_planner。"
                        "如果只需要提醒作者但不需要实质性改写，请把 apply_mode 设为 preserve_writer。"
                        "但当 quality_flags 非空时不要使用 preserve_writer，必须优先消除这些套话、抽象总结或命名漂移。"
                        "返回 JSON 时先写 public_notes，用 2-4 条短句告诉作者你主要在检查什么。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请审校以下章节初稿，并返回 issues、continuity_notes、revised_narrative_blocks。"
                        "如果初稿整体可用，请优先保留 Writer 原稿，只做最小必要改动。"
                        "如果无需实质性改写，apply_mode 应为 preserve_writer，并在 continuity_notes 中说明保留原因。"
                        "如果 quality_flags 非空时不要使用 preserve_writer，而要在 revised_narrative_blocks 中实际修掉它们。"
                        "请补充 severity，取值只能是 minor/moderate/major/critical。\n"
                        f"{prompt_variables['context_json']}"
                    ),
                },
            ],
        )
        result = self._complete_json(
            agent_name="reviewer",
            model=self.reviewer_model,
            response_model=ReviewerDraftOutput,
            messages=prompt_resolution.messages,
            temperature=0.2,
            max_tokens=2400,
            on_stream=on_stream,
        )
        self._attach_prompt_resolution(result, prompt_resolution)
        decision = result.payload.get("decision", "accept")
        return self._attach_trace_hints(
            result,
            input_summary=f"Review draft for chapter {chapter.order_index}: {chapter.title}.",
            prompt_preview=f"Review the chapter draft for consistency, pacing, and motivation, then decide whether to accept, rewrite, or fall back to planning.",
            output_summary=f"Decision={decision}; issues={len(result.payload.get('issues', []))}",
        )

    def write_chapter_scenes(
        self,
        project: Project,
        chapter: Chapter,
        previous_chapters: list[Chapter],
        *,
        extra_guidance: str = "",
        on_stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> StructuredAgentResponse:
        context = {
            "project": self._project_context(project),
            "current_chapter": self._chapter_context(chapter, include_blocks=True, include_scenes=False),
            "previous_chapters": [
                self._chapter_context(item, include_blocks=False, include_scenes=False) for item in previous_chapters
            ],
            "characters": [self._character_context(character) for character in project.characters],
            "extra_guidance": extra_guidance,
        }
        prompt_variables = {
            "project_title": project.title,
            "chapter_title": chapter.title,
            "chapter_order": chapter.order_index,
            "extra_guidance": extra_guidance,
            "context_json": json.dumps(context, ensure_ascii=False, indent=2),
        }
        prompt_resolution = self._resolve_prompt_messages(
            prompt_name="writer_scenes",
            variables=prompt_variables,
            fallback_messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 StoryCraft Studio 的 Writer Agent。"
                        "请把章节内容拆成具有表演感和画面感的 scenes，数量灵活，不允许固定套路。"
                        "scene_type 优先使用 INT 或 EXT；dialogues 要贴合人物口吻。"
                        "返回 JSON 时先写 public_notes，用 3-5 条短句告诉作者你准备怎样拆场和安排对白张力。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请根据以下上下文，生成 scenes。"
                        "每个 scene 都必须有明确地点、时间、目标、情绪和对白。"
                        "场景数量至少 1 个，但由剧情需要决定，不得机械固定。\n"
                        f"{prompt_variables['context_json']}"
                    ),
                },
            ],
        )
        result = self._complete_json(
            agent_name="writer",
            model=self.writer_model,
            response_model=WriterScenesOutput,
            messages=prompt_resolution.messages,
            temperature=0.78,
            max_tokens=2800,
            on_stream=on_stream,
        )
        self._attach_prompt_resolution(result, prompt_resolution)
        return self._attach_trace_hints(
            result,
            input_summary=f"Structure scenes for chapter {chapter.order_index}: {chapter.title}.",
            prompt_preview=f"Split chapter {chapter.title} into a flexible set of scenes with objectives, tone, and dialogue.",
            output_summary=f"Generated {len(result.payload.get('scenes', []))} scenes.",
        )

    def review_chapter_scenes(
        self,
        project: Project,
        chapter: Chapter,
        scenes_payload: dict[str, Any],
        *,
        on_stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> StructuredAgentResponse:
        context = {
            "project": self._project_context(project),
            "chapter": self._chapter_context(chapter, include_blocks=True, include_scenes=False),
            "characters": [self._character_context(character) for character in project.characters],
            "scenes_payload": scenes_payload,
        }
        prompt_variables = {
            "project_title": project.title,
            "chapter_title": chapter.title,
            "chapter_order": chapter.order_index,
            "context_json": json.dumps(context, ensure_ascii=False, indent=2),
        }
        prompt_resolution = self._resolve_prompt_messages(
            prompt_name="reviewer_scenes",
            variables=prompt_variables,
            fallback_messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 StoryCraft Studio 的 Reviewer Agent。"
                        "请审校 scenes 的因果关系、角色口吻、场景衔接与对白有效性。"
                        "你需要输出一版可直接落库的 revised_scenes。"
                        "绝大多数 minor / moderate 问题都应该直接在 revised_scenes 中修好，并把 decision 设为 accept。"
                        "只有在 revised_scenes 无法安全修复结构性问题时，才允许使用 rewrite_writer 或 fallback_planner。"
                        "返回 JSON 时先写 public_notes，用 2-4 条短句告诉作者你主要在检查什么。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请审校以下 scenes，并返回 issues、continuity_notes、revised_scenes。"
                        "如果结构已经成立，也要进行轻度修订，让场景推进更清晰。"
                        "请补充 severity，取值只能是 minor/moderate/major/critical。\n"
                        f"{prompt_variables['context_json']}"
                    ),
                },
            ],
        )
        result = self._complete_json(
            agent_name="reviewer",
            model=self.reviewer_model,
            response_model=ReviewerScenesOutput,
            messages=prompt_resolution.messages,
            temperature=0.2,
            max_tokens=2800,
            on_stream=on_stream,
        )
        self._attach_prompt_resolution(result, prompt_resolution)
        decision = result.payload.get("decision", "accept")
        return self._attach_trace_hints(
            result,
            input_summary=f"Review scenes for chapter {chapter.order_index}: {chapter.title}.",
            prompt_preview=f"Review the structured scenes for chapter {chapter.title} and decide whether to accept, rewrite, or fall back to planning.",
            output_summary=f"Decision={decision}; issues={len(result.payload.get('issues', []))}",
        )

    def build_visual_prompt(
        self,
        project: Project,
        scene: Scene,
        characters: list[Character],
        *,
        extra_guidance: str = "",
        on_stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> StructuredAgentResponse:
        context = {
            "project": self._project_context(project),
            "scene": self._scene_context(scene),
            "characters": [self._character_context(character) for character in characters],
            "extra_guidance": extra_guidance,
        }
        prompt_variables = {
            "project_title": project.title,
            "scene_title": scene.title,
            "extra_guidance": extra_guidance,
            "context_json": json.dumps(context, ensure_ascii=False, indent=2),
        }
        prompt_resolution = self._resolve_prompt_messages(
            prompt_name="visual_prompt",
            variables=prompt_variables,
            fallback_messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 StoryCraft Studio 的 Visual Prompt Agent。"
                        "请根据场景与人物视觉锚点，输出一条适用于剧照生成的 prompt_text。"
                        "画面要求克制、电影感、角色一致性强，不要写成模板化提示词堆砌。"
                        "返回 JSON 时先写 public_notes，用 2-4 条短句告诉作者你正在锁定哪些镜头和人物一致性细节。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请为以下 scene 生成视觉 prompt。"
                        "要体现地点、时段、气氛、人物锚点和镜头语言。"
                        "如果 scene 中已经有 canonical_scene_illustration，必须把它当成上一轮已批准的参考镜头，"
                        "延续角色脸部识别度、服装逻辑、灯光方向与整体气压。"
                        "如果 extra_guidance 非空，也要把它吸收进最终 prompt，而不是忽略。\n"
                        f"{prompt_variables['context_json']}"
                    ),
                },
            ],
        )
        result = self._complete_json(
            agent_name="visual_prompt",
            model=self.visual_model,
            response_model=VisualPromptOutput,
            messages=prompt_resolution.messages,
            temperature=0.45,
            max_tokens=1200,
            on_stream=on_stream,
        )
        self._attach_prompt_resolution(result, prompt_resolution)
        return self._attach_trace_hints(
            result,
            input_summary=f"Build a visual prompt for scene {scene.title}.",
            prompt_preview=f"Generate a cinematic illustration prompt for scene {scene.title} with cast and visual anchors.",
            output_summary=result.payload.get("prompt_text", ""),
        )

    def generate_scene_illustrations(
        self,
        project: Project,
        scene: Scene,
        characters: list[Character],
        *,
        prompt_text: str,
        candidate_count: int,
        extra_guidance: str = "",
        on_stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> StructuredAgentResponse:
        reference_feedback = self._scene_reference_feedback(scene, extra_guidance=extra_guidance)
        if on_stream is not None:
            on_stream(
                {
                    "text": self._trim_preview(f"正在根据场景 {scene.title} 的 prompt 渲染 {candidate_count} 张剧照候选。"),
                    "final": False,
                }
            )

        generated = self._require_image_client().generate_images(
            model=self.image_model,
            prompt=prompt_text,
            candidate_count=candidate_count,
            size=self.image_size,
            on_progress=on_stream,
        )

        if on_stream is not None:
            on_stream(
                {
                    "text": self._trim_preview(f"已拿到 {len(generated['images'])} 张剧照候选，正在准备落库。"),
                    "final": True,
                }
            )

        return StructuredAgentResponse(
            payload={
                "generated_images": generated["images"],
                "public_notes": [
                    "正在把最终 prompt 送入图像模型。",
                    "优先保持角色外貌锚点、时段光线和场景气压一致。",
                    "已参考当前场景主图来约束下一轮一致性。" if reference_feedback["used_scene_canonical"] else "当前场景还没有主图，正在以角色档案为主要参照。",
                ],
                "reference_feedback": reference_feedback,
            },
            raw_text="",
            trace=generated["trace"],
            input_summary=f"Render {candidate_count} illustration candidates for scene {scene.title}.",
            prompt_preview=self._trim_preview(prompt_text),
            output_summary=f"Rendered {len(generated['images'])} illustration candidates.",
        )

    def _complete_json(
        self,
        *,
        agent_name: str,
        model: str,
        response_model: type[BaseModel],
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        on_stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> StructuredAgentResponse:
        client = self._require_client()
        return client.complete_json(
            agent_name=agent_name,
            model=model,
            response_model=response_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            on_stream=on_stream,
        )

    def _require_client(self) -> OpenAICompatibleTextClient:
        if not self.client:
            raise LLMConfigurationError(
                "Text model provider is not configured. Set OPENAI_BASE_URL and OPENAI_API_KEY."
            )
        return self.client

    def _require_image_client(self) -> OpenAICompatibleImageClient:
        if not self.image_client:
            raise LLMConfigurationError(
                "Image model provider is not configured. Set OPENAI_BASE_URL and OPENAI_API_KEY."
            )
        return self.image_client

    @staticmethod
    def _project_context(project: Project) -> dict[str, Any]:
        return {
            "title": project.title,
            "genre": project.genre,
            "tone": project.tone,
            "era": project.era,
            "target_chapter_count": project.target_chapter_count,
            "target_length": project.target_length,
            "logline": project.logline,
            "story_bible": {
                "world_notes": project.story_bible.world_notes if project.story_bible else "",
                "style_notes": project.story_bible.style_notes if project.story_bible else "",
                "writing_rules": project.story_bible.writing_rules if project.story_bible else [],
                "addressing_rules": project.story_bible.addressing_rules if project.story_bible else "",
                "timeline_rules": project.story_bible.timeline_rules if project.story_bible else "",
            },
        }

    @staticmethod
    def _character_context(character: Character) -> dict[str, Any]:
        return {
            "name": character.name,
            "role": character.role,
            "personality": character.personality,
            "goal": character.goal,
            "speech_style": character.speech_style,
            "appearance": character.appearance,
            "relationships": character.relationships,
            "signature_line": character.signature_line,
            "reference_images": [
                {
                    "filename": item.filename,
                    "path": item.path,
                }
                for item in character.reference_images
            ],
            "visual_profile": {
                "visual_anchor": character.visual_profile.visual_anchor if character.visual_profile else "",
                "signature_palette": character.visual_profile.signature_palette if character.visual_profile else "",
                "silhouette_notes": character.visual_profile.silhouette_notes if character.visual_profile else "",
                "wardrobe_notes": character.visual_profile.wardrobe_notes if character.visual_profile else "",
                "atmosphere_notes": character.visual_profile.atmosphere_notes if character.visual_profile else "",
            },
        }

    @staticmethod
    def _chapter_context(
        chapter: Chapter,
        *,
        include_blocks: bool,
        include_scenes: bool,
    ) -> dict[str, Any]:
        payload = {
            "order_index": chapter.order_index,
            "title": chapter.title,
            "summary": chapter.summary,
            "chapter_goal": chapter.chapter_goal,
            "hook": chapter.hook,
            "status": chapter.status,
            "is_locked": chapter.is_locked,
            "continuity_notes": chapter.continuity_notes,
        }
        if include_blocks:
            payload["narrative_blocks"] = [block.content for block in sorted(chapter.narrative_blocks, key=lambda item: item.order_index)]
        if include_scenes:
            payload["scenes"] = [StoryAgentPipeline._scene_context(scene) for scene in sorted(chapter.scenes, key=lambda item: item.order_index)]
        return payload

    @staticmethod
    def _recent_causal_chain(previous_chapters: list[Chapter]) -> list[dict[str, Any]]:
        if not previous_chapters:
            return []
        recent_items = []
        for item in previous_chapters[-3:]:
            recent_items.append(
                {
                    "order_index": item.order_index,
                    "title": item.title,
                    "summary": item.summary,
                    "hook": item.hook,
                    "continuity_notes": list(item.continuity_notes or [])[:2],
                }
            )
        return recent_items

    @staticmethod
    def _style_memory(chapter: Chapter, previous_chapters: list[Chapter]) -> dict[str, Any]:
        protected_examples: list[dict[str, Any]] = []
        recent_examples: list[dict[str, Any]] = []
        candidate_chapters = [chapter, *reversed(previous_chapters)]
        for item in candidate_chapters:
            for block in sorted(item.narrative_blocks, key=lambda narrative_block: narrative_block.order_index):
                excerpt = " ".join(str(block.content or "").split())
                if not excerpt:
                    continue
                sample = {
                    "chapter_order": item.order_index,
                    "block_order": block.order_index,
                    "excerpt": excerpt,
                    "is_locked": bool(block.is_locked),
                    "is_user_edited": bool(block.is_user_edited),
                }
                if block.is_locked or block.is_user_edited:
                    protected_examples.append(sample)
                else:
                    recent_examples.append(sample)
        return {
            "author_confirmed_examples": protected_examples[:4],
            "recent_reference_examples": recent_examples[:3],
        }

    @staticmethod
    def _draft_quality_constraints(
        project: Project,
        chapter: Chapter,
        previous_chapters: list[Chapter],
    ) -> dict[str, Any]:
        source_text = " ".join(
            filter(
                None,
                [
                    project.title,
                    project.genre,
                    project.tone,
                    project.logline,
                    chapter.title,
                    chapter.summary,
                    chapter.chapter_goal,
                    chapter.hook,
                    *(character.name for character in project.characters),
                ],
            )
        )
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", source_text))
        latin_count = len(re.findall(r"[A-Za-z]", source_text))
        language_guidance = (
            "当前项目以中文叙事为主，除非用户明确要求外文，不要无故把主要角色称呼写成英文或拼音。"
            if cjk_count >= latin_count
            else "保持人物称呼与用户输入一致，不要无故切换命名体系。"
        )
        return {
            "chapter_function_focus": [
                f"开场先把{chapter.summary}落成可见画面，而不是抽象解释。",
                f"中段必须围绕“{chapter.chapter_goal}”制造关系摩擦或行动代价。",
                f"结尾钩子必须服务“{chapter.hook}”，并让角色处在被迫回应的位置。",
            ],
            "required_moves": [
                "至少一段通过具体动作推进。",
                "至少一段通过对白、潜台词或即时反应暴露人物关系。",
                "至少一段明确交付新信息、误导纠正或决策代价。",
                "段长和句长要有变化，避免每段都用同一种节奏。",
            ],
            "anti_cliche_rules": [
                "避免以下套话：心头一紧、往事如潮水、未来的阴影、空气仿佛凝固、走向未知的深渊、某种说不清的感觉。",
                "不要反复使用'他知道这一切将改变一切'之类自我解释句。",
                "不要把人物情绪直接总结成抽象名词，优先写动作、停顿、视线和反应。",
            ],
            "language_guidance": language_guidance,
            "previous_chapter_count": len(previous_chapters),
        }

    @staticmethod
    def _detect_narrative_quality_flags(blocks: list[str]) -> list[dict[str, Any]]:
        flagged_phrases = [
            "心中一紧",
            "往事如潮水",
            "未来的阴影",
            "空气仿佛凝固",
            "走向未知的深渊",
            "某种说不清的感觉",
            "无形的力量",
        ]
        flags: list[dict[str, Any]] = []
        for index, block in enumerate(blocks, start=1):
            text = str(block or "")
            matches = [phrase for phrase in flagged_phrases if phrase in text]
            if not matches:
                continue
            flags.append(
                {
                    "block_index": index,
                    "type": "cliche_phrase",
                    "matches": matches,
                    "excerpt": text[:180],
                }
            )
        return flags

    @staticmethod
    def _scene_context(scene: Scene) -> dict[str, Any]:
        canonical = StoryAgentPipeline._canonical_scene_illustration_context(scene)
        return {
            "title": scene.title,
            "scene_type": scene.scene_type,
            "location": scene.location,
            "time_of_day": scene.time_of_day,
            "cast_names": scene.cast_names,
            "objective": scene.objective,
            "emotional_tone": scene.emotional_tone,
            "visual_prompt": scene.visual_prompt,
            "existing_candidate_count": len(scene.illustrations),
            "canonical_scene_illustration": canonical,
            "existing_illustrations": [
                {
                    "id": item.id,
                    "candidate_index": item.candidate_index,
                    "is_canonical": item.is_canonical,
                    "prompt_text": item.prompt_text,
                }
                for item in sorted(scene.illustrations, key=lambda illustration: (illustration.candidate_index, illustration.id or 0))
            ],
            "dialogues": [
                {
                    "speaker": block.speaker,
                    "parenthetical": block.parenthetical,
                    "content": block.content,
                }
                for block in sorted(scene.dialogue_blocks, key=lambda item: item.order_index)
            ],
        }

    @staticmethod
    def _canonical_scene_illustration_context(scene: Scene) -> dict[str, Any] | None:
        canonical = next((item for item in scene.illustrations if item.is_canonical), None)
        if not canonical:
            return None
        return {
            "id": canonical.id,
            "candidate_index": canonical.candidate_index,
            "prompt_text": canonical.prompt_text,
            "file_path": canonical.file_path,
        }

    @classmethod
    def _scene_reference_feedback(cls, scene: Scene, *, extra_guidance: str = "") -> dict[str, Any]:
        canonical = cls._canonical_scene_illustration_context(scene)
        return {
            "used_scene_canonical": canonical is not None,
            "canonical_illustration_id": canonical.get("id") if canonical else None,
            "canonical_candidate_index": canonical.get("candidate_index") if canonical else None,
            "extra_guidance": extra_guidance,
        }


class MockCreativeStudio:
    def __init__(self, project: Project):
        self.project = project
        self.random = random.Random(project.title)

    def build_character_profile(self, character: Character) -> dict:
        palette = self.random.choice(
            [
                "酒红、煤黑、旧银",
                "深青、雾灰、月白",
                "靛蓝、炭黑、暖金",
                "墨绿、钛灰、乳白",
            ]
        )
        signature_line = f"{character.name}说话总像在替自己留后路，但每一句都直指真心。"
        return {
            "signature_line": signature_line,
            "visual_anchor": f"{character.name}的标志性气质是{character.appearance}，整体视觉始终围绕“{character.role}”的职业锋利感展开。",
            "signature_palette": palette,
            "silhouette_notes": f"轮廓应突出 {character.appearance.split('，')[0]} 与 {character.role} 的职业辨识度。",
            "wardrobe_notes": f"服装重点延续 {character.appearance} 的关键词，并加入与目标“{character.goal}”呼应的细节。",
            "atmosphere_notes": f"镜头中的 {character.name} 应呈现 {character.personality} 的张力，台词节奏遵循 {character.speech_style}。",
        }

    def plan_chapters(self, characters: list[Character], chapter_count: int) -> list[dict]:
        core_names = "、".join(character.name for character in characters[:3]) or "主角团"
        templates = [
            ("雾里开场", "城市异常第一次袭来", "让角色卷入故事", "结尾抛出第一个谜团"),
            ("旧线索复活", "被掩埋的旧事浮出水面", "推进角色关系", "结尾带出新的对手"),
            ("关系失衡", "信任链开始崩塌", "逼角色做选择", "结尾留下代价"),
            ("逼近真相", "线索指向核心秘密", "加深世界观", "结尾翻转认知"),
            ("主动出击", "主角决定反向布局", "让人物成长", "结尾进入高潮前夜"),
            ("夜里摊牌", "情感与真相双重爆发", "把冲突推到顶点", "结尾留下伤痕"),
        ]

        results = []
        for index in range(chapter_count):
            title, summary_seed, goal, hook_seed = templates[index % len(templates)]
            results.append(
                {
                    "order_index": index + 1,
                    "title": f"第{index + 1}章·{title}",
                    "summary": f"{core_names}在《{self.project.title}》中迎来“{summary_seed}”的阶段，围绕 {self.project.logline} 的核心矛盾继续推进。",
                    "chapter_goal": goal,
                    "hook": f"{hook_seed}，并把 {core_names.split('、')[0]} 推向新的悬念中心。",
                }
            )
        return results

    def write_chapter_blocks(self, chapter: Chapter, characters: list[Character]) -> tuple[list[str], list[str]]:
        leads = characters[:2] if characters else []
        lead_names = "与".join(character.name for character in leads) or "主角"
        blocks = [
            f"{chapter.summary}。夜色压住了街区边缘的霓虹，{lead_names}在失真的广播、潮湿的街角和不断逼近的旧秘密之间试探彼此。",
            f"这一章的核心动作是“{chapter.chapter_goal}”。人物推进时始终保持 {self.project.tone} 的质地，让情绪比动作先一步落地。",
            f"章节尾声必须落在“{chapter.hook}”上，让下一章的期待感自然形成，而不是硬性的悬念提示。",
        ]
        continuity = [
            f"检查主要角色是否保持“{character.speech_style}”的口吻。" for character in leads
        ]
        return blocks, continuity or ["当前章节暂无额外连续性提醒。"]

    def structure_scenes(self, chapter: Chapter, characters: list[Character]) -> list[dict]:
        cast = [character.name for character in characters[:3]]
        scene_specs = [
            {
                "title": "旧城区广播站",
                "scene_type": "INT",
                "location": "广播站维修室",
                "time_of_day": "NIGHT",
                "objective": "让主角发现异常线索并确认彼此合作的必要性",
                "emotional_tone": "压抑而克制",
                "dialogues": [
                    {"speaker": cast[0] if cast else "主角", "parenthetical": "压低声音", "content": "这不是故障，有人在借频率说话。"},
                    {"speaker": cast[1] if len(cast) > 1 else "搭档", "parenthetical": "看向门外", "content": "如果你没听错，那我们已经来晚了。"},
                ],
            },
            {
                "title": "雨夜天桥",
                "scene_type": "EXT",
                "location": "旧城高架天桥",
                "time_of_day": "NIGHT",
                "objective": "让人物关系出现第一次真实碰撞",
                "emotional_tone": "锋利又暧昧",
                "dialogues": [
                    {"speaker": cast[0] if cast else "主角", "parenthetical": "盯着雨幕", "content": "你到底是在帮我，还是在试探我？"},
                    {"speaker": cast[1] if len(cast) > 1 else "搭档", "parenthetical": "停顿一秒", "content": "这两件事，从来都不是反义词。"},
                ],
            },
        ]
        return [
            {
                "order_index": index + 1,
                "cast_names": cast,
                **scene_spec,
            }
            for index, scene_spec in enumerate(scene_specs)
        ]

    def build_visual_prompt(self, scene: Scene, characters: list[Character]) -> str:
        cast_details = []
        for character in characters:
            cast_details.append(
                f"{character.name}: {character.visual_profile.visual_anchor if character.visual_profile else character.appearance}"
            )
        cast_text = " | ".join(cast_details) if cast_details else "角色保持既有设定"
        return (
            f"{self.project.title} cinematic still, {scene.scene_type} {scene.location} at {scene.time_of_day}, "
            f"tone: {scene.emotional_tone}, objective: {scene.objective}. "
            f"Cast consistency anchors: {cast_text}. "
            f"Visual language: restrained editorial drama, subtle film grain, practical lighting, rich atmosphere."
        )
