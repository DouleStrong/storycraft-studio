import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { buildDemoSession } from "../demo-mode.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const indexHtml = fs.readFileSync(path.join(frontendDir, "index.html"), "utf8");
const appJs = fs.readFileSync(path.join(frontendDir, "app.js"), "utf8");
const stylesCss = fs.readFileSync(path.join(frontendDir, "styles.css"), "utf8");

function extractFunctionSource(source, functionName) {
  const start = source.indexOf(`function ${functionName}`);
  assert.notEqual(start, -1, `${functionName} should exist`);

  const bodyStart = source.indexOf("{", start);
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    const char = source[index];
    if (char === "{") {
      depth += 1;
    }
    if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        return source.slice(start, index + 1);
      }
    }
  }

  throw new Error(`Could not extract ${functionName}`);
}

function extractCssRule(source, selector) {
  const start = source.indexOf(`${selector} {`);
  assert.notEqual(start, -1, `${selector} should exist`);

  const bodyStart = source.indexOf("{", start);
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    const char = source[index];
    if (char === "{") {
      depth += 1;
    }
    if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        return source.slice(start, index + 1);
      }
    }
  }

  throw new Error(`Could not extract ${selector}`);
}

function extractCssRules(source, selector) {
  const rules = [];
  const rulePattern = /([^{}]+)\{([^{}]*)\}/g;
  let match;

  while ((match = rulePattern.exec(source)) !== null) {
    const selectors = match[1]
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (selectors.includes(selector)) {
      rules.push(`${match[1].trim()} {${match[2]}}`);
    }
  }

  assert.ok(rules.length > 0, `${selector} should exist`);
  return rules.join("\n");
}

function evaluateFunctions(functionNames) {
  const program = functionNames
    .map((functionName) => extractFunctionSource(appJs, functionName))
    .join("\n\n");
  return vm.runInNewContext(`${program}\n({ ${functionNames.join(", ")} });`, {});
}

function evaluateFunctionWithContext(functionName, context = {}) {
  const program = extractFunctionSource(appJs, functionName);
  return vm.runInNewContext(`${program}\n${functionName};`, context);
}

test("workspace html exposes a dedicated character chat shell", () => {
  assert.match(indexHtml, /id="characterChatShell"/);
  assert.match(indexHtml, /id="characterChatMessages"/);
  assert.match(indexHtml, /data-close-character-chat/);
});

test("workspace scripts expose character chat actions", () => {
  assert.match(appJs, /data-open-character-chat/);
  assert.match(appJs, /data-send-character-chat/);
  assert.match(appJs, /data-quick-character-reply/);
});

test("character chat renderer exposes smart NPC relationship signals", () => {
  const chatRenderer = [
    "buildCharacterQuickReplies",
    "buildCharacterSeedMessages",
    "buildDemoCharacterReply",
    "renderCharacterChat",
  ]
    .map((functionName) => extractFunctionSource(appJs, functionName))
    .join("\n");

  assert.match(chatRenderer, /npc_dialogue_profile/);
  assert.match(chatRenderer, /need_signal/);
  assert.match(chatRenderer, /relationship_hook/);
  assert.match(chatRenderer, /reaction_samples/);
  assert.match(chatRenderer, /好感/);
  assert.match(chatRenderer, /relationshipLevel/);
  assert.match(chatRenderer, /currentMood/);
  assert.match(chatRenderer, /memoryTags/);
});

test("character chat renderer mirrors the figma persona layout", () => {
  const chatRenderer = extractFunctionSource(appJs, "renderCharacterChat");

  assert.match(chatRenderer, /性格特质/);
  assert.match(chatRenderer, /当前情绪/);
  assert.match(chatRenderer, /记忆标签/);
  assert.match(chatRenderer, /互动提示/);
  assert.match(chatRenderer, /正在与你对话/);
});

