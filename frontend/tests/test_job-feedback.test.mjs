import test from "node:test";
import assert from "node:assert/strict";

import { describeJobFeedback } from "../job-feedback.mjs";

test("describeJobFeedback explains that a fresh queued job is waiting for the worker", () => {
  const feedback = describeJobFeedback({
    status: "queued",
    status_message: "",
    created_at: "2026-04-07T10:00:00.000Z",
  }, new Date("2026-04-07T10:00:04.000Z").getTime());

  assert.deepEqual(feedback, {
    message: "任务已入队，正在等待 worker 接手。",
    tone: "info",
  });
});

test("describeJobFeedback flags long queued jobs without live updates as likely abnormal", () => {
  const feedback = describeJobFeedback({
    status: "queued",
    status_message: "",
    created_at: "2026-04-07T10:00:00.000Z",
  }, new Date("2026-04-07T10:00:35.000Z").getTime());

  assert.deepEqual(feedback, {
    message: "排队时间偏长，通常不是正常生成，优先检查 worker 或重试这条任务。",
    tone: "warn",
  });
});
