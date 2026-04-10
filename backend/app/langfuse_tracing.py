from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

from .models import GenerationJob

try:  # pragma: no cover - exercised only when the optional dependency is installed
    from langfuse import Langfuse, propagate_attributes
except ImportError:  # pragma: no cover - fallback path is covered in tests via injection
    try:  # pragma: no cover
        from langfuse.otel import Langfuse  # type: ignore[attr-defined]
        from langfuse import propagate_attributes  # type: ignore[attr-defined]
    except ImportError:  # pragma: no cover
        Langfuse = None  # type: ignore[assignment]
        propagate_attributes = None  # type: ignore[assignment]


def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "", [], {}, ())}


def _stringify_dict_values(payload: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in payload.items() if value not in (None, "", [], {}, ())}


@dataclass(slots=True)
class LangfuseObservationPayload:
    trace_id: str | None = None
    observation_id: str | None = None
    trace_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact_dict(
            {
                "trace_id": self.trace_id,
                "observation_id": self.observation_id,
                "trace_url": self.trace_url,
            }
        )


class NoopLangfuseObservation:
    def update(self, **_: Any) -> None:
        return

    def complete(self, **_: Any) -> None:
        return

    def fail(self, **_: Any) -> None:
        return

    def payload(self) -> dict[str, Any]:
        return {}


class NoopLangfuseWorkflowTrace:
    def start_agent_observation(self, **_: Any) -> NoopLangfuseObservation:
        return NoopLangfuseObservation()

    def complete(self, **_: Any) -> None:
        return

    def fail(self, **_: Any) -> None:
        return

    def payload(self) -> dict[str, Any]:
        return {}

    def close(self) -> None:
        return


class LangfuseObservationHandle:
    def __init__(
        self,
        *,
        observation: Any,
        payload: LangfuseObservationPayload,
    ):
        self._observation = observation
        self._payload = payload

    def update(self, **kwargs: Any) -> None:
        payload = _compact_dict(kwargs)
        if not payload:
            return
        update_fn = getattr(self._observation, "update", None)
        if callable(update_fn):
            update_fn(**payload)

    def complete(self, **kwargs: Any) -> None:
        payload = _compact_dict(kwargs)
        update_fn = getattr(self._observation, "update", None)
        end_fn = getattr(self._observation, "end", None)
        if callable(update_fn) and payload:
            update_fn(**payload)
        if callable(end_fn):
            end_fn()

    def fail(self, **kwargs: Any) -> None:
        payload = _compact_dict(kwargs)
        update_fn = getattr(self._observation, "update", None)
        end_fn = getattr(self._observation, "end", None)
        if callable(update_fn):
            update_payload = dict(payload)
            metadata = dict(update_payload.get("metadata") or {})
            metadata["status"] = "error"
            update_payload["metadata"] = metadata
            update_fn(**_compact_dict(update_payload))
        if callable(end_fn):
            end_fn()

    def payload(self) -> dict[str, Any]:
        return self._payload.to_dict()


class LangfuseWorkflowTraceHandle:
    def __init__(
        self,
        *,
        client: Any,
        root_context: Any,
        attributes_context: Any,
        root_observation: Any,
        payload: LangfuseObservationPayload,
    ):
        self._client = client
        self._root_context = root_context
        self._attributes_context = attributes_context
        self._root_observation = root_observation
        self._payload = payload

    def start_agent_observation(
        self,
        *,
        step_key: str,
        agent_name: str,
        model_id: str | None,
        input_summary: str,
        prompt_preview: str,
        metadata: dict[str, Any] | None = None,
    ) -> LangfuseObservationHandle:
        start_fn = getattr(self._client, "start_observation", None)
        if not callable(start_fn) or not self._payload.trace_id:
            return LangfuseObservationHandle(observation=None, payload=LangfuseObservationPayload())

        request_payload = _compact_dict(
            {
                "trace_context": _compact_dict(
                    {
                        "trace_id": self._payload.trace_id,
                        "parent_span_id": self._payload.observation_id,
                    }
                ),
                "name": f"storycraft.{step_key}",
                "as_type": "generation" if model_id else "span",
                "input": _compact_dict(
                    {
                        "input_summary": input_summary,
                        "prompt_preview": prompt_preview,
                    }
                ),
                "metadata": _compact_dict(
                    {
                        "step_key": step_key,
                        "agent_name": agent_name,
                        **(metadata or {}),
                    }
                ),
                "model": model_id,
            }
        )
        observation = start_fn(**request_payload)
        payload = LangfuseObservationPayload(
            trace_id=self._payload.trace_id,
            observation_id=getattr(observation, "id", None) or getattr(observation, "observation_id", None),
            trace_url=self._payload.trace_url,
        )
        return LangfuseObservationHandle(observation=observation, payload=payload)

    def complete(self, **kwargs: Any) -> None:
        payload = _compact_dict(kwargs)
        update_fn = getattr(self._root_observation, "update", None)
        end_fn = getattr(self._root_observation, "end", None)
        if callable(update_fn) and payload:
            update_fn(**payload)
        if callable(end_fn):
            end_fn()
        flush_fn = getattr(self._client, "flush", None)
        if callable(flush_fn):
            flush_fn()

    def fail(self, **kwargs: Any) -> None:
        payload = _compact_dict(kwargs)
        update_fn = getattr(self._root_observation, "update", None)
        end_fn = getattr(self._root_observation, "end", None)
        if callable(update_fn):
            update_payload = dict(payload)
            metadata = dict(update_payload.get("metadata") or {})
            metadata["status"] = "error"
            update_payload["metadata"] = metadata
            update_fn(**_compact_dict(update_payload))
        if callable(end_fn):
            end_fn()
        flush_fn = getattr(self._client, "flush", None)
        if callable(flush_fn):
            flush_fn()

    def payload(self) -> dict[str, Any]:
        return self._payload.to_dict()

    def close(self) -> None:
        exit_fn = getattr(self._root_context, "__exit__", None)
        if callable(exit_fn):
            exit_fn(None, None, None)
        attr_exit_fn = getattr(self._attributes_context, "__exit__", None)
        if callable(attr_exit_fn):
            attr_exit_fn(None, None, None)


