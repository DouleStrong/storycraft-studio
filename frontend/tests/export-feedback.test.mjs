import test from "node:test";
import assert from "node:assert/strict";

import { describeReadyExport } from "../export-feedback.mjs";

test("describeReadyExport returns null when export is not completed yet", () => {
  const result = describeReadyExport({
    id: 8,
    status: "processing",
    files: [
      { format: "pdf", url: "/media/exports/project_8/demo_bundle.pdf" },
    ],
  });

  assert.equal(result, null);
});

test("describeReadyExport returns a downloadable summary for completed bundles", () => {
  const result = describeReadyExport({
    id: 9,
    status: "completed",
    files: [
      { format: "pdf", url: "/media/exports/project_9/demo_bundle.pdf" },
      { format: "docx", url: "/media/exports/project_9/demo_bundle.docx" },
    ],
  });

  assert.deepEqual(result, {
    title: "导出成品已就绪",
    summary: "PDF + DOCX 已生成，可直接下载到本地。",
    files: [
      {
        format: "pdf",
        formatLabel: "PDF",
        downloadLabel: "下载 PDF",
        url: "/media/exports/project_9/demo_bundle.pdf",
      },
      {
        format: "docx",
        formatLabel: "DOCX",
        downloadLabel: "下载 DOCX",
        url: "/media/exports/project_9/demo_bundle.docx",
      },
    ],
  });
});
