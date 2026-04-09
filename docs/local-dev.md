# StoryCraft Studio 本地运行与联调

这份文档按当前项目的真实运行形态整理：

- `PostgreSQL` 作为唯一正式数据库
- `Redis + RQ worker` 负责异步任务
- `FastAPI` 同时提供 API 和前端静态页面 `/studio/`
- 前端源码在 `frontend/`，当前不需要额外打包服务

## 1. 前置环境

- Conda 环境：`AGI`
- Python 依赖已经安装在 `AGI`
- Docker 可用
- 代码目录：`/home/doublestrong/codex/storycraft-studio`

## 2. 准备 `.env`

如果还没有项目根目录 `.env`，先从示例复制：

```bash
cd /home/doublestrong/codex/storycraft-studio
cp .env.example .env
```

推荐至少确认这些字段：

```dotenv
OPENAI_BASE_URL=https://nangeai.top/v1
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-4o-mini
STORY_AGENT_PLANNER_MODEL=gpt-4o-mini
STORY_AGENT_WRITER_MODEL=gpt-4o-mini
STORY_AGENT_REVIEWER_MODEL=gpt-4o-mini
STORY_AGENT_VISUAL_MODEL=gpt-4o-mini
STORY_AGENT_IMAGE_MODEL=flux-schnell
STORY_AGENT_IMAGE_SIZE=1536x1024

STORY_PLATFORM_DB_URL=postgresql+psycopg://postgres:your-password@127.0.0.1:5432/storycraft
REDIS_URL=redis://:myredissecret@127.0.0.1:6379/0
STORY_PLATFORM_QUEUE_BACKEND=rq
STORY_QUEUE_NAME=storycraft
```

说明：

- `STORY_AGENT_IMAGE_MODEL` 当前实测 `flux-schnell` 和 `qwen-image-max` 能成功出图。
- `gpt-image-1` / `gpt-image-1-mini` 在当前聚合源上容易遇到上游饱和，不建议作为默认值。
- 如果你本机 PostgreSQL 用户名和密码不同，直接改 `STORY_PLATFORM_DB_URL` 即可。

## 3. 启动 PostgreSQL 和 Redis

项目内已经提供了基础设施 compose 文件，现在同时包含 `postgres + redis`：

```bash
cd /home/doublestrong/codex/storycraft-studio
REDIS_AUTH=myredissecret docker compose -f docker-compose.infrastructure.yml up -d postgres redis
```

检查容器：

```bash
docker compose -f /home/doublestrong/codex/storycraft-studio/docker-compose.infrastructure.yml ps
```

如果你不用 Docker，而是本机已经有 PostgreSQL / Redis：

- 确保 PostgreSQL 监听 `127.0.0.1:5432`
- 确保 Redis 监听 `127.0.0.1:6379`
- 确保 `.env` 里的数据库密码、Redis 密码和实际一致

## 4. 启动 API

项目会在启动时自动执行 Alembic 迁移，所以不需要手动先跑 `alembic upgrade`。

```bash
cd /home/doublestrong/codex/storycraft-studio/backend
conda run --no-capture-output -n AGI uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

说明：

- 推荐用 `8010`，避免和你机器上其他服务冲突。
- 前端页面也是由这个进程提供，地址会是 `/studio/`。

## 5. 启动 Worker

另开一个终端：

```bash
cd /home/doublestrong/codex/storycraft-studio/backend
conda run --no-capture-output -n AGI python -m app.worker
```

如果 Redis 需要密码，`REDIS_URL` 已经会从项目根目录 `.env` 自动读取。

## 6. 打开前端

浏览器访问：

- Studio 主界面：`http://127.0.0.1:8010/studio/`
- 健康检查：`http://127.0.0.1:8010/health`

当前前端没有独立开发服务器要求。只要 FastAPI 正常启动，前端就能直接访问。

## 7. 推荐联调顺序

建议按下面的最短链路验证：

1. 注册或登录一个账号
2. 在控制台创建一个项目
3. 新建一个角色，并可选上传参考图
4. 进入项目工作空间，点击“生成章节大纲”
5. 进入第一章，依次点击“生成正文”和“生成场景”
6. 在某个场景的“剧照工作台”里生成候选剧照
7. 选一张设为主图，再用“参考当前主图重生成”验证参考回灌
8. 最后测试导出 `PDF + DOCX`

## 8. 可用 smoke 命令

### 8.1 Provider 文本连通性

