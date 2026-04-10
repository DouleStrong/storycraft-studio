# 2026-04-10 Langfuse Tracing 接入说明

## 这轮接入了什么

StoryCraft Studio 现在已经把 Langfuse tracing 接到工作流层，而不是只停在 provider 调用层。

当前 tracing 结构分两层：

- 工作流根 trace：一条 job 对应一条 Langfuse workflow trace
- agent 子 observation：每个 `planner / writer / reviewer / visual_prompt / image_generation` step 对应一个子 observation

本地数据库仍然保留原有 `AgentRun` 作为主记录。
Langfuse tracing 的定位是：

- 统一观测
- 调 prompt 时看效果
- 复盘某轮生成为什么失败或为什么质量波动

不是替代当前本地 trace 表。

## 已接入位置

- 根 trace 启动：`backend/app/workflow.py`
- agent 子 observation 启动与更新：`backend/app/workflow.py`
- Langfuse 封装层：`backend/app/langfuse_tracing.py`
- FastAPI 注入：`backend/app/main.py`
- worker 注入：`backend/app/worker.py`

## 当前行为

### 1. 一个 job 会创建一条 workflow trace

trace 名称格式：

```text
storycraft.workflow.{job_type}
```

示例：

- `storycraft.workflow.outline`
- `storycraft.workflow.chapter_draft`
- `storycraft.workflow.chapter_scenes`
- `storycraft.workflow.scene_illustrations`

### 2. 每个 agent step 会创建子 observation

name 格式：

```text
storycraft.{step_key}
```

示例：

- `storycraft.planner`
- `storycraft.writer_draft`
- `storycraft.reviewer_draft`
- `storycraft.writer_scenes`
- `storycraft.reviewer_scenes`
- `storycraft.visual_prompt`
- `storycraft.image_generation`

### 3. 现有 AgentRun 会回填 Langfuse 元数据

每个 `AgentRun.usage_payload` 里现在会附带：

```json
{
  "langfuse": {
    "trace_id": "...",
    "observation_id": "...",
    "trace_url": "..."
  }
}
```

同时 `GenerationJob.result_payload` 也会附带根 trace 信息：

```json
{
  "langfuse": {
    "trace_id": "...",
    "observation_id": "...",
    "trace_url": "..."
  }
}
```

这意味着：

- 前端 job 详情页后续可以直接挂一个 “在 Langfuse 中打开” 的按钮
- 不需要额外建表，也能从现有 API 里拿到 Langfuse 跳转信息

## 使用前提

只要配置了这三个环境变量，worker 和 API 就会自动启用 tracing：

- `LANGFUSE_BASE_URL`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

你当前给的配置可以直接使用：

```env
LANGFUSE_BASE_URL=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-46285617-d60b-456c-997f-57b05b291eac
LANGFUSE_SECRET_KEY=sk-lf-d20611ea-9b16-4578-8678-243d9c35ca71
```

## 当前落点与限制

### 已完成

- workflow 根 trace
- agent 子 observation
- stream 过程中的阶段更新
- 完成/失败状态同步
- trace url 回填到本地 job / agent run

### 暂未做

- 把 Langfuse trace url 直接展示到前端按钮
- 把 prompt 对象作为 Langfuse 原生 prompt artifact 关联到 generation
- 导出链路的更细粒度 span
- 对非 agent 的 persist 节点单独建 span

这些都可以继续往上加，但这轮先把最关键的“真实可追踪”打通。

## 为什么这套接法更稳

### 1. 不让 Langfuse 成为主存储

一旦外部 tracing 平台抖动，创作主流程不能跟着坏。
所以本地 `AgentRun` 仍然是主记录，Langfuse 是镜像与观测层。

### 2. 先把 workflow trace 做完整，再考虑更细颗粒度

如果一开始就给每个 persist / db write / export 子步骤都建 span，数据量会上来得很快，UI 里也会变噪。
先保住用户真正关心的那条链：

- 谁生成了
- 谁审了
- 结果为什么采纳
- 最终在哪一轮失败了

### 3. trace 要能和 prompt 版本对应起来

现在 provider 已经会把这些字段写回 agent trace：

- `prompt_name`
- `prompt_source`
- `prompt_version`
- `prompt_label`
- `prompt_registry_error`

这意味着后续正文质量波动时，我们可以把三个维度对齐看：

- Langfuse 里到底用了哪版 prompt
- 这轮模型是什么
- 本地落库的成稿和 reviewer 决策是什么
