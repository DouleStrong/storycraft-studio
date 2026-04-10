import test from "node:test";
import assert from "node:assert/strict";

import { buildStoryBibleWorkbench } from "../story-bible-workbench.mjs";

test("buildStoryBibleWorkbench creates a compact summary card for the workspace rail", () => {
  const result = buildStoryBibleWorkbench(
    {
      id: 101,
      target_chapter_count: 8,
      target_length: "8章，短剧节奏",
      story_bible: {
        world_notes: "故事发生在沿江老城，一座仍保留旧电台系统的城市里，公开叙事和私密记忆长期错位。",
        style_notes: "浅色、克制、电影感，不靠堆砌辞藻取胜。",
        writing_rules: ["人物驱动剧情", "章尾必须留钩子", "优先场景化描写"],
        addressing_rules: "公开场合保持全名称呼，情绪升高时才允许改口。",
        timeline_rules: "默认连续时间推进，不允许无提示跳时。",
        current_revision: {
          id: 14,
          revision_index: 3,
        },
      },
    },
    {
      storyBibleRevisions: [
        {
          id: 14,
          revision_index: 3,
          created_by: "user",
          created_at: "2026-04-09T08:30:00.000Z",
        },
      ],
    },
  );

  assert.equal(result.summary.currentRevisionLabel, "当前版本 #3");
  assert.equal(result.summary.targetChapterLabel, "8章");
  assert.equal(result.summary.ruleCountLabel, "3 条规则");
  assert.equal(result.summary.filledSectionLabel, "4 项已填写");
  assert.equal(result.summary.targetLengthChip, "8章，短剧节奏");
  assert.equal(result.summary.previewSections.length, 3);
  assert.equal(result.summary.previewSections[0].label, "世界观");
  assert.match(result.summary.previewSections[0].excerpt, /沿江老城/);
  assert.equal(result.summary.lastUpdatedLabel, "最近更新");
  assert.ok(result.summary.lastUpdatedValue.length > 0);
  assert.ok(result.summary.lastUpdatedCompactValue.length > 0);
  assert.equal(result.detail.writingRulesText, "人物驱动剧情\n章尾必须留钩子\n优先场景化描写");
});

test("buildStoryBibleWorkbench falls back gracefully when story bible data is sparse", () => {
  const result = buildStoryBibleWorkbench(
    {
      id: 202,
      target_chapter_count: 6,
      target_length: "",
      story_bible: null,
    },
    {
      storyBibleRevisions: [],
    },
  );

  assert.equal(result.summary.currentRevisionLabel, "未记录版本");
  assert.equal(result.summary.targetChapterLabel, "6章");
  assert.equal(result.summary.ruleCountLabel, "0 条规则");
  assert.equal(result.summary.filledSectionLabel, "0 项已填写");
  assert.equal(result.summary.targetLengthChip, "");
  assert.equal(result.summary.previewSections[0].excerpt, "当前还没有填写世界观摘要。");
  assert.equal(result.detail.writingRulesText, "");
});
