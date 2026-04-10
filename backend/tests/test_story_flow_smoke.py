from types import SimpleNamespace

from app.story_flow_smoke import freeze_story_flow_environment


def test_freeze_story_flow_environment_preserves_current_image_model_and_runtime_overrides(tmp_path):
    settings = SimpleNamespace(
        database_url="postgresql+psycopg://postgres:secret@127.0.0.1:5432/storycraft",
        storage_dir=tmp_path / "storage",
        export_dir=tmp_path / "exports",
        openai_base_url="https://nangeai.top/v1",
        openai_api_key="sk-test",
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

    env = freeze_story_flow_environment(settings, str(tmp_path))

    assert env["STORY_PLATFORM_SKIP_DOTENV"] == "1"
    assert env["STORY_PLATFORM_ALLOW_SQLITE"] == "1"
    assert env["STORY_PLATFORM_QUEUE_BACKEND"] == "inline"
    assert env["STORY_PLATFORM_DB_URL"].startswith("sqlite:///")
    assert env["STORY_AGENT_IMAGE_MODEL"] == "flux-schnell"
    assert env["STORY_AGENT_IMAGE_SIZE"] == "1536x1024"
    assert env["OPENAI_BASE_URL"] == "https://nangeai.top/v1"