class LangfuseTracingClient:
    def __init__(
        self,
        *,
        base_url: str | None,
        public_key: str | None,
        secret_key: str | None,
        environment: str | None = None,
        release: str | None = None,
        client: Any | None = None,
    ):
        self.base_url = base_url or ""
        self.public_key = public_key or ""
        self.secret_key = secret_key or ""
        self.environment = environment
        self.release = release
        self._client = client

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.public_key and self.secret_key)

    @classmethod
    def from_settings(cls, settings) -> "LangfuseTracingClient | NoopLangfuseTracingClient":
        if not settings.langfuse_base_url or not settings.langfuse_public_key or not settings.langfuse_secret_key:
            return NoopLangfuseTracingClient()
        return cls(
            base_url=settings.langfuse_base_url,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            environment=getattr(settings, "langfuse_environment", None),
            release=getattr(settings, "langfuse_release", None),
        )

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        if Langfuse is None:
            return None
        self._client = Langfuse(
            public_key=self.public_key,
            secret_key=self.secret_key,
            host=self.base_url,
            environment=self.environment,
            release=self.release,
        )
        return self._client

    def start_workflow_trace(self, *, job: GenerationJob) -> LangfuseWorkflowTraceHandle | NoopLangfuseWorkflowTrace:
        client = self._get_client()
        if client is None:
            return NoopLangfuseWorkflowTrace()

        trace_metadata = _compact_dict(
            {
                "job_id": job.id,
                "job_type": job.job_type,
                "project_id": job.project_id,
                "chapter_id": job.chapter_id,
                "scene_id": job.scene_id,
            }
        )
        attributes_context = nullcontext()
        if callable(propagate_attributes):
            attributes_context = propagate_attributes(
                user_id=str(job.user_id),
                session_id=f"project:{job.project_id}" if job.project_id else f"user:{job.user_id}",
                trace_name=f"StoryCraft {job.job_type}",
                tags=["storycraft-studio", job.job_type],
                metadata=_stringify_dict_values(trace_metadata),
            )
        root_context = client.start_as_current_observation(
            name=f"storycraft.workflow.{job.job_type}",
            as_type="agent",
            input=_compact_dict(
                {
                    "job_type": job.job_type,
                    "input_snapshot": job.input_snapshot,
                }
            ),
            metadata=trace_metadata,
            end_on_exit=False,
        )
        attributes_context.__enter__()
        root_observation = root_context.__enter__()
        trace_id_getter = getattr(client, "get_current_trace_id", None)
        observation_id_getter = getattr(client, "get_current_observation_id", None)
        trace_url_getter = getattr(client, "get_trace_url", None)
        payload = LangfuseObservationPayload(
            trace_id=trace_id_getter() if callable(trace_id_getter) else None,
            observation_id=observation_id_getter() if callable(observation_id_getter) else None,
            trace_url=trace_url_getter() if callable(trace_url_getter) else None,
        )
        return LangfuseWorkflowTraceHandle(
            client=client,
            root_context=root_context,
            attributes_context=attributes_context,
            root_observation=root_observation,
            payload=payload,
        )


class NoopLangfuseTracingClient:
    def start_workflow_trace(self, *, job: GenerationJob) -> NoopLangfuseWorkflowTrace:
        return NoopLangfuseWorkflowTrace()
