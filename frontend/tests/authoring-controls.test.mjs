import test from "node:test";
import assert from "node:assert/strict";

import {
  buildProjectDuplicatePayload,
  buildSnapshotPayload,
  buildStoryBiblePayload,
  countProtectedContent,
} from "../authoring-controls.mjs";

test("buildStoryBiblePayload trims free text and expands rule lines", () => {
  const payload = buildStoryBiblePayload({
    world_notes: "  海雾旧港，所有冲突都围绕封存档案展开。  ",
    style_notes: "  动作先于解释。 ",
    writing_rules_text: "称呼必须稳定\n\n每章至少推进一条伏笔\n  避免上帝视角直给答案 ",
    addressing_rules: "  林听始终称顾昼为“顾昼”。 ",
    timeline_rules: "  全篇时间跨度限制在七天内。 ",
  });

  assert.deepEqual(payload, {
    world_notes: "海雾旧港，所有冲突都围绕封存档案展开。",
    style_notes: "动作先于解释。",
    writing_rules: ["称呼必须稳定", "每章至少推进一条伏笔", "避免上帝视角直给答案"],
    addressing_rules: "林听始终称顾昼为“顾昼”。",
    timeline_rules: "全篇时间跨度限制在七天内。",
  });
});

test("buildProjectDuplicatePayload falls back to a stable duplicate title", () => {
  assert.deepEqual(buildProjectDuplicatePayload("雾港备忘录", ""), { title: "雾港备忘录·副本" });
  assert.deepEqual(buildProjectDuplicatePayload("雾港备忘录", "  雾港备忘录·分支稿  "), {
    title: "雾港备忘录·分支稿",
  });
});

test("buildSnapshotPayload gives the workspace a readable fallback label", () => {
  assert.deepEqual(buildSnapshotPayload("桥面回音", ""), { label: "桥面回音 · 自动快照" });
  assert.deepEqual(buildSnapshotPayload("桥面回音", "  重写前备份 "), { label: "重写前备份" });
});

test("countProtectedContent summarizes user-edited and locked items in a chapter", () => {
  const summary = countProtectedContent({
    narrative_blocks: [
      { is_locked: true, is_user_edited: false },
      { is_locked: false, is_user_edited: true },
    ],
    scenes: [
      {
        is_locked: false,
        is_user_edited: true,
        dialogue_blocks: [
          { is_locked: true, is_user_edited: false },
          { is_locked: false, is_user_edited: false },
        ],
      },
    ],
  });

  assert.deepEqual(summary, {
    narrativeBlocks: 2,
    scenes: 1,
    dialogueBlocks: 1,
    total: 4,
  });
});