```bash
cd /home/doublestrong/codex/storycraft-studio/backend
conda run --no-capture-output -n AGI python -m app.provider_smoke
```

### 8.2 真实图片模型单点验证

```bash
cd /home/doublestrong/codex/storycraft-studio/backend
conda run --no-capture-output -n AGI python - <<'PY'
from io import BytesIO
from PIL import Image

from app.config import load_settings
from app.providers import OpenAICompatibleImageClient

settings = load_settings()
client = OpenAICompatibleImageClient(
    base_url=settings.openai_base_url,
    api_key=settings.openai_api_key,
    timeout_seconds=settings.story_agent_timeout_seconds,
    default_model=settings.story_agent_image_model,
)
result = client.generate_images(
    model=settings.story_agent_image_model,
    prompt="A restrained cinematic still of a lone radio host in a midnight studio, realistic, moody blue light",
    candidate_count=1,
    size=settings.story_agent_image_size,
)
image = result["images"][0]
img = Image.open(BytesIO(image.payload_bytes))
img.load()
print("image smoke ok", result["trace"]["model"], img.size, img.format)
PY
```

### 8.3 端到端 story flow smoke

```bash
cd /home/doublestrong/codex/storycraft-studio/backend
conda run --no-capture-output -n AGI python -m app.story_flow_smoke --chapter-count 2 --candidate-count 1 --timeout 180
```

说明：

- 这条命令会在临时 SQLite 环境里跑一条真实外部模型链路，只用于 smoke。
- 如果它报 `Temporary failure in name resolution`，通常是当前环境 DNS / 网络抖动，不一定是业务代码错误。

### 8.4 导出交付 smoke

如果你想只验证“导出任务创建 -> PDF/DOCX 落地 -> `/api/exports/{id}` 返回 -> 下载可用”这一段，而不重跑整条写作链路，可以直接对一个现有项目执行：

```bash
cd /home/doublestrong/codex/storycraft-studio/backend
conda run --no-capture-output -n AGI python -m app.export_delivery_smoke --project-id 10 --formats pdf docx --timeout 30
```

说明：

- 这条命令会读取当前 Postgres 里的真实项目数据。
- 它会自动冻结当前运行时配置，然后临时切到 `inline` 队列来触发导出，避免依赖你当前是否已经启动 worker。
- 命令会打印 `JOB_CREATED`、`JOB_STATUS`、`EXPORT`、`DOWNLOAD`，最后输出 `export delivery smoke ok`。
- 如果项目 owner 当前没有 `access_token`，先通过前端登录一次，让该用户拿到新的 token 后再跑。

为什么这里要“冻结当前运行时配置”：

- 项目根目录 `.env` 默认启用了 `STORY_PLATFORM_DOTENV_OVERRIDE=1`
- 如果不先冻结，临时设置的 `STORY_PLATFORM_QUEUE_BACKEND=inline` 可能会再次被 `.env` 覆盖回 `rq`
- 结果就是本来想跑本地 inline smoke，却又去连接 Redis

## 9. 常见问题

### PostgreSQL 密码错误

如果看到类似：

```text
password authentication failed
```

说明 `.env` 中的 `STORY_PLATFORM_DB_URL` 和数据库真实凭证不一致，直接改成正确用户名密码即可。

### Redis Authentication required

如果 worker 启动时报：

```text
redis.exceptions.AuthenticationError: Authentication required
```

说明 `REDIS_URL` 缺少密码或密码不匹配。带密码的格式应该是：

```dotenv
REDIS_URL=redis://:myredissecret@127.0.0.1:6379/0
```

### 8000 端口被占用

如果你机器上 `8000` 已被别的服务占用，比如 `milvus attu`，直接把 API 改跑在 `8010`：

```bash
conda run --no-capture-output -n AGI uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

### 前端打不开或空白

优先检查：

1. `uvicorn` 是否真的启动成功
2. 浏览器访问的是不是 `http://127.0.0.1:8010/studio/`
3. 控制台有没有后端返回的 `500` 错误
4. Worker 是否正在运行，否则生成类任务只会一直排队

## 10. 回归测试

后端：

```bash
cd /home/doublestrong/codex/storycraft-studio/backend
conda run --no-capture-output -n AGI pytest tests -q
```

前端状态层测试：

```bash
cd /home/doublestrong/codex/storycraft-studio/frontend
node --test tests/*.test.mjs
```
