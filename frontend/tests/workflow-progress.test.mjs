import test from "node:test";
import assert from "node:assert/strict";

import { resolveWorkflowProgress } from "../workflow-progress.mjs";

test("resolveWorkflowProgress marks processing stage and keeps later stages pending", () => {
  const progress = resolveWorkflowProgress({
    status: "processing",
    progress: 48,
    result: {
      live_state: {
        current_stage: "generate",
        current_step: "writer_draft",
        current_step_label: "Writer 生成正文",
        latest_agent_name: "writer",
        latest_agent_summary: "正在把章节目标拆成三段有推进力的正文。",
        stage_history: [
          { stage: "queued", status: "completed" },
          { stage: "context", status: "completed" },
          { stage: "generate", status: "processing" },
        ],
      },
    },
  });

  assert.equal(progress.currentStage, "generate");
  assert.equal(progress.currentStepLabel, "Writer 生成正文");
  assert.equal(progress.latestAgentSummary, "正在把章节目标拆成三段有推进力的正文。");
  assert.equal(progress.stages[0].state, "done");
  assert.equal(progress.stages[2].state, "active");
  assert.equal(progress.stages[3].state, "pending");
});

test("resolveWorkflowProgress marks review stage as awaiting user when reviewer interrupts", () => {
  const progress = resolveWorkflowProgress({
    status: "awaiting_user",
    result: {
      live_state: {
        current_stage: "review",
        current_step: "create_intervention",
        current_step_label: "等待作者确认",
        stage_history: [
          { stage: "queued", status: "completed" },
          { stage: "context", status: "completed" },
          { stage: "generate", status: "completed" },
          { stage: "review", status: "awaiting_user" },
        ],
      },
    },
  });

  assert.equal(progress.currentStage, "review");
  assert.equal(progress.stages[3].state, "awaiting_user");
  assert.equal(progress.stages[4].state, "pending");
});

test("resolveWorkflowProgress marks all stages done after completion", () => {
  const progress = resolveWorkflowProgress({
    status: "completed",
    result: {
      live_state: {
        current_stage: "complete",
        current_step: "complete",
        current_step_label: "工作流完成",
        stage_history: [
          { stage: "queued", status: "completed" },
          { stage: "context", status: "completed" },
          { stage: "generate", status: "completed" },
          { stage: "review", status: "completed" },
          { stage: "persist", status: "completed" },
          { stage: "complete", status: "completed" },
        ],
      },
    },
  });

  assert.equal(progress.currentStage, "complete");
  assert.equal(progress.stages.at(-1).state, "done");
  assert.ok(progress.stages.every((stage) => stage.state === "done"));
});
