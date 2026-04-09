import test from "node:test";
import assert from "node:assert/strict";

import {
  buildStudioRoute,
  buildProjectPayload,
  findPendingIntervention,
  isTerminalJobStatus,
  parseStudioRoute,
  partitionCharacterLibrary,
  resolveActiveChapterId,
  resolveWorkspaceProjectId,
  resolveWorkspaceMode,
} from "../studio-state.mjs";

test("resolveActiveChapterId keeps the current chapter when it still exists", () => {
  const project = {
    chapters: [
      { id: 11, title: "第一章" },
      { id: 12, title: "第二章" },
    ],
  };

  assert.equal(resolveActiveChapterId(project, 12), 12);
});

test("resolveActiveChapterId falls back to the first chapter when current chapter is missing", () => {
  const project = {
    chapters: [
      { id: 21, title: "第一章" },
      { id: 22, title: "第二章" },
    ],
  };

  assert.equal(resolveActiveChapterId(project, 999), 21);
  assert.equal(resolveActiveChapterId(project, null), 21);
});

test("buildProjectPayload parses target chapter count as a number", () => {
  const payload = buildProjectPayload({
    title: "桥面风声",
    genre: "悬疑",
    tone: "冷静、克制",
    era: "当代",
    target_chapter_count: "8",
    target_length: "8章，短剧节奏",
    logline: "一条深夜语音把她重新拉回桥面。",
  });

  assert.equal(payload.target_chapter_count, 8);
  assert.equal(typeof payload.target_chapter_count, "number");
  assert.equal(payload.target_length, "8章，短剧节奏");
});

test("parseStudioRoute resolves dashboard and workspace hashes", () => {
  assert.deepEqual(parseStudioRoute(""), { view: "dashboard", projectId: null });
  assert.deepEqual(parseStudioRoute("#/dashboard"), { view: "dashboard", projectId: null });
  assert.deepEqual(parseStudioRoute("#/projects/42"), { view: "workspace", projectId: 42 });
  assert.deepEqual(parseStudioRoute("#/unknown"), { view: "dashboard", projectId: null });
});

test("buildStudioRoute creates stable hashes for dashboard and workspace", () => {
  assert.equal(buildStudioRoute("dashboard"), "#/dashboard");
  assert.equal(buildStudioRoute("workspace", 19), "#/projects/19");
});

test("resolveWorkspaceProjectId only opens a project when the requested project actually exists", () => {
  const projects = [
    { id: 5, title: "夜路归档" },
    { id: 8, title: "冷幕之下" },
  ];

  assert.equal(resolveWorkspaceProjectId(projects, 8, null), 8);
  assert.equal(resolveWorkspaceProjectId(projects, null, 5), 5);
  assert.equal(resolveWorkspaceProjectId(projects, 99, null), null);
  assert.equal(resolveWorkspaceProjectId(projects, null, null), null);
});

test("findPendingIntervention returns the first pending intervention on a chapter", () => {
  const chapter = {
    pending_interventions: [
      { id: 301, status: "resolved" },
      { id: 302, status: "pending", intervention_type: "rewrite_writer" },
    ],
  };

  assert.deepEqual(findPendingIntervention(chapter), {
    id: 302,
    status: "pending",
    intervention_type: "rewrite_writer",
  });
});

test("isTerminalJobStatus treats awaiting_user as a terminal UI state", () => {
  assert.equal(isTerminalJobStatus("queued"), false);
  assert.equal(isTerminalJobStatus("processing"), false);
  assert.equal(isTerminalJobStatus("awaiting_user"), true);
  assert.equal(isTerminalJobStatus("completed"), true);
  assert.equal(isTerminalJobStatus("failed"), true);
});

test("resolveWorkspaceMode keeps three columns only when the editor has enough width", () => {
  assert.equal(resolveWorkspaceMode(1600), "wide");
  assert.equal(resolveWorkspaceMode(1320), "balanced");
  assert.equal(resolveWorkspaceMode(980), "stacked");
});

test("partitionCharacterLibrary splits attached and available characters for the current project", () => {
  const library = [
    { id: 11, name: "林听", linked_project_ids: [3, 8] },
    { id: 12, name: "顾昼", linked_project_ids: [] },
    { id: 13, name: "沈苒", linked_project_ids: [8] },
  ];

  const result = partitionCharacterLibrary(library, { id: 8 });

  assert.deepEqual(
    result.attached.map((item) => item.id),
    [11, 13],
  );
  assert.deepEqual(
    result.available.map((item) => item.id),
    [12],
  );
});

test("partitionCharacterLibrary treats all characters as available when no project is selected", () => {
  const library = [
    { id: 21, linked_project_ids: [4] },
    { id: 22, linked_project_ids: [] },
  ];

  const result = partitionCharacterLibrary(library, null);

  assert.deepEqual(result.attached, []);
  assert.deepEqual(
    result.available.map((item) => item.id),
    [21, 22],
  );
});
