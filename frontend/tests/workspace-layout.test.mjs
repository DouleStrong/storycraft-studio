import test from "node:test";
import assert from "node:assert/strict";

import { computeWorkspaceHeight, resolveWorkspaceDensity } from "../workspace-layout.mjs";

test("computeWorkspaceHeight respects viewport remaining space with a stable floor", () => {
  const height = computeWorkspaceHeight({
    viewportHeight: 1280,
    gridTop: 360,
    bottomOffset: 32,
  });

  assert.equal(height, 888);
});

test("computeWorkspaceHeight clamps to the minimum when remaining space is too short", () => {
  const height = computeWorkspaceHeight({
    viewportHeight: 880,
    gridTop: 500,
    bottomOffset: 32,
  });

  assert.equal(height, 520);
});

test("computeWorkspaceHeight clamps to the maximum for very tall displays", () => {
  const height = computeWorkspaceHeight({
    viewportHeight: 2200,
    gridTop: 260,
    bottomOffset: 48,
  });

  assert.equal(height, 980);
});

test("resolveWorkspaceDensity keeps a relaxed layout when enough vertical room is available", () => {
  const density = resolveWorkspaceDensity({
    viewportHeight: 1240,
    workspaceHeight: 860,
  });

  assert.equal(density, "relaxed");
});

test("resolveWorkspaceDensity switches to compact when the usable workspace is tight", () => {
  const density = resolveWorkspaceDensity({
    viewportHeight: 900,
    workspaceHeight: 620,
  });

  assert.equal(density, "compact");
});
