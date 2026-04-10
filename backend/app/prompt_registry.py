from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx


class PromptRegistryError(RuntimeError):
    pass


@dataclass(slots=True)
class PromptResolution:
    name: str
    messages: list[dict[str, str]]
    source: Literal["langfuse", "fallback"]
    version: int | None = None
    label: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""


@dataclass(slots=True)
class _CachedPromptDefinition:
    payload: dict[str, Any]
    expires_at: float


class LangfusePromptRegistry:
    def __init__(
        self,
        *,
        base_url: str | None,
        public_key: str | None,
        secret_key: str | None,
        prompt_label: str = "production",
        cache_ttl_seconds: int = 300,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.public_key = public_key or ""
        self.secret_key = secret_key or ""
        self.prompt_label = prompt_label.strip() or "production"
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))
        self._client = http_client or httpx.Client(
            base_url=self.base_url or "http://invalid.local",
            timeout=10,
            trust_env=False,
        )
        self._cache: dict[tuple[str, str], _CachedPromptDefinition] = {}

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.public_key and self.secret_key)

    def resolve_messages(
        self,
        name: str,
        *,
        variables: dict[str, Any],
        fallback_messages: list[dict[str, str]],
    ) -> PromptResolution:
        if not self.is_configured:
            return PromptResolution(
                name=name,
                messages=fallback_messages,
                source="fallback",
                label=self.prompt_label,
                error_message="Langfuse prompt registry is not configured.",
            )

        try:
            payload = self._fetch_prompt_definition(name)
            messages = self._compile_prompt_messages(payload, variables)
            return PromptResolution(
                name=name,
                messages=messages,
                source="langfuse",
                version=self._parse_version(payload.get("version")),
                label=self.prompt_label,
                config=payload.get("config") if isinstance(payload.get("config"), dict) else {},
            )
        except Exception as exc:
            return PromptResolution(
                name=name,
                messages=fallback_messages,
                source="fallback",
                label=self.prompt_label,
                error_message=str(exc),
            )

    def _fetch_prompt_definition(self, name: str) -> dict[str, Any]:
        cache_key = (name, self.prompt_label)
        cached = self._cache.get(cache_key)
        now = time.time()
        if cached and cached.expires_at >= now:
            return cached.payload

        response = self._client.get(
            f"/api/public/v2/prompts/{name}",
            headers={"Authorization": f"Basic {self._basic_auth_token()}"},
            params={"label": self.prompt_label},
        )
        payload = self._read_json_response(response)
        if self.cache_ttl_seconds > 0:
            self._cache[cache_key] = _CachedPromptDefinition(
                payload=payload,
                expires_at=now + self.cache_ttl_seconds,
            )
        return payload

    def _compile_prompt_messages(self, payload: dict[str, Any], variables: dict[str, Any]) -> list[dict[str, str]]:
        prompt_payload = payload.get("prompt")
        prompt_type = str(payload.get("type") or "").strip().lower()
        if isinstance(prompt_payload, list):
            messages: list[dict[str, str]] = []
            for item in prompt_payload:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "user").strip() or "user"
                content = self._render_template(str(item.get("content") or ""), variables)
                messages.append({"role": role, "content": content})
            if not messages:
                raise PromptRegistryError("Langfuse chat prompt did not contain any valid messages.")
            return messages

        if isinstance(prompt_payload, str):
            role = "system" if prompt_type == "text" else "user"
            return [{"role": role, "content": self._render_template(prompt_payload, variables)}]

        raise PromptRegistryError("Langfuse prompt payload is missing a supported prompt field.")

    @staticmethod
    def _parse_version(raw_value: Any) -> int | None:
        if raw_value is None:
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _render_template(template: str, variables: dict[str, Any]) -> str:
        pattern = re.compile(r"\{\{\{?\s*([a-zA-Z0-9_.-]+)\s*\}?\}\}")

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            value = LangfusePromptRegistry._resolve_variable(variables, key)
            if value is None:
                raise PromptRegistryError(f"Missing Langfuse prompt variable: {key}")
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False, indent=2)
            return str(value)

        return pattern.sub(replace, template)

    @staticmethod
    def _resolve_variable(variables: dict[str, Any], key: str) -> Any:
        current: Any = variables
        for segment in key.split("."):
            if isinstance(current, dict) and segment in current:
                current = current[segment]
            else:
                return None
        return current

    def _basic_auth_token(self) -> str:
        raw = f"{self.public_key}:{self.secret_key}".encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    @staticmethod
    def _read_json_response(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise PromptRegistryError(f"Langfuse returned non-JSON response: {response.text[:200]}") from exc

        if response.is_error:
            message = payload.get("message") if isinstance(payload, dict) else payload
            raise PromptRegistryError(f"Langfuse prompt fetch failed: {message}")

        if not isinstance(payload, dict):
            raise PromptRegistryError("Langfuse prompt response is not a JSON object.")
        return payload
