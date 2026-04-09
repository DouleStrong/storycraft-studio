import test from "node:test";
import assert from "node:assert/strict";

import { buildExportDeliveryCenter } from "../export-center.mjs";

test("buildExportDeliveryCenter returns an empty delivery board when there are no exports", () => {
  const result = buildExportDeliveryCenter([]);

  assert.equal(result.state, "empty");
  assert.equal(result.hero, null);
  assert.deepEqual(result.metrics, []);
  assert.deepEqual(result.cards, []);
});

test("buildExportDeliveryCenter summarizes the latest ready bundle and quality state", () => {
  const result = buildExportDeliveryCenter([
    {
      id: 3,
      status: "completed",
      formats: ["pdf", "docx"],
      completed_at: "2026-04-07T14:00:00.000Z",
      delivery_summary: {
        chapter_count: 8,
        character_count: 5,
        illustration_count: 4,
        total_size_bytes: 245760,
        quality_status: "passed",
        total_page_count: 26,
      },
      files: [
        { format: "pdf", url: "/media/exports/project_3/story.pdf", page_count: 26 },
        { format: "docx", url: "/media/exports/project_3/story.docx" },
      ],
    },
    {
      id: 2,
      status: "processing",
      formats: ["pdf"],
      delivery_summary: {
        chapter_count: 8,
        character_count: 5,
        illustration_count: 4,
        total_size_bytes: 0,
        quality_status: "pending",
        total_page_count: 0,
      },
      files: [],
    },
  ]);

  assert.equal(result.state, "ready");
  assert.equal(result.hero.title, "成品交付台");
  assert.equal(result.hero.qualityLabel, "质量校验通过");
  assert.equal(result.hero.downloads.length, 2);
  assert.deepEqual(result.metrics, [
    { label: "已完成导出", value: "1" },
    { label: "校验通过", value: "1" },
    { label: "总页数", value: "26" },
  ]);
  assert.equal(result.cards[0].id, 3);
  assert.equal(result.cards[0].downloads[0].label, "下载 PDF");
});