test("character chat styles reserve safe avatar space and figma proportions", () => {
  assert.match(stylesCss, /\.character-chat-aside-top\s*\{[\s\S]*justify-items:\s*center/);
  assert.match(stylesCss, /\.character-chat-avatar\s*\{[\s\S]*width:\s*80px/);
  assert.match(stylesCss, /\.character-chat-avatar\s*\{[\s\S]*height:\s*80px/);
  assert.match(stylesCss, /\.character-chat-avatar\s*\{[\s\S]*flex-shrink:\s*0/);
  assert.match(stylesCss, /\.chat-message-avatar\s*\{[\s\S]*width:\s*40px/);
  assert.match(stylesCss, /\.chat-message-avatar\s*\{[\s\S]*height:\s*40px/);
});

test("buildDemoCharacterReply varies responses by player intent", () => {
  const { buildDemoCharacterReply } = evaluateFunctions(["buildDemoCharacterReply"]);
  const session = buildDemoSession();
  const mentor = session.characterLibrary.find((character) => character.id === 101);

  assert.ok(mentor, "demo mentor character should exist");

  const knowledgeReply = buildDemoCharacterReply(mentor, "我想问学院规则是怎么运作的");
  const emotionReply = buildDemoCharacterReply(mentor, "我今天有点沮丧，不知道该怎么办");
  const companionReply = buildDemoCharacterReply(mentor, "下次还能和你一起巡夜吗");

  assert.notEqual(knowledgeReply, emotionReply);
  assert.notEqual(emotionReply, companionReply);
  assert.notEqual(knowledgeReply, companionReply);
});

test("workspace includes figma-inspired navigation and stage affordances", () => {
  assert.match(indexHtml, /figma-sidebar-tabs/);
  assert.match(indexHtml, /figma-agent-tabs/);
  assert.match(appJs, /stage-mode-switcher/);
  assert.match(appJs, /figma-scene-summary/);
});

test("demo workspace exposes a figma-aligned three-column shell", () => {
  const demoRenderer = [
    "renderDemoProjectWorkspace",
    "renderDemoSidebar",
    "renderDemoMainStage",
    "renderDemoAgentPanel",
  ]
    .map((functionName) => extractFunctionSource(appJs, functionName))
    .join("\n");

  assert.match(demoRenderer, /figma-demo-workspace/);
  assert.match(demoRenderer, /figma-demo-grid/);
  assert.match(demoRenderer, /demo-sidebar/);
  assert.match(demoRenderer, /demo-main-stage/);
  assert.match(demoRenderer, /demo-ai-panel/);
  assert.match(demoRenderer, /data-demo-sidebar-tab/);
  assert.match(demoRenderer, /data-demo-agent-tab/);
});

test("demo workspace topbar, sidebar and stage use figma-like component structures", () => {
  const demoRenderer = [
    "renderDemoProjectWorkspace",
    "renderDemoSidebar",
    "renderDemoChapterList",
    "renderDemoMainStage",
    "renderDemoSceneCard",
    "renderDemoDialogueWorkbench",
  ]
    .map((functionName) => extractFunctionSource(appJs, functionName))
    .join("\n");

  assert.match(demoRenderer, /demo-toolbar-button is-primary/);
  assert.match(demoRenderer, /demo-toolbar-button demo-toolbar-ghost/);
  assert.match(demoRenderer, /demo-square-button/);
  assert.match(demoRenderer, /demo-chapter-card/);
  assert.match(demoRenderer, /demo-chapter-hero-summary/);
  assert.match(demoRenderer, /demo-scene-card-head/);
  assert.match(demoRenderer, /demo-scene-card-status/);
  assert.match(demoRenderer, /demo-main-stage-shell/);
  assert.match(demoRenderer, /demo-dialogue-workbench/);
});

test("demo main stage keeps scene cards compact by default", () => {
  const mainStageRenderer = extractFunctionSource(appJs, "renderDemoMainStage");

  assert.doesNotMatch(mainStageRenderer, /state\.demoExpandedSceneId = chapter\.scenes\[0\]\.id/);
});

test("scene cards no longer inline-render the dialogue preview card", () => {
  const sceneCardRenderer = extractFunctionSource(appJs, "renderDemoSceneCard");

  assert.doesNotMatch(sceneCardRenderer, /demo-dialogue-preview/);
});

test("demo interactions toggle scene expansion instead of forcing a permanent selection", () => {
  assert.match(appJs, /state\.demoExpandedSceneId = state\.demoExpandedSceneId === Number\(dataset\.demoExpandScene\) \? null : Number\(dataset\.demoExpandScene\);/);
  assert.doesNotMatch(appJs, /state\.demoExpandedSceneId = getActiveChapter\(\)\?\.scenes\?\.\[0\]\?\.id \|\| null;/);
});

test("scene readiness stays completed even when chapter review is pending", () => {
  const getDemoSceneStatus = evaluateFunctionWithContext("getDemoSceneStatus", {
    findPendingIntervention: () => ({ id: 1 }),
  });

  const result = getDemoSceneStatus(
    {
      id: 1,
      dialogue_blocks: [{ id: 10 }],
    },
    {
      scenes: [{ id: 1 }],
    },
  );

  assert.equal(result.label, "已完成");
  assert.equal(result.className, "is-live");
});

test("demo agent panel uses a compact figma-like task row structure", () => {
  const agentRenderer = extractFunctionSource(appJs, "renderDemoAgentPanel");

  assert.match(agentRenderer, /demo-task-card-head/);
  assert.match(agentRenderer, /demo-task-status/);
  assert.match(agentRenderer, /demo-task-summary/);
  assert.match(agentRenderer, /demo-review-card-head/);
});

test("demo agent panel uses subdued figma-like status treatments", () => {
  const agentRenderer = extractFunctionSource(appJs, "renderDemoAgentPanel");

  assert.match(agentRenderer, /demo-agent-tab-icon/);
  assert.match(agentRenderer, /demo-agent-count-badge/);
  assert.match(agentRenderer, /demo-task-status is-subtle/);
  assert.doesNotMatch(agentRenderer, /<span aria-hidden="true">AI<\/span>/);
  assert.doesNotMatch(agentRenderer, /<span aria-hidden="true">\$\{escapeHtml\(reviewerItems\.length\)\}<\/span>/);
});

test("demo agent panel keeps the figma full-width tab rail", () => {
  const agentTabs = extractCssRules(stylesCss, ".demo-agent-tabs");
  const aiScroll = extractCssRules(stylesCss, ".demo-ai-scroll");
  const activeAgentTab = extractCssRules(stylesCss, ".demo-agent-tabs button.is-active");

  assert.doesNotMatch(agentTabs, /padding-inline:\s*20px/);
  assert.doesNotMatch(agentTabs, /margin:\s*-16px -16px 0/);
  assert.match(agentTabs, /margin:\s*0/);
  assert.match(agentTabs, /width:\s*100%/);
  assert.match(agentTabs, /grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
  assert.match(aiScroll, /padding:\s*16px/);
  assert.match(activeAgentTab, /border-bottom-color:\s*#7c3aed/);
  assert.doesNotMatch(stylesCss, /\.demo-agent-tabs button\.is-active::after\s*\{/);
  assert.match(stylesCss, /\.demo-task-card\.is-focus \.demo-task-status\.is-subtle\s*\{[\s\S]*color:\s*#6b7280/);
});

test("demo controls lock to figma-rendered button widths", () => {
  const toolbarButton = extractCssRule(stylesCss, ".demo-toolbar-button");
  const squareButton = extractCssRule(stylesCss, ".demo-square-button");
  const sidebarTabs = extractCssRules(stylesCss, ".demo-sidebar-tabs");
  const sidebarScroll = extractCssRules(stylesCss, ".demo-sidebar-scroll");

  assert.match(stylesCss, /\.demo-toolbar-button,\s*\n\.demo-square-button,\s*\n\.demo-readonly-pill\s*\{[\s\S]*min-height:\s*36px/);
  assert.match(toolbarButton, /padding:\s*0 16px/);
  assert.match(squareButton, /width:\s*36px/);
  assert.match(squareButton, /height:\s*36px/);
  assert.match(sidebarTabs, /grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/);
  assert.match(sidebarScroll, /padding:\s*16px/);
  assert.match(stylesCss, /\.demo-list-card\s*\{[\s\S]*width:\s*100%/);
  assert.match(stylesCss, /\.demo-task-card\s*\{[\s\S]*width:\s*100%/);
});

test("demo stage controls use figma compact horizontal sizing", () => {
  const heroActionButton = extractCssRule(stylesCss, ".demo-hero-action-button");
  const modeSwitcher = extractCssRule(stylesCss, ".stage-mode-switcher");
  const modePill = extractCssRule(stylesCss, ".stage-mode-pill");

  assert.match(heroActionButton, /min-height:\s*36px/);
  assert.match(heroActionButton, /padding:\s*0 16px/);
  assert.match(heroActionButton, /width:\s*auto/);
  assert.doesNotMatch(heroActionButton, /width:\s*110px/);
  assert.doesNotMatch(heroActionButton, /flex-direction:\s*column/);
  assert.match(modeSwitcher, /display:\s*flex/);
  assert.match(modeSwitcher, /gap:\s*8px/);
  assert.doesNotMatch(modeSwitcher, /padding:\s*4px/);
  assert.match(modePill, /min-height:\s*32px/);
  assert.match(modePill, /padding:\s*0 12px/);
});

test("demo agent panel prioritizes active focus tasks ahead of completed exports", () => {
  const renderDemoAgentPanel = evaluateFunctionWithContext("renderDemoAgentPanel", {
    state: {
      demoAgentTab: "agent",
      selectedJobDetail: null,
      activeChapterId: 6101,
    },
    buildAgentWorkbench: () => ({
      history: [
        {
          jobId: 8301,
          title: "导出作品包",
          summary: "PDF 与 DOCX 已通过交付质检，可用于策划评审与配音同步。",
          progressLabel: "100%",
          tone: "success",
          status: "completed",
          chapterLabel: "",
          currentStepLabel: "",
          isSelected: false,
          isFocus: false,
        },
        {
          jobId: 9102,
          title: "场景结构生成",
          summary: "已定位到 Scene 1 前两段说明过载，建议改为导师与精灵的短对话配合。",
          progressLabel: "100%",
          tone: "warn",
          status: "awaiting_user",
          chapterLabel: "第 1 章 · 入学试炼",
          currentStepLabel: "等待你确认",
          isSelected: true,
          isFocus: true,
        },
      ],
      focus: {},
    }),
    formatInterventionLabel: (value) => String(value || ""),
    getActiveChapter: () => ({ order_index: 1 }),
    renderDemoIcon: () => "",
    escapeHtml: (value) => String(value ?? ""),
  });

  const rendered = renderDemoAgentPanel({ jobs: [], chapters: [] });

  assert.ok(rendered.indexOf("场景结构生成") < rendered.indexOf("导出作品包"));
});

test("demo workspace removes old backend-only controls from the showcase renderer", () => {
  const demoRenderer = extractFunctionSource(appJs, "renderDemoProjectWorkspace");

  assert.doesNotMatch(demoRenderer, /data-generate-draft/);
  assert.doesNotMatch(demoRenderer, /data-lock-chapter/);
  assert.doesNotMatch(demoRenderer, /data-restore-revision/);
  assert.doesNotMatch(demoRenderer, /data-delete-export/);
  assert.doesNotMatch(demoRenderer, /data-detach-character/);
});

test("demo styles lock to the figma column dimensions", () => {
  assert.match(stylesCss, /\.figma-demo-grid\s*\{[\s\S]*grid-template-columns:\s*320px minmax\(0,\s*1fr\) 384px/);
  assert.match(stylesCss, /\.figma-demo-topbar\s*\{[\s\S]*height:\s*64px/);
  assert.match(stylesCss, /\.demo-task-card-head\s*\{/);
  assert.match(stylesCss, /\.demo-task-status\s*\{/);
  assert.match(stylesCss, /\.demo-agent-tab-icon\s*\{/);
  assert.match(stylesCss, /\.demo-agent-count-badge\s*\{/);
  assert.match(stylesCss, /\.demo-task-status\.is-subtle\s*\{/);
  assert.match(stylesCss, /\.demo-toolbar-ghost\s*\{/);
  assert.match(stylesCss, /\.demo-chapter-hero-summary\s*\{/);
  assert.match(stylesCss, /\.demo-scene-card-head\s*\{/);
  assert.match(stylesCss, /\.demo-scene-card-status\s*\{/);
  assert.match(stylesCss, /\.demo-main-stage-shell\s*\{/);
  assert.match(stylesCss, /\.demo-dialogue-workbench\s*\{/);
});
