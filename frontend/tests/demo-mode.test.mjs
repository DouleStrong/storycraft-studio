import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildDemoSession,
  getDemoBannerLabel,
  isDemoModeEnabled,
  resolveDemoInitialRoute,
  resolveDemoInitialView,
} from "../demo-mode.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const indexHtml = fs.readFileSync(path.join(frontendDir, "index.html"), "utf8");
const stylesCss = fs.readFileSync(path.join(frontendDir, "styles.css"), "utf8");

test("isDemoModeEnabled returns true when the url enables demo mode", () => {
  assert.equal(isDemoModeEnabled("https://example.com/?demo=1"), true);
  assert.equal(isDemoModeEnabled("https://example.com/?demo=true"), true);
  assert.equal(isDemoModeEnabled("https://example.com/?demo=showcase"), true);
});

test("isDemoModeEnabled returns false when demo mode is absent", () => {
  assert.equal(isDemoModeEnabled("https://example.com/"), false);
  assert.equal(isDemoModeEnabled("https://example.com/?demo=0"), false);
});

test("buildDemoSession returns a ready-to-show workspace session", () => {
  const session = buildDemoSession();

  assert.equal(session.token, "demo-token");
  assert.equal(session.user.pen_name, "作品集访客");
  assert.ok(session.projects.length >= 1);
  assert.ok(session.characterLibrary.length >= 2);
  assert.equal(session.currentProjectId, session.currentProject.id);
  assert.ok(session.currentProject.chapters.length >= 2);
  assert.equal(session.activeChapterId, session.currentProject.chapters[0].id);
});

test("demo characters include friendship-style NPC chat samples", () => {
  const session = buildDemoSession();

  for (const character of session.characterLibrary) {
    assert.ok(character.status, `${character.name} should expose interactive status`);
    assert.ok(character.relationship, `${character.name} should expose relationship label`);
    assert.equal(typeof character.relationshipLevel, "number", `${character.name} should expose relationship progress`);
    assert.ok(character.currentMood, `${character.name} should expose current mood`);
    assert.ok(character.memoryTags.length >= 2, `${character.name} should expose memory tags`);
    assert.ok(character.npc_dialogue_profile, `${character.name} should include a chat profile`);
    assert.ok(character.npc_dialogue_profile.need_signal, `${character.name} should expose a need signal`);
    assert.ok(character.npc_dialogue_profile.relationship_hook, `${character.name} should expose a relationship hook`);
    assert.ok(character.npc_dialogue_profile.opening_line, `${character.name} should expose an opening line`);
    assert.ok(character.npc_dialogue_profile.smart_replies.length >= 3, `${character.name} should expose quick replies`);
    assert.ok(character.npc_dialogue_profile.reaction_samples.length >= 2, `${character.name} should expose reaction samples`);
  }
});

test("resolveDemoInitialView prefers workspace when demo data is ready", () => {
  const session = buildDemoSession();

  assert.equal(resolveDemoInitialView(session), "workspace");
  assert.equal(resolveDemoInitialView({ ...session, currentProject: null }), "dashboard");
});

test("resolveDemoInitialRoute opens the ready workspace project", () => {
  const session = buildDemoSession();

  assert.deepEqual(resolveDemoInitialRoute(session), {
    view: "workspace",
    projectId: session.currentProjectId,
  });
  assert.deepEqual(resolveDemoInitialRoute({ ...session, currentProject: null, currentProjectId: null }), {
    view: "dashboard",
    projectId: null,
  });
});

test("getDemoBannerLabel exposes the showcase status copy", () => {
  assert.match(getDemoBannerLabel(), /Demo/);
  assert.match(getDemoBannerLabel(), /展示/);
});

test("index has a module-free demo boot fallback instead of exposing login first", () => {
  assert.match(indexHtml, /data-demo-boot/);
  assert.match(indexHtml, /data-demo-protocol/);
  assert.match(indexHtml, /demoBootFallback/);
  assert.match(indexHtml, /URLSearchParams\(window\.location\.search\)/);
  assert.match(indexHtml, /window\.location\.protocol === "file:"/);
  assert.match(indexHtml, /authPanel\.classList\.add\("hidden"\)/);
  assert.match(indexHtml, /http:\/\/127\.0\.0\.1:5500\/index\.html\?demo=1/);
  assert.match(indexHtml, /python -m http\.server 5500/);
  assert.match(stylesCss, /body\[data-demo-boot="pending"\]\s+\.auth-panel/);
  assert.match(stylesCss, /body\[data-demo-boot="pending"\]\s+#demoBootFallback/);
});
