from pathlib import Path

from types import SimpleNamespace

from app.export_delivery_smoke import freeze_runtime_environment


def test_freeze_runtime_environment_preserves_active_paths_and_switches_to_inline_queue():
    settings = SimpleNamespace(
        database_url="postgresql+psycopg://postgres:secret@127.0.0.1:5432/storycraft",
        storage_dir=Path("/tmp/storycraft/storage"),
        export_dir=Path("/tmp/storycraft/exports"),
        openai_base_url="https://example.test/v1",
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        story_agent_planner_model="planner-model",
        story_agent_writer_model="writer-model",
        story_agent_reviewer_model="reviewer-model",
        story_agent_visual_model="visual-model",
        story_agent_image_model="flux-schnell",
        story_agent_image_size="1536x1024",
        story_agent_timeout_seconds=45,
        story_review_intervention_min_severity="critical",
    )

    env = freeze_runtime_environment(settings)

    assert env["STORY_PLATFORM_SKIP_DOTENV"] == "1"
    assert env["STORY_PLATFORM_QUEUE_BACKEND"] == "inline"
    assert env["STORY_PLATFORM_DB_URL"] == settings.database_url
    assert env["STORY_PLATFORM_STORAGE_DIR"] == str(settings.storage_dir)
    assert env["STORY_PLATFORM_EXPORT_DIR"] == str(settings.export_dir)
    assert env["OPENAI_MODEL"] == "gpt-4o-mini"
    assert env["STORY_AGENT_IMAGE_MODEL"] == "flux-schnell"
