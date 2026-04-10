# 2026-04-10 Langfuse Prompt Registry 接入说明

## 这轮解决了什么

StoryCraft Studio 现有的多 Agent prompt 之前全部硬编码在 `backend/app/providers.py`。
这会带来两个明显问题：

- 调 prompt 需要改代码、重启后端、重新走测试
- Writer / Reviewer / Planner 的实验很难沉淀成可管理资产

这一轮先把最核心的四类 prompt 接成“Langfuse 优先，本地 fallback 兜底”：

- `planner`
- `writer_draft`
- `reviewer_draft`
- `visual_prompt`

如果 Langfuse 没配置、目标 prompt 不存在、标签不对、模板变量缺失，系统不会直接把写作链路打断，而是自动退回当前代码里的本地 prompt。

## 配置项

后端新增以下环境变量：

- `LANGFUSE_BASE_URL`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_PROMPT_LABEL`
- `LANGFUSE_PROMPT_CACHE_TTL_SECONDS`

当前默认行为：

- `LANGFUSE_PROMPT_LABEL=production`
- `LANGFUSE_PROMPT_CACHE_TTL_SECONDS=300`

如果本地调试时还没给 prompt 打 `production` 标签，建议显式设置：

```env
LANGFUSE_PROMPT_LABEL=staging
```

## 当前实现边界

这轮没有把所有 prompt 一次性搬进 Langfuse，只先接了写作主链路里的四个关键节点。

暂时仍保持本地硬编码的部分：

- 角色视觉档案 `build_character_profile`
- scenes writer / reviewer
- smoke prompt

原因不是做不到，而是先把最常调、最影响正文质量的 prompt 资产化，风险更可控。

## Prompt 名称与变量

### 1. `planner`

建议在 Langfuse 中配置为 chat prompt。

可用变量：

- `project_title`
- `chapter_count`
- `extra_guidance`
- `context_json`

### 2. `writer_draft`

可用变量：

- `project_title`
- `chapter_title`
- `chapter_order`
- `extra_guidance`
- `context_json`
- `quality_constraints_json`

说明：

- `context_json` 已经包含项目、章节、角色、前序章节、`style_memory`、`quality_constraints`
- 如果 Langfuse 里只想维护系统提示词，用户消息里直接引用 `{{context_json}}` 就够了

### 3. `reviewer_draft`

可用变量：

- `project_title`
- `chapter_title`
- `chapter_order`
- `context_json`
- `quality_flags_json`

说明：

- `context_json` 已经带了 `draft_payload`
- `quality_flags_json` 主要用于提醒 Reviewer 当前稿子有没有命中本地检测到的“模板腔/套话”风险

### 4. `visual_prompt`

可用变量：

- `project_title`
- `scene_title`
- `extra_guidance`
- `context_json`

说明：

- `context_json` 已包含场景信息、角色视觉锚点、canonical 图引用信息

## 模板写法建议

推荐直接在 Langfuse 使用 chat prompt，两条 message 就够：

- `system`
- `user`

示例结构：

```text
system:
你是 StoryCraft Studio 的 Writer Agent。
请写出章节正文，风格偏短剧/网文式混合叙事。
……

user:
请根据以下上下文写出本章 narrative_blocks：
{{context_json}}
```

当前 registry 支持替换：

- `{{variable}}`
- `{{{variable}}}`

也支持简单点号路径，例如：

- `{{project_title}}`
- `{{chapter_title}}`

## 失败回退策略

当出现以下问题时，后端会自动回退到本地 prompt：

- Langfuse 未配置
- 请求 Langfuse 失败
- prompt 不存在
- label 不匹配
- 模板变量缺失
- 返回 payload 结构不符合当前支持格式

同时会在 agent trace 中写入这些摘要字段：

- `prompt_source`
- `prompt_label`
- `prompt_version`
- `prompt_registry_error`

这让我们在前端或调试日志里能看出：

- 这次调用到底是 Langfuse prompt 还是本地 fallback
- 如果退回本地，是因为哪一步失败

## 这轮的工程经验

### 1. 先做 prompt source 抽象，再做 prompt 内容迁移

如果一上来就把所有文案从代码搬到 Langfuse，很容易在“变量不全、版本不清、回退缺失”的情况下把主链路弄脆。

更稳的路径是：

1. 先抽出 `PromptRegistry`
2. 先证明 Langfuse 拉取和 fallback 是可靠的
3. 再逐个把 prompt 内容迁进去

### 2. fallback 不是临时方案，而是线上保险丝

对于写作平台来说，Prompt 管理平台不应该成为单点故障。
用户点“生成正文”时，最糟糕的体验不是文风没调准，而是整个 job 直接失败。

### 3. prompt 管理要和 trace 联动

只知道“这次 Writer 输出差”还不够。
更关键的是知道：

- 用的是 Langfuse 版 prompt 还是本地版 prompt
- 命中的是哪个 label
- 版本是多少

否则后面正文质量变动时，很难定位是模型问题、prompt 问题，还是持久化策略问题。
