from __future__ import annotations

import json
import sys

from .config import load_settings
from .providers import LLMProviderError, StoryAgentPipeline


def main() -> int:
    settings = load_settings()
    pipeline = StoryAgentPipeline.from_settings(settings)

    try:
        models = pipeline.list_models()
        smoke_result = pipeline.smoke_completion()
    except LLMProviderError as exc:
        print(f"provider smoke failed: {exc}", file=sys.stderr)
        return 1

    print("provider smoke ok")
    print(f"model count: {len(models)}")
    preview = [model["id"] for model in models[:10]]
    print(f"models: {json.dumps(preview, ensure_ascii=False)}")
    print(f"smoke trace: {json.dumps(smoke_result.trace, ensure_ascii=False)}")
    print(f"smoke payload: {json.dumps(smoke_result.payload, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
