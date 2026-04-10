import test from "node:test";
import assert from "node:assert/strict";

import { buildAgentWorkbench } from "../agent-workbench.mjs";

test("buildAgentWorkbench prioritizes the selected job as the current collaboration focus", () => {
  const result = buildAgentWorkbench(
    {
      chapters: [{ id: 11, order_index: 2, title: "雨夜站台", pending_interventions: [] }],
      jobs: [
        {
          id: 98,
          job_type: "chapter_draft",
          status: "processing",
          progress: 44,
          chapter_id: 11,
          created_at: "2026-04-09T08:00:00.000Z",
          result: {
            live_state: {
              current_stage: "generate",
              current_step: "writer_draft",
              current_step_label: "Writer 生成正文",
              latest_agent_summary: "正在把雨夜重逢写成更克制的第一人称叙述。",
              stage_history: [
                { stage: "queued", status: "completed" },
                { stage: "context", status: "completed" },
                { stage: "generate", status: "processing" },
              ],
            },
          },
        },
      ],
    },
    {
      selectedJobDetail: {
        id: 98,
        job_type: "chapter_draft",
        status: "processing",
        progress: 44,
        chapter_id: 11,
        created_at: "2026-04-09T08:00:00.000Z",
        result: {
          live_state: {
            current_stage: "generate",
            current_step: "writer_draft",
            current_step_label: "Writer 生成正文",
            latest_agent_summary: "正在把雨夜重逢写成更克制的第一人称叙述。",
            stage_history: [
              { stage: "queued", status: "completed" },
              { stage: "context", status: "completed" },
              { stage: "generate", status: "processing" },
            ],
          },
        },
      },
      activeChapterId: 11,
    },
  );

  assert.equal(result.focus.kind, "job");
  assert.equal(result.focus.title, "章节正文生成");
  assert.equal(result.focus.chapterLabel, "第 2 章 · 雨夜站台");
  assert.equal(result.focus.currentStepLabel, "Writer 生成正文");
  assert.equal(result.focus.summary, "正在把雨夜重逢写成更克制的第一人称叙述。");
  assert.equal(result.summary.activeJobs, 1);
  assert.equal(result.history[0].jobId, 98);
  assert.equal(result.history[0].isSelected, true);
  assert.equal(result.history[0].currentStepLabel, "Writer 生成正文");
});

test("buildAgentWorkbench falls back to an awaiting-user job when no explicit selection exists", () => {
  const result = buildAgentWorkbench(
    {
      chapters: [{ id: 5, order_index: 1, title: "返程前夜", pending_interventions: [] }],
      jobs: [
        {
          id: 102,
          job_type: "chapter_scenes",
          status: "awaiting_user",
          progress: 100,
          chapter_id: 5,
          created_at: "2026-04-09T08:05:00.000Z",
          status_message: "Reviewer 建议先确认情绪推进，再决定是否重写本章。",
        },
        {
          id: 101,
          job_type: "outline",
          status: "completed",
          progress: 100,
          created_at: "2026-04-09T08:00:00.000Z",
        },
      ],
    },
    { activeChapterId: 5 },
  );

  assert.equal(result.focus.kind, "job");
  assert.equal(result.focus.statusLabel, "等待你确认");
  assert.equal(result.focus.eyebrow, "等待作者决策");
  assert.equal(result.focus.summary, "Reviewer 建议先确认情绪推进，再决定是否重写本章。");
  assert.equal(result.summary.awaitingJobs, 1);
  assert.equal(result.summary.completedJobs, 1);
  assert.equal(result.history[0].jobId, 102);
  assert.equal(result.history[0].tone, "warn");
  assert.equal(result.history[1].jobId, 101);
});

test("buildAgentWorkbench shows chapter-level intervention guidance when no jobs are running", () => {
  const result = buildAgentWorkbench(
    {
      chapters: [
        {
          id: 8,
          order_index: 3,
          title: "最后一封回信",
          pending_interventions: [
            {
              id: 1,
              status: "pending",
              reviewer_notes: "这一章的称呼和前文不一致，建议先统一再决定是否重写。",
              suggested_guidance: "保留克制语气，只调整称呼和时间线。",
            },
          ],
        },
      ],
      jobs: [],
    },
    { activeChapterId: 8 },
  );

  assert.equal(result.focus.kind, "intervention");
  assert.equal(result.focus.title, "这一章正在等待你的决定");
  assert.equal(result.focus.summary, "这一章的称呼和前文不一致，建议先统一再决定是否重写。");
  assert.equal(result.focus.detail, "保留克制语气，只调整称呼和时间线。");
  assert.equal(result.summary.totalJobs, 0);
  assert.deepEqual(result.history, []);
});
