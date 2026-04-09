# StoryCraft Studio

StoryCraft Studio is a single-user desktop-first creation platform for chapter-based fiction and short-form drama workflows. It lets creators build projects, define characters, generate chapter outlines and drafts, create scene illustrations, and export a polished PDF/DOCX bundle.

## What is included

- FastAPI backend with REST APIs for auth, projects, characters, chapter generation, illustration jobs, and exports
- Local async job orchestration with persisted job status tracking
- A four-agent writing pipeline for `Planner`, `Writer`, `Reviewer`, and `Visual Prompt`
- OpenAI-compatible text model integration for structured JSON generation
- OpenAI-compatible image generation for scene illustration candidates
- Editorial-style frontend workspace served at `/studio/`
- PDF and DOCX export pipeline for a complete illustrated story bundle

## Runtime requirements

- PostgreSQL is now the only supported runtime database for the API and worker.
- Redis + RQ is required for background jobs.
- Legacy SQLite files can still be imported once with the built-in import tool.

## Quick start with the AGI conda environment

1. Configure `.env` with a PostgreSQL URL, Redis URL, and your OpenAI-compatible credentials.
   A ready-to-run example is in `.env.example`.
   If you want Docker-managed infrastructure quickly, run:

```bash
cd /home/doublestrong/codex/storycraft-studio
REDIS_AUTH=myredissecret docker compose -f docker-compose.infrastructure.yml up -d postgres redis
```

2. Start the API on `8010`:

```bash
conda run -n AGI uvicorn app.main:app --app-dir /home/doublestrong/codex/storycraft-studio/backend --reload --port 8010
```

3. Start the worker in a second shell:

```bash
cd /home/doublestrong/codex/storycraft-studio/backend
conda run -n AGI python -m app.worker
```

Open:

- Studio UI: `http://127.0.0.1:8010/studio/`
- Health check: `http://127.0.0.1:8010/health`

完整的本地启动、联调与排障说明见：

- [docs/local-dev.md](/home/doublestrong/codex/storycraft-studio/docs/local-dev.md)

## Legacy SQLite import

If you still have old split SQLite files such as:

- `/home/doublestrong/codex/storycraft-studio/storycraft_studio.db`
- `/home/doublestrong/codex/storycraft-studio/backend/storycraft_studio.db`

run:

```bash
cd /home/doublestrong/codex/storycraft-studio/backend
conda run -n AGI python -m app.legacy_import
```

The importer will:

- merge detected legacy SQLite databases into the currently configured primary database
- rewrite storage/export file paths into the active runtime directories
- copy files from legacy `runtime/storage` and `runtime/exports` when needed

## Tests

```bash
conda run -n AGI pytest /home/doublestrong/codex/storycraft-studio/backend/tests -q
```

## Notes

- The backend now auto-loads the project root `.env` file on startup.
- Runtime startup now rejects SQLite unless `STORY_PLATFORM_ALLOW_SQLITE=1` is set explicitly for tests or one-off smoke scripts.
- By default, existing shell environment variables keep precedence. If you want this project's `.env` to take over even when your shell already has global `OPENAI_*` variables, set `STORY_PLATFORM_DOTENV_OVERRIDE=1` in `.env`.
- You can point to a custom env file with `STORY_PLATFORM_ENV_FILE=/path/to/.env`.
- The current build uses local filesystem storage for uploaded assets, generated illustrations, thumbnails, and exports.
- Text generation in v2 uses a real OpenAI-compatible provider when `OPENAI_BASE_URL` and `OPENAI_API_KEY` are configured.
- Text generation expects an OpenAI-compatible endpoint via:
  - `OPENAI_BASE_URL`
  - `OPENAI_API_KEY`
  - optional `OPENAI_MODEL`, `STORY_AGENT_PLANNER_MODEL`, `STORY_AGENT_WRITER_MODEL`, `STORY_AGENT_REVIEWER_MODEL`, `STORY_AGENT_VISUAL_MODEL`
- Image generation now supports real OpenAI-compatible image providers via:
  - `STORY_AGENT_IMAGE_MODEL`
  - `STORY_AGENT_IMAGE_SIZE`
- Reviewer only interrupts the user on high-severity issues by default. Tune this with `STORY_REVIEW_INTERVENTION_MIN_SEVERITY`.

## Provider smoke

```bash
OPENAI_BASE_URL=https://nangeai.top/v1 \
OPENAI_API_KEY=your-key \
conda run -n AGI python -m app.provider_smoke
```

## Story Flow Smoke

```bash
OPENAI_BASE_URL=https://nangeai.top/v1 \
OPENAI_API_KEY=your-key \
OPENAI_MODEL=gpt-4o-mini \
conda run -n AGI python -m app.story_flow_smoke
```
