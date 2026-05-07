import { getAuthErrorFeedback, getAuthValidationMessage, validateAuthFields } from "./auth-feedback.mjs";
import {
  buildProjectDuplicatePayload,
  buildSnapshotPayload,
  buildStoryBiblePayload,
  countProtectedContent,
} from "./authoring-controls.mjs";
import { buildAgentWorkbench } from "./agent-workbench.mjs";
import { buildExportDeliveryCenter } from "./export-center.mjs";
import { withSubmitForm } from "./form-utils.mjs";
import { describeReadyExport } from "./export-feedback.mjs";
import { buildIllustrationRequestPayload, resolveFeaturedIllustration } from "./illustration-workbench.mjs";
import { describeJobFeedback } from "./job-feedback.mjs";
import { captureScrollState, restoreScrollState } from "./scroll-state.mjs";
import { buildStoryBibleWorkbench } from "./story-bible-workbench.mjs";
import { resolveWorkflowProgress } from "./workflow-progress.mjs";
import { computeWorkspaceHeight, resolveWorkspaceDensity } from "./workspace-layout.mjs";
import {
  buildDemoSession,
  getDemoBannerLabel,
  getDemoReadOnlyMessage,
  isDemoModeEnabled,
  resolveDemoInitialRoute,
  resolveDemoApiResponse,
  resolveDemoInitialView,
} from "./demo-mode.mjs";
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
} from "./studio-state.mjs";

const state = {
  token: localStorage.getItem("storycraft_token") || "",
  user: JSON.parse(localStorage.getItem("storycraft_user") || "null"),
  authMode: "register",
  view: "dashboard",
  projects: [],
  characterLibrary: [],
  currentProjectId: null,
  currentProject: null,
  activeChapterId: null,
  selectedJobId: null,
  selectedJobDetail: null,
  featuredExportId: null,
  exportNotice: null,
  activeJobs: new Set(),
  pollHandle: null,
  interventionDrafts: {},
  layoutMode: "wide",
  layoutObserver: null,
  jobStreamController: null,
  streamingJobId: null,
  characterModalMode: "create",
  illustrationWorkbench: {},
  storyBibleRevisions: [],
  storyBibleDiffs: {},
  activeStoryBibleDiffId: null,
  chapterRevisions: {},
  chapterRevisionDiffs: {},
  activeChapterRevisionDiffId: null,
  blockDrafts: {},
  sceneDrafts: {},
  dialogueDrafts: {},
  activeCharacterChatId: null,
  characterChatDraft: "",
  characterChatMessages: {},
  demoSidebarTab: "chapters",
  demoAgentTab: "agent",
  demoExpandedSceneId: null,
  demoStageMode: "default",
};

const demoSession = isDemoModeEnabled(window.location.href) ? buildDemoSession() : null;

if (demoSession) {
  state.token = demoSession.token;
  state.user = demoSession.user;
  state.projects = demoSession.projects;
  state.characterLibrary = demoSession.characterLibrary;
  state.currentProjectId = demoSession.currentProjectId;
  state.currentProject = demoSession.currentProject;
  state.activeChapterId = demoSession.activeChapterId;
  state.selectedJobId = demoSession.selectedJobId;
  state.selectedJobDetail = demoSession.selectedJobDetail;
  state.exportNotice = demoSession.exportNotice;
  state.featuredExportId = demoSession.featuredExportId;
  state.storyBibleRevisions = demoSession.storyBibleRevisions;
  state.storyBibleDiffs = demoSession.storyBibleDiffsByProjectId?.[String(demoSession.currentProjectId)] || {};
  state.chapterRevisions = demoSession.chapterRevisionsByChapterId || {};
  state.chapterRevisionDiffs = demoSession.chapterRevisionDiffsByChapterId || {};
  state.view = resolveDemoInitialView(demoSession);
}

const els = {
  appShell: document.querySelector(".app-shell"),
  authPanel: document.getElementById("authPanel"),
  dashboardShell: document.getElementById("dashboardShell"),
  workspaceShell: document.getElementById("workspaceShell"),
  authForm: document.getElementById("authForm"),
  authSubmitButton: document.getElementById("authSubmitButton"),
  authFeedback: document.getElementById("authFeedback"),
  authEmail: document.getElementById("authEmail"),
  authPassword: document.getElementById("authPassword"),
  authPenName: document.getElementById("authPenName"),
  penNameField: document.getElementById("penNameField"),
  sessionBadge: document.getElementById("sessionBadge"),
  newCharacterButton: document.getElementById("newCharacterButton"),
  logoutButton: document.getElementById("logoutButton"),
  projectForm: document.getElementById("projectForm"),
  projectList: document.getElementById("projectList"),
  dashboardMetrics: document.getElementById("dashboardMetrics"),
  dashboardLibrarySummary: document.getElementById("dashboardLibrarySummary"),
  backToDashboardButton: document.getElementById("backToDashboardButton"),
  returnToDashboardButton: document.getElementById("returnToDashboardButton"),
  refreshWorkspaceButton: document.getElementById("refreshWorkspaceButton"),
  workspaceHeading: document.getElementById("workspaceHeading"),
  exportReadyBanner: document.getElementById("exportReadyBanner"),
  workspaceGrid: document.querySelector(".workspace-grid"),
  projectHero: document.getElementById("projectHero"),
  projectHeroMeta: document.getElementById("projectHeroMeta"),
  deleteProjectButton: document.getElementById("deleteProjectButton"),
  openStoryBibleButton: document.getElementById("openStoryBibleButton"),
  storyBiblePanel: document.getElementById("storyBiblePanel"),
  projectWorkspace: document.getElementById("projectWorkspace"),
  characterPanelScroll: document.getElementById("characterPanelScroll"),
  agentPanel: document.querySelector(".agent-panel"),
  agentFocus: document.getElementById("agentFocus"),
  emptyState: document.getElementById("emptyState"),
  characterLibrarySummary: document.getElementById("characterLibrarySummary"),
  openCharacterLibraryButton: document.getElementById("openCharacterLibraryButton"),
  characterList: document.getElementById("characterList"),
  characterModal: document.getElementById("characterModal"),
  closeCharacterModalButton: document.getElementById("closeCharacterModalButton"),
  storyBibleModal: document.getElementById("storyBibleModal"),
  closeStoryBibleModalButton: document.getElementById("closeStoryBibleModalButton"),
  storyBibleDetail: document.getElementById("storyBibleDetail"),
  characterCreatePane: document.getElementById("characterCreatePane"),
  characterLibraryPane: document.getElementById("characterLibraryPane"),
  characterCreateHint: document.getElementById("characterCreateHint"),
  characterCreateForm: document.getElementById("characterCreateForm"),
  attachCharacterToProject: document.getElementById("attachCharacterToProject"),
  attachCharacterLabel: document.getElementById("attachCharacterLabel"),
  characterLibraryHint: document.getElementById("characterLibraryHint"),
  characterLibraryList: document.getElementById("characterLibraryList"),
  chapterTabs: document.getElementById("chapterTabs"),
  chapterDetail: document.getElementById("chapterDetail"),
  chapterPager: document.getElementById("chapterPager"),
  jobList: document.getElementById("jobList"),
  jobTrace: document.getElementById("jobTrace"),
  exportList: document.getElementById("exportList"),
  generateOutlineButton: document.getElementById("generateOutlineButton"),
  createSnapshotButton: document.getElementById("createSnapshotButton"),
  duplicateProjectButton: document.getElementById("duplicateProjectButton"),
  exportBundleButton: document.getElementById("exportBundleButton"),
  refreshProjectsButton: document.getElementById("refreshProjectsButton"),
  characterChatShell: document.getElementById("characterChatShell"),
  characterChatAside: document.getElementById("characterChatAside"),
  characterChatHeader: document.getElementById("characterChatHeader"),
  characterChatMessages: document.getElementById("characterChatMessages"),
  characterChatQuickReplies: document.getElementById("characterChatQuickReplies"),
  characterChatForm: document.getElementById("characterChatForm"),
  characterChatInput: document.getElementById("characterChatInput"),
  toast: document.getElementById("toast"),
};

const authTabButtons = [...document.querySelectorAll("[data-auth-mode]")];
const characterModalTabButtons = [...document.querySelectorAll("[data-character-modal-tab]")];

function applyWorkspaceMode(width) {
  const nextMode = resolveWorkspaceMode(width);
  state.layoutMode = nextMode;
  els.projectWorkspace.dataset.layoutMode = nextMode;
}

function syncWorkspaceMetrics() {
  if (!els.projectWorkspace || !els.workspaceGrid || !els.appShell) {
    return;
  }

  if (demoSession) {
    els.projectWorkspace.style.removeProperty("--workspace-grid-height");
    els.projectWorkspace.dataset.density = "relaxed";
    return;
  }

  if (!state.currentProject || state.view !== "workspace" || state.layoutMode === "stacked") {
    els.projectWorkspace.style.removeProperty("--workspace-grid-height");
    els.projectWorkspace.dataset.density = "relaxed";
    return;
  }

  const viewportHeight = window.visualViewport?.height || window.innerHeight || document.documentElement.clientHeight;
  const gridTop = els.workspaceGrid.getBoundingClientRect().top;
  const appShellStyles = window.getComputedStyle(els.appShell);
  const bottomOffset = parseFloat(appShellStyles.paddingBottom || "0") + 12;
  const workspaceHeight = computeWorkspaceHeight({
    viewportHeight,
    gridTop,
    bottomOffset,
  });
  els.projectWorkspace.style.setProperty("--workspace-grid-height", `${workspaceHeight}px`);
  els.projectWorkspace.dataset.density = resolveWorkspaceDensity({
    viewportHeight,
    workspaceHeight,
  });
}

function syncWorkspaceMode() {
  const width = els.projectWorkspace?.getBoundingClientRect().width || window.innerWidth;
  applyWorkspaceMode(width);
  syncWorkspaceMetrics();
}

function ensureWorkspaceObserver() {
  if (state.layoutObserver || !els.projectWorkspace || typeof ResizeObserver === "undefined") {
    return;
  }

  state.layoutObserver = new ResizeObserver((entries) => {
    const entry = entries[0];
    if (!entry) {
      return;
    }
    applyWorkspaceMode(entry.contentRect.width);
    syncWorkspaceMetrics();
  });
  state.layoutObserver.observe(els.projectWorkspace);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatDiffStatus(status) {
  return (
    {
      changed: "已变更",
      added: "新增",
      removed: "移除",
      unchanged: "未变化",
    }[String(status || "")] || "变化"
  );
}

function renderWorkflowStageRail(job) {
  const progress = resolveWorkflowProgress(job);
  return `
    <div class="workflow-stage-rail" aria-label="任务阶段进度">
      ${progress.stages
        .map(
          (stage) => `
            <article class="workflow-stage-pill is-${stage.state}">
              <span class="workflow-stage-dot" aria-hidden="true"></span>
              <div>
                <strong>${escapeHtml(stage.label)}</strong>
                <span>${escapeHtml(
                  {
                    done: "已完成",
                    active: "进行中",
                    awaiting_user: "等待确认",
                    failed: "失败",
                    skipped: "跳过",
                    pending: "待执行",
                  }[stage.state] || "待执行",
                )}</span>
              </div>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderStoryBibleRevisionDiff(diff) {
  if (!diff) {
    return "";
  }
  return `
    <article class="revision-diff-card">
      <div class="revision-diff-head">
        <div>
          <p class="eyebrow">设定差异</p>
          <h5>${escapeHtml(diff.base_revision?.revision_index ? `版本 #${diff.base_revision.revision_index}` : "当前设定")} 对比 ${escapeHtml(
            diff.target_revision?.revision_index ? `版本 #${diff.target_revision.revision_index}` : `版本 #${diff.target_revision?.id || ""}`,
          )}</h5>
        </div>
        <span class="status-chip">${escapeHtml(diff.summary?.changed_field_count || 0)} 项变化</span>
      </div>
      <div class="revision-diff-list">
        ${(diff.fields || [])
          .filter((field) => field.changed)
          .map(
            (field) => `
              <article class="revision-diff-row">
                <div class="revision-diff-row-head">
                  <strong>${escapeHtml(field.label)}</strong>
                  <span class="mini-chip is-warn">${escapeHtml(formatDiffStatus("changed"))}</span>
                </div>
                <div class="revision-diff-columns">
                  <div class="revision-diff-column">
                    <span class="eyebrow">当前</span>
                    <p>${escapeHtml(field.base_excerpt || "空")}</p>
                  </div>
                  <div class="revision-diff-column">
                    <span class="eyebrow">所选版本</span>
                    <p>${escapeHtml(field.target_excerpt || "空")}</p>
                    ${
                      field.added?.length || field.removed?.length
                        ? `<div class="chip-row">
                            ${field.added?.length ? `<span class="mini-chip is-live">新增 ${escapeHtml(field.added.join(" / "))}</span>` : ""}
                            ${field.removed?.length ? `<span class="mini-chip">移除 ${escapeHtml(field.removed.join(" / "))}</span>` : ""}
                          </div>`
                        : ""
                    }
                  </div>
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    </article>
  `;
}

function renderStoryBibleDetailMarkup(project, workbench, activeStoryBibleDiff) {
  const currentRevision = workbench.detail.currentRevision;
  const revisionCards = state.storyBibleRevisions.length
    ? state.storyBibleRevisions
        .slice(0, 6)
        .map(
          (revision) => `
            <article class="revision-card ${currentRevision?.id === revision.id ? "is-current" : ""}">
              <div class="revision-card-head">
                <strong>设定版本 #${escapeHtml(revision.revision_index || revision.id)}</strong>
                <span class="mini-chip">${escapeHtml(revision.created_by || "system")}</span>
              </div>
              <p class="muted">${escapeHtml(revision.created_at ? new Date(revision.created_at).toLocaleString() : "刚刚")}</p>
              <div class="inline-actions">
                <button class="ghost-button" type="button" data-view-story-bible-diff="${revision.id}">
                  ${state.activeStoryBibleDiffId === revision.id ? "收起差异" : "查看差异"}
                </button>
              </div>
            </article>
          `,
        )
        .join("")
    : `<p class="muted">当前还没有设定修订历史。</p>`;

  return `
    <div class="story-bible-detail-shell">
      <section class="story-bible-meta story-bible-detail-meta">
        <div class="chip-row">
          <span class="status-chip">${escapeHtml(workbench.summary.currentRevisionLabel)}</span>
          <span class="mini-chip">${escapeHtml(workbench.summary.targetChapterLabel)}</span>
          <span class="mini-chip">${escapeHtml(workbench.summary.targetLengthLabel)}</span>
          <span class="mini-chip">${escapeHtml(workbench.summary.ruleCountLabel)}</span>
        </div>
        <p class="muted">${escapeHtml(workbench.summary.helperText)}</p>
      </section>

      <div class="story-bible-detail-layout">
        <form id="storyBibleForm" class="stack-form compact story-bible-form story-bible-detail-form">
          <label>
            <span>世界观</span>
            <textarea name="world_notes" rows="4">${escapeHtml(workbench.detail.worldNotes)}</textarea>
          </label>
          <label>
            <span>风格说明</span>
            <textarea name="style_notes" rows="4">${escapeHtml(workbench.detail.styleNotes)}</textarea>
          </label>
          <label>
            <span>写作禁忌 / 规则</span>
            <textarea name="writing_rules_text" rows="5" placeholder="一行一条规则">${escapeHtml(workbench.detail.writingRulesText)}</textarea>
          </label>
          <label>
            <span>称呼规则</span>
            <textarea name="addressing_rules" rows="3">${escapeHtml(workbench.detail.addressingRules)}</textarea>
          </label>
          <label>
            <span>时间线约束</span>
            <textarea name="timeline_rules" rows="3">${escapeHtml(workbench.detail.timelineRules)}</textarea>
          </label>
          <div class="inline-actions">
            <button class="primary-button" type="submit">保存设定版本</button>
          </div>
        </form>

        <section class="revision-list story-bible-detail-history">
          <div class="section-heading compact">
            <h5>最近设定版本</h5>
          </div>
          ${revisionCards}
          ${renderStoryBibleRevisionDiff(activeStoryBibleDiff)}
        </section>
      </div>
    </div>
  `;
}

function renderChapterRevisionDiff(diff) {
  if (!diff) {
    return "";
  }
  const overview = diff.overview || {};
  const narrativeOverview = overview.narrative_blocks || {};
  const sceneOverview = overview.scenes || {};
  return `
    <article class="revision-diff-card">
      <div class="revision-diff-head">
        <div>
          <p class="eyebrow">版本差异</p>
          <h5>${escapeHtml(diff.base?.label || "当前章节")} 对比 ${escapeHtml(diff.target?.label || "历史版本")}</h5>
        </div>
        <div class="chip-row">
          <span class="mini-chip">${escapeHtml(narrativeOverview.changed || 0)} 处正文变化</span>
          <span class="mini-chip">${escapeHtml(sceneOverview.changed || 0)} 处场景变化</span>
        </div>
      </div>
      <div class="revision-diff-overview">
        <span class="mini-chip">正文增减 ${escapeHtml((narrativeOverview.added || 0) + (narrativeOverview.removed || 0))} 处</span>
        <span class="mini-chip">场景增减 ${escapeHtml((sceneOverview.added || 0) + (sceneOverview.removed || 0))} 处</span>
        <span class="mini-chip">Meta 变化 ${escapeHtml(overview.meta_change_count || 0)} 项</span>
        <span class="mini-chip">对白差异 ${escapeHtml(overview.dialogue_count_delta || 0)} 处</span>
      </div>
      ${
        diff.meta_changes?.length
          ? `
              <section class="revision-diff-list">
                <div class="section-heading compact">
                  <h5>章节字段变化</h5>
                </div>
                ${diff.meta_changes
                  .map(
                    (change) => `
                      <article class="revision-diff-row">
                        <div class="revision-diff-row-head">
                          <strong>${escapeHtml(change.label)}</strong>
                          <span class="mini-chip is-warn">${escapeHtml(formatDiffStatus(change.status))}</span>
                        </div>
                        <div class="revision-diff-columns">
                          <div class="revision-diff-column">
                            <span class="eyebrow">当前</span>
                            <p>${escapeHtml(change.base_excerpt || "空")}</p>
                          </div>
                          <div class="revision-diff-column">
                            <span class="eyebrow">所选版本</span>
                            <p>${escapeHtml(change.target_excerpt || "空")}</p>
                          </div>
                        </div>
                      </article>
                    `,
                  )
                  .join("")}
              </section>
            `
          : ""
      }
      ${
        diff.narrative_block_changes?.length
          ? `
              <section class="revision-diff-list">
                <div class="section-heading compact">
                  <h5>正文块变化</h5>
                </div>
                ${diff.narrative_block_changes
                  .slice(0, 6)
                  .map(
                    (change) => `
                      <article class="revision-diff-row">
                        <div class="revision-diff-row-head">
                          <strong>正文块 ${escapeHtml(change.order_index)}</strong>
                          <span class="mini-chip ${change.status === "added" ? "is-live" : change.status === "removed" ? "" : "is-warn"}">
                            ${escapeHtml(formatDiffStatus(change.status))}
                          </span>
                        </div>
                        <div class="revision-diff-columns">
                          <div class="revision-diff-column">
                            <span class="eyebrow">当前</span>
                            <p>${escapeHtml(change.base_excerpt || "空")}</p>
                          </div>
                          <div class="revision-diff-column">
                            <span class="eyebrow">所选版本</span>
                            <p>${escapeHtml(change.target_excerpt || "空")}</p>
                          </div>
                        </div>
                      </article>
                    `,
                  )
                  .join("")}
              </section>
            `
          : ""
      }
      ${
        diff.scene_changes?.length
          ? `
              <section class="revision-diff-list">
                <div class="section-heading compact">
                  <h5>Scene 变化</h5>
                </div>
                ${diff.scene_changes
                  .slice(0, 4)
                  .map(
                    (change) => `
                      <article class="revision-diff-row">
                        <div class="revision-diff-row-head">
                          <strong>Scene ${escapeHtml(change.order_index)} · ${escapeHtml(change.base_title || change.target_title || "未命名场景")}</strong>
                          <span class="mini-chip ${change.status === "added" ? "is-live" : change.status === "removed" ? "" : "is-warn"}">
                            ${escapeHtml(formatDiffStatus(change.status))}
                          </span>
                        </div>
                        <div class="revision-diff-columns">
                          <div class="revision-diff-column">
                            <span class="eyebrow">当前</span>
                            <p>${escapeHtml(change.base_excerpt || "空")}</p>
                          </div>
                          <div class="revision-diff-column">
                            <span class="eyebrow">所选版本</span>
                            <p>${escapeHtml(change.target_excerpt || "空")}</p>
                          </div>
                        </div>
                      </article>
                    `,
                  )
                  .join("")}
              </section>
            `
          : ""
      }
    </article>
  `;
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => {
    els.toast.classList.add("hidden");
  }, 2600);
}

function clearExportNotice() {
  state.exportNotice = null;
}

async function setExportNotice(exportId, projectId = state.currentProjectId) {
  const bundle = await api(`/api/exports/${exportId}`);
  const readyExport = describeReadyExport(bundle);
  if (!readyExport) {
    return;
  }
  state.exportNotice = {
    projectId: Number(projectId),
    bundle,
  };
  state.featuredExportId = Number(bundle.id);
}

function showDemoReadOnlyToast() {
  showToast(getDemoReadOnlyMessage());
}

function clearAuthFeedback() {
  els.authFeedback.textContent = "";
  els.authFeedback.classList.add("hidden");
  els.authFeedback.classList.remove("is-warn");
}

function showAuthFeedback(message, tone = "error") {
  els.authFeedback.textContent = message;
  els.authFeedback.classList.remove("hidden");
  els.authFeedback.classList.toggle("is-warn", tone === "warn");
}

function setAuthSubmitBusy(isBusy) {
  els.authSubmitButton.disabled = isBusy;
  if (isBusy) {
    els.authSubmitButton.textContent = state.authMode === "login" ? "正在登录..." : "正在创建账号...";
    return;
  }
  els.authSubmitButton.textContent = state.authMode === "login" ? "登录进入工作台" : "创建账号";
}

function buildRequestHeaders(initialHeaders = {}, hasJsonBody = false) {
  const headers = new Headers(initialHeaders);
  if (!headers.has("Content-Type") && hasJsonBody) {
    headers.set("Content-Type", "application/json");
  }
  if (state.token) {
    headers.set("Authorization", `Bearer ${state.token}`);
  }
  return headers;
}

async function api(path, options = {}) {
  if (demoSession) {
    return resolveDemoApiResponse(demoSession, path, options);
  }
  const headers = buildRequestHeaders(options.headers || {}, Boolean(options.body && !(options.body instanceof FormData)));

  const response = await fetch(path, { ...options, headers });
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    throw new Error(payload.detail || payload || "请求失败");
  }
  return payload;
}

function updateProjectJobSummary(job) {
  if (!state.currentProject) {
    return;
  }
  const currentJobs = state.currentProject.jobs || [];
  const nextJobs = currentJobs.some((item) => item.id === job.id)
    ? currentJobs.map((item) => (item.id === job.id ? { ...item, ...job } : item))
    : [job, ...currentJobs];
  state.currentProject.jobs = nextJobs.sort((left, right) => right.id - left.id).slice(0, 10);
}

function getWorkspaceScrollTargets() {
  return {
    storyBiblePanel: els.storyBiblePanel,
    characterPanelScroll: els.characterPanelScroll,
    agentPanel: els.agentPanel,
    characterList: els.characterList,
    characterLibraryList: els.characterLibraryList,
    chapterTabs: els.chapterTabs,
    chapterDetail: els.chapterDetail,
    jobList: els.jobList,
    jobTrace: els.jobTrace,
  };
}

function renderWorkspaceDynamicPanels() {
  if (!state.currentProject) {
    renderProjectWorkspace();
    return;
  }

  const preservedScrollState = captureScrollState({
    storyBiblePanel: els.storyBiblePanel,
    characterPanelScroll: els.characterPanelScroll,
    chapterTabs: els.chapterTabs,
    chapterDetail: els.chapterDetail,
    agentPanel: els.agentPanel,
    jobList: els.jobList,
    jobTrace: els.jobTrace,
  });

  renderChapterTabs(state.currentProject);
  renderChapterDetail(state.currentProject);
  renderAgentFocusPanel(state.currentProject);
  renderJobList(state.currentProject);
  renderTracePanel();
  renderExports(state.currentProject);
  renderExportReadyBanner();
  window.requestAnimationFrame(syncWorkspaceMetrics);

  restoreScrollState(preservedScrollState, {
    storyBiblePanel: els.storyBiblePanel,
    characterPanelScroll: els.characterPanelScroll,
    chapterTabs: els.chapterTabs,
    chapterDetail: els.chapterDetail,
    agentPanel: els.agentPanel,
    jobList: els.jobList,
    jobTrace: els.jobTrace,
  });
}

function renderExportReadyBanner() {
  const noticeProjectId = Number(state.exportNotice?.projectId || 0);
  const bundle = state.exportNotice?.bundle || null;
  const readyExport = describeReadyExport(bundle);
  if (!state.currentProject || !readyExport || noticeProjectId !== Number(state.currentProject.id)) {
    els.exportReadyBanner.innerHTML = "";
    els.exportReadyBanner.classList.add("hidden");
    return;
  }

  els.exportReadyBanner.innerHTML = `
    <div class="export-ready-copy">
      <p class="eyebrow">导出中心</p>
      <h3>${escapeHtml(readyExport.title)}</h3>
      <p class="muted">${escapeHtml(readyExport.summary)}</p>
    </div>
    <div class="export-ready-actions">
      ${readyExport.files
        .map(
          (file) => `
            <a class="primary-button export-download-link" href="${escapeHtml(file.url)}" download>
              ${escapeHtml(file.downloadLabel)}
            </a>
          `,
        )
        .join("")}
      <button class="ghost-button" type="button" data-dismiss-export-banner="1">收起提示</button>
    </div>
  `;
  els.exportReadyBanner.classList.remove("hidden");
}

function closeJobStream(targetJobId = null) {
  if (targetJobId !== null && state.streamingJobId !== Number(targetJobId)) {
    return;
  }
  if (state.jobStreamController) {
    state.jobStreamController.abort();
  }
  state.jobStreamController = null;
  state.streamingJobId = null;
}

async function handleTerminalJob(job) {
  state.activeJobs.delete(job.id);
  closeJobStream(job.id);
  if (state.currentProjectId) {
    await loadProjectDetail(state.currentProjectId, {
      focusChapterId: job.chapter_id ?? state.activeChapterId,
      focusJobId: job.id,
    });
  }
  if (job.status === "completed" && job.job_type === "export" && job.result?.export_id) {
    try {
      await setExportNotice(job.result.export_id, job.project_id ?? state.currentProjectId);
      renderWorkspaceDynamicPanels();
    } catch {
      clearExportNotice();
      state.featuredExportId = null;
    }
  }
  const message =
    job.status === "completed"
      ? job.job_type === "export"
        ? "导出成品已就绪，可直接下载"
        : `${formatJobType(job.job_type || "")}已回填`
      : job.status === "awaiting_user"
        ? "Reviewer 已提出干预，等待你确认"
        : `任务失败：${job.error_message || "未知错误"}`;
  showToast(message);
}

async function openJobStream(jobId) {
  if (demoSession) {
    return;
  }
  const normalizedJobId = Number(jobId);
  if (!normalizedJobId || (state.streamingJobId === normalizedJobId && state.jobStreamController)) {
    return;
  }

  closeJobStream();
  const controller = new AbortController();
  state.jobStreamController = controller;
  state.streamingJobId = normalizedJobId;

  try {
    const response = await fetch(`/api/jobs/${normalizedJobId}/stream`, {
      method: "GET",
      headers: buildRequestHeaders(),
      signal: controller.signal,
    });
    if (!response.ok || !response.body) {
      const payload = response.headers.get("content-type")?.includes("application/json")
        ? await response.json()
        : await response.text();
      throw new Error(payload?.detail || payload || "实时协作流连接失败");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");

        let eventName = "message";
        const dataLines = [];
        rawEvent.split("\n").forEach((line) => {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
          }
          if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trim());
          }
        });
        if (!dataLines.length) {
          continue;
        }

        const rawData = dataLines.join("\n");
        if (eventName === "job") {
          const job = JSON.parse(rawData);
          if (state.selectedJobId === job.id) {
            state.selectedJobDetail = job;
          }
          updateProjectJobSummary(job);
          renderWorkspaceDynamicPanels();
          if (isTerminalJobStatus(job.status)) {
            await handleTerminalJob(job);
            return;
          }
        }

        if (eventName === "done") {
          return;
        }
      }
    }
  } catch (error) {
    if (controller.signal.aborted) {
      return;
    }
    closeJobStream(normalizedJobId);
    showToast(error.message || "实时协作流中断");
  }
}

function syncSelectedJobStream() {
  if (state.selectedJobDetail && !isTerminalJobStatus(state.selectedJobDetail.status)) {
    openJobStream(state.selectedJobDetail.id);
    return;
  }
  closeJobStream();
}

function setSession(user, token) {
  state.user = user;
  state.token = token;
  if (demoSession) {
    return;
  }
  localStorage.setItem("storycraft_user", JSON.stringify(user));
  localStorage.setItem("storycraft_token", token);
}

function clearSession() {
  closeJobStream();
  clearAuthFeedback();
  state.user = null;
  state.token = "";
  state.view = "dashboard";
  state.projects = [];
  state.characterLibrary = [];
  state.currentProjectId = null;
  state.currentProject = null;
  state.activeChapterId = null;
  state.selectedJobId = null;
  state.selectedJobDetail = null;
  state.activeJobs.clear();
  state.interventionDrafts = {};
  state.illustrationWorkbench = {};
  state.storyBibleRevisions = [];
  state.chapterRevisions = {};
  state.blockDrafts = {};
  state.sceneDrafts = {};
  state.dialogueDrafts = {};
  if (demoSession) {
    return;
  }
  localStorage.removeItem("storycraft_user");
  localStorage.removeItem("storycraft_token");
}

function updateAuthUI() {
  const authenticated = Boolean(state.token && state.user);
  document.body.dataset.demoMode = demoSession ? "true" : "false";
  if (demoSession) {
    document.body.removeAttribute("data-demo-boot");
  }
  els.appShell.dataset.demoMode = demoSession ? "true" : "false";
  els.authPanel.classList.toggle("hidden", authenticated);
  els.dashboardShell.classList.toggle("hidden", !authenticated || state.view !== "dashboard");
  els.workspaceShell.classList.toggle("hidden", !authenticated || state.view !== "workspace");
  els.logoutButton.classList.toggle("hidden", !authenticated);
  els.sessionBadge.classList.toggle("hidden", !authenticated);
  els.newCharacterButton.classList.toggle("hidden", !authenticated);
  els.sessionBadge.textContent = authenticated
    ? state.view === "workspace" && state.currentProject?.title
      ? `${state.user.pen_name} · ${state.currentProject.title}`
      : `${state.user.pen_name} · 项目控制台`
    : "";
}

function replaceStudioHash(view, projectId = null) {
  const nextHash = buildStudioRoute(view, projectId);
  const nextUrl = `${window.location.pathname}${window.location.search}${nextHash}`;
  window.history.replaceState(null, "", nextUrl);
}

async function navigateToDashboard(options = {}) {
  const nextHash = buildStudioRoute("dashboard");
  if (window.location.hash !== nextHash) {
    window.location.hash = nextHash;
    return;
  }
  await syncStudioRoute(options);
}

async function navigateToWorkspace(projectId, options = {}) {
  const nextHash = buildStudioRoute("workspace", projectId);
  if (window.location.hash !== nextHash) {
    window.location.hash = nextHash;
    return;
  }
  await syncStudioRoute({ ...options, forceReload: true });
}

async function syncStudioRoute(options = {}) {
  if (!state.token && !demoSession) {
    state.view = "dashboard";
    updateAuthUI();
    return;
  }

  const route = parseStudioRoute(window.location.hash);
  if (route.view === "workspace") {
    state.view = "workspace";
    updateAuthUI();
    const projectId = resolveWorkspaceProjectId(state.projects, route.projectId, state.currentProjectId ?? route.projectId);
    if (!projectId) {
      state.currentProjectId = route.projectId;
      state.currentProject = null;
      state.activeChapterId = null;
      state.selectedJobId = null;
      state.selectedJobDetail = null;
      state.storyBibleRevisions = [];
      state.chapterRevisions = {};
      renderDashboard();
      renderProjectWorkspace();
      return;
    }

    if (!options.forceReload && state.currentProject?.id === projectId) {
      renderDashboard();
      renderProjectWorkspace();
      return;
    }

    await loadProjectDetail(projectId);
    return;
  }

  state.view = "dashboard";
  state.currentProjectId = null;
  state.currentProject = null;
  state.activeChapterId = null;
  state.selectedJobId = null;
  state.selectedJobDetail = null;
  state.storyBibleRevisions = [];
  state.chapterRevisions = {};
  closeJobStream();
  renderDashboard();
  renderProjectWorkspace();
  updateAuthUI();
}

function applyDemoBadge() {
  if (!demoSession || !els.sessionBadge) {
    return;
  }
  els.sessionBadge.classList.remove("hidden");
  els.sessionBadge.dataset.demoMode = "true";
  els.sessionBadge.textContent = `${getDemoBannerLabel()} | ${state.user?.pen_name || "作品集访客"}`;
}

function setAuthMode(mode) {
  state.authMode = mode;
  clearAuthFeedback();
  setAuthSubmitBusy(false);
  authTabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.authMode === mode);
  });
  els.penNameField.classList.toggle("hidden", mode === "login");
  els.authPenName.required = mode !== "login";
  els.authSubmitButton.textContent = mode === "login" ? "登录进入工作台" : "创建账号";
}

function formatJobType(jobType) {
  return {
    outline: "章节大纲生成",
    outline_repair: "章节规划回退",
    chapter_draft: "章节正文生成",
    chapter_draft_retry: "章节正文重写",
    chapter_scenes: "场景结构生成",
    chapter_scenes_retry: "场景结构重写",
    scene_illustrations: "关键场景剧照生成",
    export: "导出作品包",
  }[jobType] || jobType;
}

function formatJobStatus(status) {
  return {
    queued: "排队中",
    processing: "处理中",
    awaiting_user: "等待你确认",
    completed: "已完成",
    failed: "失败",
  }[status] || status;
}

function formatChapterStatus(status) {
  return {
    planned: "已规划",
    drafted: "已成稿",
    scenes_ready: "场景就绪",
    needs_regeneration: "待重生",
  }[status] || status;
}

function formatInterventionAction(type) {
  return type === "fallback_planner" ? "提交规划回退" : "提交重写";
}

function formatInterventionLabel(type) {
  return type === "fallback_planner" ? "回退 Planner" : "要求 Writer 重写";
}

function setCharacterModalMode(mode) {
  state.characterModalMode = mode === "library" ? "library" : "create";
  characterModalTabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.characterModalTab === state.characterModalMode);
  });
  els.characterCreatePane.classList.toggle("hidden", state.characterModalMode !== "create");
  els.characterLibraryPane.classList.toggle("hidden", state.characterModalMode !== "library");
}

function openCharacterModal(mode = "create") {
  closeStoryBibleModal();
  setCharacterModalMode(mode);
  renderCharacterModal();
  els.characterModal.classList.remove("hidden");
}

function closeCharacterModal() {
  els.characterModal.classList.add("hidden");
}

function openStoryBibleModal() {
  if (!state.currentProject) {
    return;
  }
  closeCharacterModal();
  els.storyBibleModal.classList.remove("hidden");
}

function closeStoryBibleModal() {
  els.storyBibleModal.classList.add("hidden");
}

function renderCharacterModal() {
  const currentProject = state.currentProject;
  const projectTitle = currentProject?.title ? `《${currentProject.title}》` : "";
  const hasCurrentProject = Boolean(currentProject?.id);
  const attachLabel = hasCurrentProject
    ? `创建后加入当前作品 ${projectTitle}`
    : "当前未选中作品，仅保存到角色库";

  els.characterCreateHint.textContent = hasCurrentProject
    ? `角色会先进入全局角色库；勾选后会同步加入当前作品 ${projectTitle}。`
    : "你可以先把角色存进全局角色库，稍后再挂接到任何作品。";
  els.attachCharacterLabel.textContent = attachLabel;
  els.attachCharacterToProject.checked = hasCurrentProject;
  els.attachCharacterToProject.disabled = !hasCurrentProject;

  const { attached, available } = partitionCharacterLibrary(state.characterLibrary, currentProject);
  els.characterLibraryHint.textContent = hasCurrentProject
    ? `当前作品已加入 ${attached.length} 个角色，角色库里还有 ${available.length} 个角色可直接挂接。`
    : `当前共有 ${state.characterLibrary.length} 个角色。选择作品后，可以把角色挂接到当前故事。`;

  const renderLibraryCard = (character, attachedToProject) => `
    <article class="character-card character-library-card">
      <div class="character-library-head">
        <div>
          <p class="eyebrow">${escapeHtml(character.role)}</p>
          <h4>${escapeHtml(character.name)}</h4>
        </div>
        <div class="chip-row">
          <span class="mini-chip">${escapeHtml(`${character.linked_project_ids.length} 个作品`)}</span>
          ${attachedToProject ? `<span class="mini-chip is-live">已加入当前作品</span>` : ""}
        </div>
      </div>
      <p class="muted">${escapeHtml(character.signature_line || character.personality)}</p>
      <p class="muted">视觉锚点：${escapeHtml(character.visual_profile?.visual_anchor || "待生成")}</p>
      ${
        character.reference_images[0]
          ? `<img src="${character.reference_images[0].url}" alt="${escapeHtml(character.name)}" class="character-image" />`
          : ""
      }
      <div class="inline-actions">
        ${
          hasCurrentProject
            ? attachedToProject
              ? `<button class="ghost-button" data-detach-character="${character.id}">移出当前作品</button>`
              : `<button class="ghost-button" data-attach-character="${character.id}">加入当前作品</button>`
            : ""
        }
        <button class="ghost-button danger-button" data-delete-library-character="${character.id}">删除角色</button>
      </div>
    </article>
  `;

  if (!state.characterLibrary.length) {
    els.characterLibraryList.innerHTML = `<div class="character-card"><p class="muted">角色库还是空的。先创建一个角色，后面就能在不同作品间复用。</p></div>`;
    return;
  }

  const sections = [];
  if (attached.length) {
    sections.push(`
      <section class="character-library-section">
        <div class="section-heading"><h5>当前作品角色</h5></div>
        <div class="entity-list">${attached.map((item) => renderLibraryCard(item, true)).join("")}</div>
      </section>
    `);
  }
  if (available.length) {
    sections.push(`
      <section class="character-library-section">
        <div class="section-heading"><h5>${hasCurrentProject ? "可加入当前作品" : "角色库"}</h5></div>
        <div class="entity-list">${available.map((item) => renderLibraryCard(item, false)).join("")}</div>
      </section>
    `);
  }
  els.characterLibraryList.innerHTML = sections.join("");
}

function formatAdoptionState(stateValue) {
  return {
    proposed: "提案",
    applied: "已采纳",
    superseded: "已被替换",
    rejected: "已拒绝",
  }[stateValue] || stateValue;
}

function findChapterById(chapterId) {
  return state.currentProject?.chapters.find((chapter) => chapter.id === Number(chapterId)) || null;
}

function findSceneChapter(sceneId) {
  if (!state.currentProject) {
    return null;
  }
  return (
    state.currentProject.chapters.find((chapter) =>
      chapter.scenes.some((scene) => scene.id === Number(sceneId)),
    ) || null
  );
}

function findSceneById(sceneId) {
  if (!state.currentProject) {
    return null;
  }
  for (const chapter of state.currentProject.chapters) {
    const scene = chapter.scenes.find((item) => item.id === Number(sceneId));
    if (scene) {
      return scene;
    }
  }
  return null;
}

function findJobSummary(jobId) {
  return state.currentProject?.jobs.find((job) => job.id === Number(jobId)) || null;
}

function getActiveChapter() {
  return findChapterById(state.activeChapterId);
}

function getActiveCharacterChat() {
  if (!state.currentProject || !state.activeCharacterChatId) {
    return null;
  }
  return state.currentProject.characters.find((character) => character.id === Number(state.activeCharacterChatId)) || null;
}

function buildCharacterQuickReplies(character) {
  const fallbacks = [
    "你现在最在意什么？",
    "如果我继续推进剧情，你会怎么回应？",
    "用你的口吻介绍一下自己。",
  ];
  const profile = character.npc_dialogue_profile || {};
  const replyPool = [
    ...(profile.smart_replies || []),
    character.signature_line,
    character.goal,
    character.speech_style,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .map((value) => value.slice(0, 28));
  return [...new Set([...fallbacks, ...replyPool])].slice(0, 4);
}

function buildCharacterSeedMessages(character) {
  const profile = character.npc_dialogue_profile || {};
  const opening = profile.opening_line || character.signature_line || character.personality || "我在，继续吧。";
  const followup = profile.need_signal
    ? `我现在会观察的是：${profile.need_signal}`
    : character.goal
      ? `我当前最在意的是：${character.goal}`
      : "我会根据当前剧情给出角色化回应。";
  return [
    {
      id: `${character.id}-seed-1`,
      sender: "character",
      content: opening,
      emotion: profile.friendship_stage || "角色状态已同步",
      timestamp: "刚刚",
    },
    {
      id: `${character.id}-seed-2`,
      sender: "character",
      content: followup,
      emotion: profile.relationship_hook ? "关系判断已开启" : "个性对话模式",
      timestamp: "刚刚",
    },
  ];
}

function ensureCharacterChatMessages(character) {
  const key = String(character.id);
  if (!state.characterChatMessages[key]?.length) {
    state.characterChatMessages[key] = buildCharacterSeedMessages(character);
  }
  return state.characterChatMessages[key];
}

function buildDemoCharacterReply(character, prompt) {
  const promptText = String(prompt || "").trim();
  const profile = character.npc_dialogue_profile || {};
  if (!promptText) {
    return `${character.name}：你可以说得再具体一点，我会按当前关系和情绪继续回应你。`;
  }

  function buildTokens(text) {
    const value = String(text || "").trim();
    const tokens = value
      .split(/[、，。；：？！,.!?\s]/)
      .map((item) => item.trim())
      .filter(Boolean);
    for (let index = 0; index < value.length - 1; index += 1) {
      tokens.push(value.slice(index, index + 2));
    }
    return [...new Set(tokens.filter((item) => item.length >= 2))];
  }

  const matchedReaction = (profile.reaction_samples || []).find((sample) =>
    buildTokens(sample.trigger).some((token) => promptText.includes(token)),
  );
  if (matchedReaction) {
    return `${character.name}：${matchedReaction.response}（${matchedReaction.affection_delta || "关系变化待判断"}）`;
  }

  function includesAny(keywords) {
    return keywords.some((keyword) => promptText.includes(keyword));
  }

  let intent = "generic";
  if (includesAny(["为什么", "凭什么", "怀疑", "不信", "观察我", "监视", "动机", "试探", "拦我", "真假"])) {
    intent = "challenge";
  } else if (includesAny(["一起", "陪我", "陪你", "下次", "约定", "同行", "巡夜", "继续和你", "带你", "还会"])) {
    intent = "companion";
  } else if (includesAny(["难过", "沮丧", "害怕", "紧张", "担心", "迷茫", "压力", "累", "失望", "心情", "感受", "不开心"])) {
    intent = "emotion";
  } else if (includesAny(["规则", "学院", "怎么", "原理", "线索", "证据", "判断", "脚印", "回响", "结界", "试炼", "为什么会"])) {
    intent = "knowledge";
  } else if (includesAny(["介绍", "你是谁", "认识", "名字", "口吻", "你自己"])) {
    intent = "intro";
  }

  const responsePoolsByCharacterId = {
    101: {
      knowledge: [
        "学院的规则从来不只是为了限制你，它更像一套防止你在未知里失去判断的护栏。你如果愿意，我可以先陪你拆开其中最关键的一条。",
        "先看规则保护了谁，再看规则束缚了谁。只要这个顺序不乱，你就不会被表面的仪式带偏。",
        "你问的是方法，不是答案，这很好。我更愿意把判断路径告诉你，而不是直接替你决定。",
      ],
      emotion: [
        "先别急着责怪自己。试炼里最常见的失误，不是做错选择，而是情绪一乱就不肯继续观察。",
        "你现在需要的不是更快，而是更稳。把刚才最让你在意的那个瞬间告诉我，我们从那里重新看。",
        "能把沮丧说出来，本身就是一种清醒。你先站在这里，我替你把局势理顺一点。",
      ],
      companion: [
        "可以。只要你不是把同行当作依赖，而是愿意一起承担判断，我会继续陪你走下一段。",
        "下次巡夜我会在第二道门等你。但我更在意的是，你到那时会不会比今晚更敢做决定。",
        "我会和你一起去，不过你得先答应我，遇到分歧时先说理由，不要沉默。",
      ],
      challenge: [
        "你会反问，说明你还没有把自己交给惯性。很好，我宁愿带一个会追问的人，也不想带一个只会点头的人。",
        "我观察你，不是为了审判你，而是为了确认你值不值得被托付更深的线索。",
        "如果你连动机都敢问出口，那我也可以坦白一点: 我在判断你会不会为了正确，牺牲掉你真正想保护的人。",
      ],
      intro: [
        "你可以把我当成学院里最不急着给答案的人。我的职责不是替你通关，而是让你学会自己辨认方向。",
        "我是薇岚，负责把新人从混乱里带到能独立判断的位置上。至于喜不喜欢你，要看你接下来的选择。",
      ],
      generic: [
        "我听见了。你这句话背后真正的问题，不在表面，而在你准备为哪个结果负责。",
        "先别把话说满。把你最在意的那个词留下来，我们就能继续往深处走。",
        "你现在的反应，已经能说明很多事。我会按你的选择继续调整对你的判断。",
      ],
    },
    102: {
      knowledge: [
        "要是把学院规则比作地图，它不是告诉你每一步怎么走，而是提醒你哪里会突然塌下去。我可以帮你挑最值得先看的那块。",
        "线索其实已经在你身边啦，只是它们不爱排队。你先盯住最亮的那一个，剩下的我帮你串起来。",
        "你问得好轻巧，但这题其实很关键。像铃的声音多半不是威胁，它更像有人想把你往回引。",
      ],
      emotion: [
        "那我先陪你缓一下。你不用现在就变勇敢，先把最让你不舒服的地方说给我听。",
        "我听出来啦，你不是做不到，是心里有点乱。没关系，我可以先替你记住那些容易漏掉的细节。",
        "别一个人扛着呀。你要是愿意，我可以把刚才那些吓人的部分都拆成比较好处理的小块。",
      ],
      companion: [
        "当然可以！你下次出发前叫我一声，我会把最好用的光路和最亮的尾光都准备好。",
        "你要是愿意带上我，我会很认真地陪你。不是跟在后面那种，是会一起帮你找答案的那种。",
        "说定了哦。下次如果雾又变重，我就负责给你指路，你负责别把我丢下。",
      ],
      challenge: [
        "你这样问也没错啦，但我真不是在糊弄你。我只是想确认，你是在担心危险，还是在担心被骗。",
        "你可以怀疑我，不过先别把门关上。我比大多数人都更希望你别走进错误的方向。",
        "哎，被你这么一问我反而更认真了。那我也直说: 我是在试你会不会把疑问憋在心里。",
      ],
      intro: [
        "我是霁光，负责把严肃的事变得没那么难靠近。如果你愿意，我也可以顺便当你的移动线索提示器。",
        "你可以把我当成会飞的同行搭子。遇到好看的、危险的、奇怪的东西，我通常都会比别人先发现。",
      ],
      generic: [
        "我懂你的意思啦，而且这句很像你会在岔路口说出来的话。我们可以顺着这个方向继续试一次。",
        "你这句话让我有点在意。要不这样，我先把我听见的风声告诉你，你再决定往哪边走。",
        "好呀，那我们就从这里继续。你负责选方向，我负责提醒你别错过那些会闪一下就消失的细节。",
      ],
    },
    103: {
      knowledge: [
        "别只看表面。真正有用的线索通常不显眼，但它们彼此之间会对得上。",
        "规则不是拿来背的，是拿来过滤噪音的。你要是分不清重点，就会被人牵着走。",
        "想判断，就先找反常。脚印、停顿、呼吸、回头次数，任何一个都比空话可靠。",
      ],
      emotion: [
        "情绪可以有，但别让它替你做决定。你要是还想往前走，就先把心跳压下来。",
        "害怕没什么丢人的。真正丢人的是明明慌了，还假装自己看得很清楚。",
        "如果你现在很乱，那就别急着证明自己。先把能确认的东西确认掉。",
      ],
      companion: [
        "你想同行，可以。但我不会为了照顾你放慢判断节奏，你最好跟得上。",
        "下次要不要一起，看你今晚表现。别把承诺说得太早，我更看行动。",
        "可以继续并肩，但你得给出值得我信的理由。夜巡队不收只会依赖别人的人。",
      ],
      challenge: [
        "你敢质疑我，比顺着我说强。至少这说明你还在自己判断。",
        "我在意你的回答，是因为错误的人一旦走进第二章，会拖累整条线索。",
        "想知道我为什么盯着你？因为你身上的犹豫和直觉都太明显，很难不看。",
      ],
      intro: [
        "夜巡学员。职责是排除噪音，确认危险，顺便看看你是不是会在关键时刻犹豫。",
        "名字不重要。你只要记住一件事: 我只尊重能拿出判断的人。",
      ],
      generic: [
        "继续说。我在听，但我更在意你话里没说出来的部分。",
        "这句不算无用，不过还不够。给我一个能落到证据上的理由。",
        "你可以继续解释，但最好别空着来。我对模糊表态没兴趣。",
      ],
    },
  };

  const fallbackPools = {
    knowledge: [
      "先把你看到的、听到的和你推断的分开说，我会更容易顺着角色逻辑回应你。",
      "这个问题可以继续展开，不过我会优先抓住与你当前剧情目标最相关的那一层。",
    ],
    emotion: [
      "我能接住你的情绪，但我也会把它放回当前剧情情境里继续回应。",
      "你先把感受说清楚，我会按这个角色最自然的方式接话。",
    ],
    companion: [
      "如果你想建立更近的关系，我会记住这次选择，并在后续回应里体现出来。",
      "这类问题最能拉开角色差异，我会按你们之间的关系阶段继续往下接。",
    ],
    challenge: [
      "你的质疑会改变这场对话的走向，我会按角色的防御和信任策略回应你。",
      "这种反问很有效，因为它能直接暴露角色真正的立场。",
    ],
    intro: [
      "我会先按角色身份介绍自己，再慢慢把更深一层的动机露出来。",
      "这种问题很适合拿来展示角色口吻和身份感。",
    ],
    generic: [
      "我会继续保留角色口吻，但更具体的提问会让回应更有层次。",
      "继续说下去吧，我会按当前关系、动机和情绪接住这句话。",
    ],
  };

  const activePools = responsePoolsByCharacterId[character.id] || fallbackPools;
  const replyPool = activePools[intent] || activePools.generic || fallbackPools.generic;
  let hash = 0;
  for (const char of promptText) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  const selectedReply = replyPool[hash % replyPool.length];
  const relationshipLevel = Number(character.relationshipLevel || 0);
  const relationshipTone = relationshipLevel >= 70 ? "你这句话会让我更愿意主动靠近你。" : relationshipLevel >= 40 ? "这会继续影响我对你的信任判断。" : "我暂时还不会完全放下戒备。";

  if (intent === "emotion") {
    return `${character.name}：${selectedReply} ${relationshipTone}`;
  }
  if (intent === "companion") {
    return `${character.name}：${selectedReply} ${String(profile.relationship_hook || "").split("。")[0] || relationshipTone}`;
  }
  if (intent === "challenge") {
    return `${character.name}：${selectedReply} ${relationshipTone}`;
  }
  return `${character.name}：${selectedReply}`;
}

function getCharacterAffinityLevel(character) {
  return Math.max(1, Math.floor(Number(character.relationshipLevel || 0) / 20));
}

function getCharacterMemoryTags(character) {
  const baseTags = Array.isArray(character.memoryTags) ? character.memoryTags : [];
  const profile = character.npc_dialogue_profile || {};
  const derivedTags = [profile.need_signal, profile.relationship_hook]
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .map((value) => value.slice(0, 18));
  return [...new Set([...baseTags, ...derivedTags])].slice(0, 4);
}

function openCharacterChat(characterId) {
  if (!state.currentProject) {
    return;
  }
  const targetId = Number(characterId);
  const character = state.currentProject.characters.find((item) => item.id === targetId);
  if (!character) {
    return;
  }
  state.activeCharacterChatId = targetId;
  ensureCharacterChatMessages(character);
  renderCharacterChat();
}

function closeCharacterChat() {
  state.activeCharacterChatId = null;
  state.characterChatDraft = "";
  renderCharacterChat();
}

function sendCharacterChatMessage(message = state.characterChatDraft) {
  const character = getActiveCharacterChat();
  const content = String(message || "").trim();
  if (!character || !content) {
    return;
  }

  const key = String(character.id);
  const messages = ensureCharacterChatMessages(character);
  messages.push({
    id: `${key}-user-${Date.now()}`,
    sender: "user",
    content,
    timestamp: "刚刚",
  });
  messages.push({
    id: `${key}-npc-${Date.now() + 1}`,
    sender: "character",
    content: buildDemoCharacterReply(character, content),
    emotion: "角色即时回应",
    timestamp: "刚刚",
  });
  state.characterChatDraft = "";
  renderCharacterChat();
}

function renderCharacterChat() {
  if (!els.characterChatShell) {
    return;
  }

  const character = getActiveCharacterChat();
  if (!character) {
    els.characterChatShell.classList.add("hidden");
    els.characterChatShell.setAttribute("aria-hidden", "true");
    if (els.characterChatInput) {
      els.characterChatInput.value = "";
    }
    return;
  }

  const messages = ensureCharacterChatMessages(character);
  const quickReplies = buildCharacterQuickReplies(character);
  const profile = character.npc_dialogue_profile || {};
  const avatar = escapeHtml(String(character.name || "角").slice(0, 1));
  const personality = escapeHtml(character.personality || "角色性格待补充");
  const mood = escapeHtml(character.currentMood || character.personality || character.goal || "个性对话已开启");
  const interactionHint = escapeHtml(profile.need_signal || "你可以通过提问、共情和追问来触发不同回复。");
  const relationshipHint = escapeHtml(profile.relationship_hook || "系统会继续记录你的对话选择。");
  const memoryTags = getCharacterMemoryTags(character);
  const relationshipLevel = Math.max(0, Math.min(100, Number(character.relationshipLevel || 0)));
  const affinityLevel = getCharacterAffinityLevel(character);

  els.characterChatAside.innerHTML = `
    <div class="character-chat-aside-top">
      <button class="ghost-button character-chat-back-button" type="button" data-close-character-chat>← 返回工作台</button>
      <div class="character-chat-avatar">${avatar}</div>
      <div class="character-chat-identity">
        <h3>${escapeHtml(character.name)}</h3>
        <p class="muted">${escapeHtml(character.role || "智能 NPC")}</p>
        <span class="status-chip">${escapeHtml(character.status || "在线可聊")}</span>
      </div>
    </div>
    <section class="character-chat-aside-section">
      <div class="character-chat-progress-head">
        <span class="character-chat-section-label">关系进度</span>
        <span class="mini-chip">${escapeHtml(character.relationship || "关系建立中")}</span>
      </div>
      <div class="character-chat-progress-track" aria-label="角色关系进度">
        <span style="width: ${relationshipLevel}%"></span>
      </div>
      <div class="character-chat-progress-meta">
        <span>好感度 Lv.${escapeHtml(affinityLevel)}</span>
        <span>${escapeHtml(profile.friendship_stage || `${relationshipLevel}% 已建立联系`)}</span>
      </div>
    </section>
    <section class="character-chat-aside-section">
      <span class="character-chat-section-label">性格特质</span>
      <p>${personality}</p>
    </section>
    <section class="character-chat-aside-section">
      <span class="character-chat-section-label">当前情绪</span>
      <p>${mood}</p>
    </section>
    <section class="character-chat-aside-section">
      <span class="character-chat-section-label">记忆标签</span>
      <div class="chip-row">
        ${memoryTags.length ? memoryTags.map((tag) => `<span class="mini-chip">${escapeHtml(tag)}</span>`).join("") : `<span class="mini-chip">等待补充设定</span>`}
      </div>
    </section>
    <section class="character-chat-aside-section">
      <span class="character-chat-section-label">互动提示</span>
      <p>${interactionHint}</p>
      <p class="character-chat-helper-note">${relationshipHint}</p>
    </section>
  `;

  els.characterChatHeader.innerHTML = `
    <div class="character-chat-header-main">
      <div class="character-chat-header-avatar">${avatar}</div>
      <div class="character-chat-header-copy">
        <h3>${escapeHtml(character.name)}</h3>
        <p>正在与你对话</p>
      </div>
    </div>
    <div class="character-chat-header-actions">
      <span class="mini-chip is-live">Demo 对话演示</span>
      <button class="ghost-button character-chat-header-button" type="button" aria-label="更多操作">···</button>
    </div>
  `;

  els.characterChatMessages.innerHTML = messages
    .map(
      (entry) => `
        <article class="chat-message ${entry.sender === "user" ? "is-user" : "is-character"}">
          <div class="chat-message-avatar">${entry.sender === "user" ? "我" : avatar}</div>
          <div class="chat-message-bubble">
            ${entry.emotion && entry.sender === "character" ? `<span class="chat-message-emotion">「${escapeHtml(entry.emotion)}」</span>` : ""}
            <p>${escapeHtml(entry.content)}</p>
            <span class="chat-message-time">${escapeHtml(entry.timestamp || "刚刚")}</span>
          </div>
        </article>
      `,
    )
    .join("");

  els.characterChatQuickReplies.innerHTML = `
    <span class="character-chat-section-label">快捷发问</span>
    <div class="character-chat-reply-list">
      ${quickReplies
        .map(
          (reply) => `
            <button class="ghost-button" type="button" data-quick-character-reply="${escapeHtml(reply)}">${escapeHtml(reply)}</button>
          `,
        )
        .join("")}
    </div>
  `;

  els.characterChatInput.value = state.characterChatDraft || "";
  els.characterChatInput.placeholder = `继续和 ${character.name} 对话`;
  els.characterChatShell.classList.remove("hidden");
  els.characterChatShell.setAttribute("aria-hidden", "false");
  window.requestAnimationFrame(() => {
    els.characterChatMessages.scrollTop = els.characterChatMessages.scrollHeight;
    els.characterChatInput.focus();
  });
}

function findLiveChapterJob(chapterId) {
  if (!state.currentProject) {
    return null;
  }
  return (
    state.currentProject.jobs.find(
      (job) => job.chapter_id === Number(chapterId) && !isTerminalJobStatus(job.status),
    ) || null
  );
}

function findLiveSceneJob(sceneId) {
  if (!state.currentProject) {
    return null;
  }
  return (
    state.currentProject.jobs.find(
      (job) => job.scene_id === Number(sceneId) && !isTerminalJobStatus(job.status),
    ) || null
  );
}

function getIllustrationWorkbenchState(sceneId) {
  const current = state.illustrationWorkbench[sceneId] || {};
  return {
    candidateCount: current.candidateCount ?? 2,
    extraGuidance: current.extraGuidance ?? "",
    selectedIllustrationId: current.selectedIllustrationId ?? null,
  };
}

function patchIllustrationWorkbenchState(sceneId, patch) {
  state.illustrationWorkbench[sceneId] = {
    ...getIllustrationWorkbenchState(sceneId),
    ...patch,
  };
}

function computeDurationLabel(run) {
  if (!run?.started_at || !run?.completed_at) {
    return "耗时未知";
  }
  const startedAt = new Date(run.started_at).getTime();
  const completedAt = new Date(run.completed_at).getTime();
  if (Number.isNaN(startedAt) || Number.isNaN(completedAt)) {
    return "耗时未知";
  }
  const seconds = Math.max(0, Math.round((completedAt - startedAt) / 1000));
  return `${seconds}s`;
}

function renderProjects() {
  if (!state.projects.length) {
    els.projectList.innerHTML = `
      <article class="project-card project-card-empty">
        <p class="eyebrow">书架还是空的</p>
        <h4>先创建第一部故事</h4>
        <p class="muted">控制台会保留你的项目资产，进入工作空间后再专注写当前这一部。</p>
      </article>
    `;
    return;
  }

  els.projectList.innerHTML = state.projects
    .map(
      (project) => `
        <article class="project-card console-project-card ${project.id === state.currentProjectId && state.view === "workspace" ? "active" : ""}" data-project-id="${project.id}">
          <div class="project-card-cover" ${project.cover_image_url ? `style="background-image: url('${escapeHtml(project.cover_image_url)}')"` : ""}>
            <span class="mini-chip">${escapeHtml(project.genre)}</span>
            <span class="mini-chip">${project.target_chapter_count} 章</span>
          </div>
          <div class="project-card-body">
            <div class="project-card-copy">
              <p class="eyebrow">${escapeHtml(project.era)} · ${escapeHtml(project.tone)}</p>
              <h4>${escapeHtml(project.title)}</h4>
              <p class="muted">${escapeHtml(project.logline)}</p>
              <p class="muted">状态：${escapeHtml(project.status)} · ${escapeHtml(project.target_length)}</p>
            </div>
            <div class="inline-actions">
              <button class="primary-button" data-open-project="${project.id}">进入工作空间</button>
              <button class="ghost-button danger-button" data-delete-project="${project.id}">删除</button>
            </div>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderDashboard() {
  const projectCount = state.projects.length;
  const totalPlannedChapters = state.projects.reduce(
    (sum, project) => sum + Number(project.target_chapter_count || 0),
    0,
  );
  const activeProject = state.projects.find((project) => project.id === state.currentProjectId) || null;

  els.dashboardMetrics.innerHTML = `
    <article class="metric-card">
      <span class="metric-value">${projectCount}</span>
      <span class="metric-label">项目</span>
    </article>
    <article class="metric-card">
      <span class="metric-value">${state.characterLibrary.length}</span>
      <span class="metric-label">角色资产</span>
    </article>
    <article class="metric-card">
      <span class="metric-value">${totalPlannedChapters}</span>
      <span class="metric-label">目标章节</span>
    </article>
  `;

  const spotlight = activeProject
    ? `最近进入的是《${activeProject.title}》，随时可以回到它的独立工作空间继续创作。`
    : projectCount
      ? "选择任意项目后会进入独立工作空间，章节、Agent 轨迹和角色资产都会围绕该作品展开。"
      : "角色可以先建在全局角色库里，后面再挂接到任何作品。";

  const recentCharacters = state.characterLibrary.slice(0, 4);
  els.dashboardLibrarySummary.innerHTML = `
    <div class="console-library-copy">
      <p class="muted">${escapeHtml(spotlight)}</p>
      <div class="chip-row">
        <span class="status-chip">${projectCount} 个项目</span>
        <span class="status-chip">${state.characterLibrary.length} 个角色</span>
      </div>
    </div>
    ${
      recentCharacters.length
        ? `
            <div class="console-character-preview">
              ${recentCharacters
                .map(
                  (character) => `
                    <article class="console-character-pill">
                      <strong>${escapeHtml(character.name)}</strong>
                      <span>${escapeHtml(character.role)}</span>
                    </article>
                  `,
                )
                .join("")}
            </div>
          `
        : `<p class="muted">点击顶部“新建角色”先建立你的全局角色资产库。</p>`
    }
  `;

  renderProjects();
  updateAuthUI();
}

function renderStoryBiblePanel(project) {
  const workbench = buildStoryBibleWorkbench(project, {
    storyBibleRevisions: state.storyBibleRevisions,
  });
  const activeStoryBibleDiff = state.activeStoryBibleDiffId
    ? state.storyBibleDiffs[`${project.id}:${state.activeStoryBibleDiffId}`]
    : null;
  const summaryChips = [
    `<span class="mini-chip">${escapeHtml(workbench.summary.ruleCountLabel)}</span>`,
    `<span class="mini-chip">${escapeHtml(workbench.summary.filledSectionLabel)}</span>`,
  ]
    .filter(Boolean)
    .join("");

  els.storyBiblePanel.innerHTML = `
    <article class="asset-panel-summary story-bible-summary-card">
      <div class="asset-summary-grid story-bible-summary-grid">
        <article class="asset-summary-stat story-bible-summary-stat">
          <strong>${escapeHtml(workbench.summary.currentRevisionLabel)}</strong>
          <span>当前设定版本</span>
        </article>
        <article class="asset-summary-stat story-bible-summary-stat">
          <strong>${escapeHtml(workbench.summary.targetChapterLabel)}</strong>
          <span>目标章节</span>
        </article>
      </div>
      <div class="chip-row asset-summary-chips">
        ${summaryChips}
      </div>
    </article>
  `;

  els.storyBibleDetail.innerHTML = renderStoryBibleDetailMarkup(project, workbench, activeStoryBibleDiff);
}

function protectedContentLabel(chapter) {
  const protectedSummary = countProtectedContent(chapter);
  if (!protectedSummary.total) {
    return "当前章节还没有手动保护的内容。";
  }
  return `当前章节有 ${protectedSummary.total} 处受保护内容：正文 ${protectedSummary.narrativeBlocks} 处，场景 ${protectedSummary.scenes} 处，对白 ${protectedSummary.dialogueBlocks} 处。`;
}

function renderBlockProtectionChips(item) {
  return `
    <div class="chip-row">
      ${item.is_locked ? `<span class="mini-chip is-locked">已锁</span>` : ""}
      ${item.is_user_edited ? `<span class="mini-chip is-live">人工改稿</span>` : ""}
      ${item.source_revision_id ? `<span class="mini-chip">来源 rev #${escapeHtml(item.source_revision_id)}</span>` : ""}
    </div>
  `;
}

function renderCharacters(project) {
  const attachedCount = project.characters.length;
  const libraryCount = state.characterLibrary.length;
  const withVisualProfile = project.characters.filter((character) => character.visual_profile?.visual_anchor).length;
  const withReferenceImage = project.characters.filter((character) => character.reference_images?.[0]).length;

  els.characterLibrarySummary.innerHTML = `
    <div class="asset-summary-grid">
      <article class="asset-summary-stat">
        <strong>${attachedCount}</strong>
        <span>已挂接角色</span>
      </article>
      <article class="asset-summary-stat">
        <strong>${libraryCount}</strong>
        <span>全局角色资产</span>
      </article>
    </div>
    <div class="chip-row asset-summary-chips">
      <span class="mini-chip">${withVisualProfile} 个已生成视觉锚点</span>
      <span class="mini-chip">${withReferenceImage} 个带参考图</span>
    </div>
    <p class="muted">
      角色先沉淀在全局角色库，再挂接到当前作品。后续章节生成与剧照提示词会优先复用这些角色资产。
    </p>
  `;

  const buildAnchorTokens = (character) => {
    const source = character.visual_profile?.visual_anchor || "";
    const tokens = String(source)
      .split(/[，,、/|]/)
      .map((token) => token.trim())
      .filter(Boolean);
    return [...new Set(tokens)].slice(0, 4);
  };

  const renderReferenceMedia = (character) => {
    if (character.reference_images?.[0]) {
      return `
        <div class="character-media">
          <img src="${character.reference_images[0].url}" alt="${escapeHtml(character.name)}" class="character-image" />
        </div>
      `;
    }

    return `
      <div class="character-media character-image-placeholder" aria-hidden="true">
        <span class="character-image-badge">待补参考图</span>
        <strong>${escapeHtml(character.name)}</strong>
        <span>先保存外貌描述，后面也可以继续补图。</span>
      </div>
    `;
  };

  const renderAnchorChips = (character) => {
    const anchors = buildAnchorTokens(character);
    if (!anchors.length) {
      return `<span class="mini-chip">视觉锚点待生成</span>`;
    }
    return anchors.map((anchor) => `<span class="mini-chip">${escapeHtml(anchor)}</span>`).join("");
  };

  els.characterList.innerHTML = project.characters.length
    ? project.characters
        .map(
          (character) => `
            <article class="character-card character-card-chat-ready">
              <button
                class="character-card-hitarea"
                type="button"
                data-open-character-chat="${character.id}"
                aria-label="和 ${escapeHtml(character.name)} 单独对话"
              ></button>
              <div class="character-card-head">
                <div class="character-card-title">
                  <p class="eyebrow">${escapeHtml(character.role)}</p>
                  <h4>${escapeHtml(character.name)}</h4>
                  <button class="character-chat-launch" type="button" data-open-character-chat="${character.id}">进入单聊</button>
                </div>
                <div class="chip-row">
                  <span class="mini-chip ${character.reference_images?.[0] ? "is-live" : ""}">
                    ${character.reference_images?.[0] ? "参考图已接入" : "仅文本设定"}
                  </span>
                </div>
              </div>
              <div class="character-meta-stack">
                <p class="muted">${escapeHtml(character.signature_line || character.personality)}</p>
                <div class="character-visual-row">
                  <span class="character-visual-label">视觉锚点</span>
                  <div class="chip-row character-anchor-list">${renderAnchorChips(character)}</div>
                </div>
              </div>
              ${renderReferenceMedia(character)}
              <div class="inline-actions character-card-actions">
                <button class="ghost-button" data-detach-character="${character.id}">移出作品</button>
                <button class="ghost-button" data-open-character-modal="library">角色库</button>
              </div>
            </article>
          `,
        )
        .join("")
    : `
        <div class="character-card character-empty-card">
          <p class="eyebrow">角色库待挂接</p>
          <h4>当前作品还没有角色</h4>
          <p class="muted">
            点击顶部“新建角色”，或打开角色库把已有角色挂接进来。角色资产越完整，后续正文口吻和剧照提示词越稳定。
          </p>
        </div>
      `;
}

function renderChapterTabs(project) {
  if (!project.chapters.length) {
    els.chapterTabs.innerHTML = `<div class="panel-note">先生成章节大纲，章节标签才会展开。</div>`;
    return;
  }

  els.chapterTabs.innerHTML = project.chapters
    .map((chapter) => {
      const pendingIntervention = findPendingIntervention(chapter);
      const liveJob = findLiveChapterJob(chapter.id);
      const subtitle = [
        formatChapterStatus(chapter.status),
        chapter.is_locked ? "已锁" : "",
        pendingIntervention ? "待确认" : "",
        liveJob ? "进行中" : "",
      ]
        .filter(Boolean)
        .join(" · ");
      const stateClass = pendingIntervention
        ? "is-warn"
        : liveJob
          ? "is-live"
          : chapter.is_locked
            ? "is-locked"
            : chapter.status === "scenes_ready"
              ? "is-ready"
              : "";

      return `
        <button
          class="chapter-tab ${chapter.id === state.activeChapterId ? "active" : ""}"
          data-select-chapter="${chapter.id}"
        >
          <span class="chapter-tab-index">${String(chapter.order_index).padStart(2, "0")}</span>
          <span class="chapter-tab-copy">
            <span class="chapter-tab-title">${escapeHtml(chapter.title)}</span>
            <span class="chapter-tab-subtitle">${escapeHtml(subtitle)}</span>
          </span>
          <span class="chapter-tab-state ${stateClass}" aria-hidden="true"></span>
        </button>
      `;
    })
    .join("");
}

function renderInterventionCard(intervention) {
  const draftValue =
    state.interventionDrafts[intervention.id] ?? intervention.user_guidance ?? intervention.suggested_guidance ?? "";
  return `
    <section class="intervention-card">
      <div class="intervention-header">
        <div>
          <p class="eyebrow">Reviewer 干预</p>
          <h4>${escapeHtml(formatInterventionLabel(intervention.intervention_type))}</h4>
        </div>
        <span class="status-chip is-warn">等待处理</span>
      </div>
      <p class="muted">${escapeHtml(intervention.reviewer_notes)}</p>
      ${
        intervention.suggested_guidance
          ? `<p class="muted"><strong>建议动作：</strong>${escapeHtml(intervention.suggested_guidance)}</p>`
          : ""
      }
      <label class="stack-form compact">
        <span>补充说明</span>
        <textarea
          rows="4"
          data-intervention-guidance="${intervention.id}"
          placeholder="补充你希望保留的角色关系、情绪方向、节奏调整等…"
        >${escapeHtml(draftValue)}</textarea>
      </label>
      <div class="inline-actions">
        <button class="primary-button" data-retry-intervention="${intervention.id}">
          ${escapeHtml(formatInterventionAction(intervention.intervention_type))}
        </button>
        <button class="ghost-button danger-button" data-dismiss-intervention="${intervention.id}">暂不采纳</button>
      </div>
    </section>
  `;
}

function renderNarrativeBlockCard(block) {
  const draft = state.blockDrafts[block.id];
  const isEditing = draft !== undefined;
  return `
    <article class="narrative-block editable-block">
      <div class="editable-block-head">
        <strong>正文块 ${block.order_index}</strong>
        <div class="inline-actions compact-inline-actions">
          <button class="ghost-button" data-edit-block="${block.id}">${isEditing ? "继续编辑" : "编辑"}</button>
          <button class="ghost-button" data-toggle-block-lock="${block.id}">
            ${block.is_locked ? "取消锁定" : "锁定此块"}
          </button>
        </div>
      </div>
      ${renderBlockProtectionChips(block)}
      ${
        isEditing
          ? `
              <label class="stack-form compact inline-editor">
                <span>正文内容</span>
                <textarea rows="5" data-block-draft="${block.id}">${escapeHtml(draft)}</textarea>
              </label>
              <div class="inline-actions">
                <button class="primary-button" data-save-block="${block.id}">保存改稿</button>
                <button class="ghost-button" data-cancel-block="${block.id}">取消</button>
              </div>
            `
          : `<div>${escapeHtml(block.content)}</div>`
      }
    </article>
  `;
}

function renderDialogueEditor(dialogue) {
  const draft =
    state.dialogueDrafts[dialogue.id] || {
      speaker: dialogue.speaker,
      parenthetical: dialogue.parenthetical,
      content: dialogue.content,
    };
  const isEditing = Boolean(state.dialogueDrafts[dialogue.id]);
  return `
    <div class="dialogue-line editable-dialogue-line">
      <div class="editable-block-head">
        <strong>${escapeHtml(dialogue.speaker)}</strong>
        <div class="inline-actions compact-inline-actions">
          <button class="ghost-button" data-edit-dialogue="${dialogue.id}">${isEditing ? "继续编辑" : "编辑"}</button>
          <button class="ghost-button" data-toggle-dialogue-lock="${dialogue.id}">
            ${dialogue.is_locked ? "取消锁定" : "锁定对白"}
          </button>
        </div>
      </div>
      ${renderBlockProtectionChips(dialogue)}
      ${
        isEditing
          ? `
              <div class="stack-form compact inline-editor">
                <label>
                  <span>说话人</span>
                  <input type="text" value="${escapeHtml(draft.speaker)}" data-dialogue-draft-field="${dialogue.id}" data-field="speaker" />
                </label>
                <label>
                  <span>括注</span>
                  <input type="text" value="${escapeHtml(draft.parenthetical)}" data-dialogue-draft-field="${dialogue.id}" data-field="parenthetical" />
                </label>
                <label>
                  <span>对白</span>
                  <textarea rows="3" data-dialogue-draft-field="${dialogue.id}" data-field="content">${escapeHtml(draft.content)}</textarea>
                </label>
              </div>
              <div class="inline-actions">
                <button class="primary-button" data-save-dialogue="${dialogue.id}">保存对白</button>
                <button class="ghost-button" data-cancel-dialogue="${dialogue.id}">取消</button>
              </div>
            `
          : `
              ${dialogue.parenthetical ? `<span class="muted">（${escapeHtml(dialogue.parenthetical)}）</span>` : ""}
              <div>${escapeHtml(dialogue.content)}</div>
            `
      }
    </div>
  `;
}

function renderSceneCard(scene) {
  const liveIllustrationJob = findLiveSceneJob(scene.id);
  const canonicalIllustration = scene.illustrations.find((item) => item.is_canonical) || null;
  const workbench = getIllustrationWorkbenchState(scene.id);
  const featuredIllustration = resolveFeaturedIllustration(scene, workbench.selectedIllustrationId);
  const sceneDraft =
    state.sceneDrafts[scene.id] || {
      title: scene.title,
      scene_type: scene.scene_type,
      location: scene.location,
      time_of_day: scene.time_of_day,
      objective: scene.objective,
      emotional_tone: scene.emotional_tone,
      visual_prompt: scene.visual_prompt || "",
    };
  const isEditingScene = Boolean(state.sceneDrafts[scene.id]);
  const dialogues = scene.dialogue_blocks.length
    ? scene.dialogue_blocks.map((dialogue) => renderDialogueEditor(dialogue)).join("")
    : `<p class="muted">这一场还没有对白块。</p>`;

  const illustrationOptions = [1, 2, 3, 4]
    .map(
      (count) =>
        `<option value="${count}" ${Number(workbench.candidateCount) === count ? "selected" : ""}>${count} 张</option>`,
    )
    .join("");

  const illustrationFilmstrip = scene.illustrations.length
    ? `
        <div class="illustration-filmstrip">
          ${scene.illustrations
            .map(
              (item) => `
                <button
                  class="illustration-thumb ${featuredIllustration?.id === item.id ? "is-selected" : ""} ${item.is_canonical ? "is-canonical" : ""}"
                  type="button"
                  data-select-illustration="${item.id}"
                  data-scene-id="${scene.id}"
                >
                  <img src="${escapeHtml(item.thumbnail_url)}" alt="scene illustration thumbnail" />
                  <span>候选 ${item.candidate_index}${item.is_canonical ? " · 主图" : ""}</span>
                </button>
              `,
            )
            .join("")}
        </div>
      `
    : `<div class="illustration-empty muted">还没有候选剧照。先生成一轮，下面会变成可挑选的镜头台。</div>`;

  const featuredIllustrationCard = featuredIllustration
    ? `
        <article class="illustration-featured-card ${featuredIllustration.is_canonical ? "is-canonical" : ""}">
          <img src="${escapeHtml(featuredIllustration.url)}" alt="scene illustration preview" class="illustration-featured-image" />
          <div class="illustration-featured-meta">
            <div class="illustration-featured-head">
              <div>
                <p class="eyebrow">当前预览</p>
                <h6>候选 ${featuredIllustration.candidate_index}${featuredIllustration.is_canonical ? " · 已设为主图" : ""}</h6>
              </div>
              <div class="inline-actions">
                <a class="ghost-button" href="${escapeHtml(featuredIllustration.url)}" target="_blank" rel="noreferrer">查看原图</a>
                <button class="ghost-button" data-mark-canonical="${featuredIllustration.id}" ${featuredIllustration.is_canonical ? "disabled" : ""}>
                  ${featuredIllustration.is_canonical ? "当前主图" : "设为主图"}
                </button>
                <button class="ghost-button danger-button" data-delete-illustration="${featuredIllustration.id}">删除</button>
              </div>
            </div>
            <div class="prompt-card compact-prompt">
              <strong>候选 Prompt 摘要</strong>
              <div>${escapeHtml(featuredIllustration.prompt_text || "当前候选没有返回额外 prompt。")}</div>
            </div>
          </div>
        </article>
      `
    : `
        <div class="illustration-featured-placeholder">
          <p class="eyebrow">镜头预览</p>
          <h6>还没有可预览的剧照</h6>
          <p>生成后这里会固定展示你当前选中的候选图，方便设为主图或继续重生成。</p>
        </div>
      `;

  const illustrationWorkbench = `
    <section class="illustration-workbench">
      <div class="illustration-workbench-head">
        <div>
          <p class="eyebrow">剧照工作台</p>
          <h6>${canonicalIllustration ? "主图已锁定，可继续参考重生成" : "先生成候选，再挑出主图"}</h6>
        </div>
        ${liveIllustrationJob ? `<span class="status-chip is-live">${escapeHtml(formatJobStatus(liveIllustrationJob.status))}</span>` : ""}
      </div>
      <div class="illustration-toolbar">
        <label class="compact-field">
          <span>候选数量</span>
          <select data-illustration-count="${scene.id}">
            ${illustrationOptions}
          </select>
        </label>
        <label class="compact-field illustration-guidance-field">
          <span>重生成说明</span>
          <textarea
            rows="2"
            data-illustration-guidance="${scene.id}"
            placeholder="例如：保留面部识别度，只把灯光压冷一些；服装不要变。"
          >${escapeHtml(workbench.extraGuidance)}</textarea>
        </label>
        <div class="inline-actions">
          <button class="ghost-button" data-generate-illustrations="${scene.id}" ${liveIllustrationJob ? "disabled" : ""}>
            ${scene.illustrations.length ? "参考当前主图重生成" : "生成剧照"}
          </button>
        </div>
      </div>
      <div class="illustration-reference-note ${canonicalIllustration ? "is-active" : ""}">
        ${
          canonicalIllustration
            ? `当前主图会自动回灌到下一轮生成，系统会优先延续候选 ${canonicalIllustration.candidate_index} 的人物识别度、服装逻辑和灯光方向。`
            : "当前还没有主图，下一轮会以角色视觉档案和场景 prompt 为主要参照。"
        }
      </div>
      ${featuredIllustrationCard}
      ${illustrationFilmstrip}
    </section>
  `;

  return `
    <article class="scene-card figma-scene-card">
      <div class="scene-heading">
        <div>
          <p class="eyebrow">${escapeHtml(scene.scene_type)} · ${escapeHtml(scene.time_of_day)}</p>
          <h5>${escapeHtml(scene.title)}</h5>
        </div>
        <div class="chip-row">
          <span class="mini-chip">${escapeHtml(scene.location)}</span>
          ${scene.is_locked ? `<span class="mini-chip is-locked">已锁</span>` : ""}
          ${scene.is_user_edited ? `<span class="mini-chip is-live">人工改稿</span>` : ""}
        </div>
      </div>
      <div class="inline-actions compact-inline-actions">
        <button class="ghost-button" data-edit-scene="${scene.id}">${isEditingScene ? "继续编辑" : "编辑场景"}</button>
        <button class="ghost-button" data-toggle-scene-lock="${scene.id}">
          ${scene.is_locked ? "取消锁定" : "锁定场景"}
        </button>
      </div>
      ${
        isEditingScene
          ? `
              <div class="stack-form compact inline-editor">
                <label>
                  <span>场景标题</span>
                  <input type="text" value="${escapeHtml(sceneDraft.title)}" data-scene-draft-field="${scene.id}" data-field="title" />
                </label>
                <label>
                  <span>景别</span>
                  <input type="text" value="${escapeHtml(sceneDraft.scene_type)}" data-scene-draft-field="${scene.id}" data-field="scene_type" />
                </label>
                <label>
                  <span>地点</span>
                  <input type="text" value="${escapeHtml(sceneDraft.location)}" data-scene-draft-field="${scene.id}" data-field="location" />
                </label>
                <label>
                  <span>时段</span>
                  <input type="text" value="${escapeHtml(sceneDraft.time_of_day)}" data-scene-draft-field="${scene.id}" data-field="time_of_day" />
                </label>
                <label>
                  <span>场景目标</span>
                  <textarea rows="3" data-scene-draft-field="${scene.id}" data-field="objective">${escapeHtml(sceneDraft.objective)}</textarea>
                </label>
                <label>
                  <span>情绪</span>
                  <input type="text" value="${escapeHtml(sceneDraft.emotional_tone)}" data-scene-draft-field="${scene.id}" data-field="emotional_tone" />
                </label>
              </div>
              <div class="inline-actions">
                <button class="primary-button" data-save-scene="${scene.id}">保存场景</button>
                <button class="ghost-button" data-cancel-scene="${scene.id}">取消</button>
              </div>
            `
          : ""
      }
      <p class="muted"><strong>目标：</strong>${escapeHtml(scene.objective)}</p>
      <p class="muted"><strong>情绪：</strong>${escapeHtml(scene.emotional_tone)}</p>
      <p class="muted"><strong>出场：</strong>${escapeHtml(scene.cast_names.join(" / ") || "待补全")}</p>
      <div class="figma-scene-summary">
        <div>
          <span class="figma-scene-metric">${escapeHtml(scene.dialogue_blocks.length)}</span>
          <span>对话</span>
        </div>
        <div>
          <span class="figma-scene-metric">${escapeHtml(scene.illustrations.length)}</span>
          <span>剧照</span>
        </div>
        <div>
          <span class="figma-scene-metric">${scene.is_locked ? "锁" : "开"}</span>
          <span>状态</span>
        </div>
      </div>
      <div class="dialogue-stack">${dialogues}</div>
      ${
        scene.visual_prompt
          ? `
              <div class="narrative-block prompt-card">
                <strong>Visual Prompt 摘要</strong>
                <div>${escapeHtml(scene.visual_prompt)}</div>
              </div>
            `
          : ""
      }
      ${illustrationWorkbench}
    </article>
  `;
}

function renderChapterDetail(project) {
  const chapter = getActiveChapter();
  if (!chapter) {
    els.chapterDetail.innerHTML = `<div class="chapter-card"><p class="muted">当前还没有可编辑章节。</p></div>`;
    els.chapterPager.innerHTML = "";
    return;
  }

  const chapterIndex = project.chapters.findIndex((item) => item.id === chapter.id);
  const previousChapter = chapterIndex > 0 ? project.chapters[chapterIndex - 1] : null;
  const nextChapter = chapterIndex < project.chapters.length - 1 ? project.chapters[chapterIndex + 1] : null;
  const pendingIntervention = findPendingIntervention(chapter);
  const liveJob = findLiveChapterJob(chapter.id);
  const liveJobFeedback = liveJob ? describeJobFeedback(liveJob) : null;
  const liveJobProgress = liveJob ? resolveWorkflowProgress(liveJob) : null;
  const hasActiveJob = Boolean(liveJob);
  const chapterRevisions = state.chapterRevisions[chapter.id] || [];
  const activeChapterDiff = state.activeChapterRevisionDiffId
    ? state.chapterRevisionDiffs[chapter.id]?.[state.activeChapterRevisionDiffId] || null
    : null;
  const protectedSummary = countProtectedContent(chapter);

  const chapterBadges = [
    `<span class="status-chip">${escapeHtml(formatChapterStatus(chapter.status))}</span>`,
    chapter.is_locked ? `<span class="status-chip is-locked">已锁定</span>` : "",
    chapter.status === "needs_regeneration" ? `<span class="status-chip is-warn">建议重生成</span>` : "",
    pendingIntervention ? `<span class="status-chip is-warn">存在 Reviewer 干预</span>` : "",
    liveJob ? `<span class="status-chip is-live">协作进行中</span>` : "",
  ]
    .filter(Boolean)
    .join("");

  const actionHint = chapter.is_locked
    ? "章节已锁定，先取消锁定后才能继续生成。"
    : pendingIntervention
      ? "本章有待处理的 Reviewer 干预，先处理后再继续生成更稳妥。"
      : liveJob
        ? liveJobFeedback?.message || "当前有一条生成任务正在运行。"
        : "";

  const overwriteHint = protectedSummary.total
    ? `再次生成时，已锁定或人工编辑的内容会尽量保留。${protectedContentLabel(chapter)}`
    : "";

  els.chapterDetail.innerHTML = `
    <article class="chapter-card chapter-workspace">
      <div class="stage-mode-switcher" aria-label="章节生成模式">
        <button class="stage-mode-pill is-active" type="button">默认</button>
        <button class="stage-mode-pill" type="button">AI 生成中</button>
        <button class="stage-mode-pill" type="button">Reviewer 审校</button>
      </div>
      <div class="chapter-header">
        <div>
          <p class="eyebrow">第 ${chapter.order_index} 章</p>
          <h4>${escapeHtml(chapter.title)}</h4>
        </div>
        <div class="chip-row">${chapterBadges}</div>
      </div>
      <p class="chapter-meta">${escapeHtml(chapter.summary)}</p>
      <div class="chapter-summary-grid">
        <div class="narrative-block">
          <strong>章节目标</strong>
          <div>${escapeHtml(chapter.chapter_goal)}</div>
        </div>
        <div class="narrative-block">
          <strong>章节钩子</strong>
          <div>${escapeHtml(chapter.hook)}</div>
        </div>
      </div>
      <div class="inline-actions">
        <button class="primary-button" data-generate-draft="${chapter.id}" ${chapter.is_locked || hasActiveJob ? "disabled" : ""}>生成正文</button>
        <button class="ghost-button" data-generate-scenes="${chapter.id}" ${chapter.is_locked || hasActiveJob ? "disabled" : ""}>生成场景</button>
        <button class="ghost-button" data-lock-chapter="${chapter.id}" ${hasActiveJob ? "disabled" : ""}>
          ${chapter.is_locked ? "取消锁定" : "锁定章节"}
        </button>
      </div>
      ${
        liveJob
          ? `
              <section class="live-stage-card">
                <div class="live-stage-header">
                  <div>
                    <p class="eyebrow">实时协作</p>
                    <h5>${escapeHtml(formatJobType(liveJob.job_type))}</h5>
                  </div>
                  <span class="status-chip is-live">${escapeHtml(formatJobStatus(liveJob.status))} · ${liveJob.progress}%</span>
                </div>
                <p>${escapeHtml(liveJobFeedback?.message || "Agent 正在处理当前章节。")}</p>
                ${renderWorkflowStageRail(liveJob)}
                ${
                  liveJobProgress?.currentStepLabel
                    ? `<p class="panel-note">当前步骤：${escapeHtml(liveJobProgress.currentStepLabel)}${
                        liveJobProgress.latestAgentSummary ? ` · ${escapeHtml(liveJobProgress.latestAgentSummary)}` : ""
                      }</p>`
                    : ""
                }
              </section>
            `
          : ""
      }
      ${actionHint ? `<p class="panel-note">${escapeHtml(actionHint)}</p>` : ""}
      ${overwriteHint ? `<p class="panel-note emphasis-note">${escapeHtml(overwriteHint)}</p>` : ""}
      ${pendingIntervention ? renderInterventionCard(pendingIntervention) : ""}
      <section class="chapter-section">
        <div class="section-heading">
          <h5>版本历史</h5>
        </div>
        ${
          chapter.latest_revision
            ? `<p class="muted">当前章节基于 Story Bible 版本 #${escapeHtml(chapter.source_story_bible_revision_id || "未记录")} 生成，最近 revision 为 #${escapeHtml(chapter.latest_revision.id)}。</p>`
            : `<p class="muted">当前章节还没有可恢复版本。</p>`
        }
        ${
          chapterRevisions.length
            ? `
                <div class="revision-list chapter-revision-list">
                  ${chapterRevisions
                    .slice(0, 5)
                    .map(
                      (revision) => `
                        <article class="revision-card">
                          <div class="revision-card-head">
                            <strong>Revision #${revision.id}</strong>
                            <span class="mini-chip">${escapeHtml(revision.created_by)}</span>
                          </div>
                          <p class="muted">${escapeHtml(revision.summary || "未写摘要")}</p>
                          <div class="chip-row">
                            <span class="mini-chip">${escapeHtml(revision.revision_kind)}</span>
                            <span class="mini-chip">${escapeHtml(revision.narrative_block_count)} 段正文</span>
                            <span class="mini-chip">${escapeHtml(revision.scene_count)} 场</span>
                          </div>
                          <div class="inline-actions">
                            <button class="ghost-button" data-view-chapter-diff="${revision.id}" data-chapter-id="${chapter.id}">
                              ${state.activeChapterRevisionDiffId === revision.id ? "收起差异" : "查看差异"}
                            </button>
                            <button class="ghost-button" data-restore-revision="${revision.id}" data-chapter-id="${chapter.id}">恢复到此版本</button>
                          </div>
                        </article>
                      `,
                    )
                    .join("")}
                </div>
              `
            : `<p class="muted">还没有更多历史版本。</p>`
        }
        ${renderChapterRevisionDiff(activeChapterDiff)}
      </section>
      <section class="chapter-section">
        <div class="section-heading">
          <h5>正文块</h5>
        </div>
        ${
          chapter.narrative_blocks.length
            ? chapter.narrative_blocks
                .map((block) => renderNarrativeBlockCard(block))
                .join("")
            : `<p class="muted">正文还未生成。</p>`
        }
      </section>
      <section class="chapter-section">
        <div class="section-heading">
          <h5>Reviewer 审校说明</h5>
        </div>
        ${
          chapter.continuity_notes.length
            ? `<div class="narrative-block">${chapter.continuity_notes.map((note) => escapeHtml(note)).join("<br>")}</div>`
            : `<p class="muted">当前没有连续性提示。</p>`
        }
      </section>
      <section class="chapter-section">
        <div class="section-heading">
          <h5>Scene 卡</h5>
        </div>
        ${
          chapter.scenes.length
            ? `<div class="scene-stack">${chapter.scenes.map((scene) => renderSceneCard(scene)).join("")}</div>`
            : `<p class="muted">场景卡还未生成。</p>`
        }
      </section>
    </article>
  `;

  els.chapterPager.innerHTML = `
    <div class="chapter-nav">
      ${
        previousChapter
          ? `<button class="ghost-button" data-select-chapter="${previousChapter.id}">上一章 · ${escapeHtml(previousChapter.title)}</button>`
          : `<span class="panel-note">已经是第一章</span>`
      }
      ${
        nextChapter
          ? `<button class="ghost-button" data-select-chapter="${nextChapter.id}">下一章 · ${escapeHtml(nextChapter.title)}</button>`
          : `<span class="panel-note">已经是最后一章</span>`
      }
    </div>
  `;
}

function renderJobList(project) {
  const workbench = buildAgentWorkbench(project, {
    selectedJobDetail: state.selectedJobDetail,
    activeChapterId: state.activeChapterId,
  });
  const historyMarkup = workbench.history.length
    ? `
        <div class="agent-history-list">
          ${workbench.history
            .map(
              (item) => `
                <button
                  class="agent-history-item ${item.isSelected ? "active" : ""} ${item.isFocus ? "is-focus" : ""}"
                  type="button"
                  data-select-job="${item.jobId}"
                >
                  <span class="agent-history-rail" aria-hidden="true">
                    <span class="agent-history-dot is-${item.tone}"></span>
                  </span>
                  <span class="agent-history-body">
                    <span class="agent-history-top">
                      <strong>${escapeHtml(item.title)}</strong>
                      <span class="mini-chip ${item.tone === "warn" ? "is-warn" : item.tone === "success" ? "is-live" : ""}">
                        ${escapeHtml(item.statusLabel)}
                      </span>
                    </span>
                    ${item.chapterLabel ? `<span class="agent-history-chapter">${escapeHtml(item.chapterLabel)}</span>` : ""}
                    <span class="agent-history-summary">${escapeHtml(item.summary)}</span>
                    <span class="agent-history-meta">
                      ${item.currentStepLabel ? `<span>${escapeHtml(item.currentStepLabel)}</span>` : ""}
                      ${item.progressLabel ? `<span>${escapeHtml(item.progressLabel)}</span>` : ""}
                    </span>
                  </span>
                </button>
              `,
            )
            .join("")}
        </div>
      `
    : `<div class="job-card job-card-empty"><p class="muted">生成大纲后，右侧会开始沉淀 Agent 的协作历史。</p></div>`;

  els.jobList.innerHTML = `
    <section class="agent-history-shell agent-surface">
      <div class="agent-section-head">
        <div>
          <p class="eyebrow">历史轨迹</p>
          <h4>最近协作记录</h4>
        </div>
        <div class="chip-row">
          ${
            workbench.summary.activeJobs
              ? `<span class="mini-chip is-live">${escapeHtml(`${workbench.summary.activeJobs} 条进行中`)}</span>`
              : ""
          }
          ${
            workbench.summary.awaitingJobs
              ? `<span class="mini-chip is-warn">${escapeHtml(`${workbench.summary.awaitingJobs} 条待确认`)}</span>`
              : ""
          }
          <span class="mini-chip">${escapeHtml(`${workbench.summary.totalJobs} 条任务`)}</span>
        </div>
      </div>
      ${historyMarkup}
    </section>
  `;
}

function renderAgentFocusPanel(project) {
  const workbench = buildAgentWorkbench(project, {
    selectedJobDetail: state.selectedJobDetail,
    activeChapterId: state.activeChapterId,
  });
  const focus = workbench.focus;
  const focusJob = project.jobs.find((job) => Number(job.id) === Number(focus.jobId)) || null;
  const focusActions = [
    focus.chapterId ? `<button class="ghost-button" data-select-chapter="${focus.chapterId}">定位章节</button>` : "",
    focus.jobId ? `<button class="primary-button" data-select-job="${focus.jobId}">展开轨迹</button>` : "",
    focusJob?.status === "failed" ? `<button class="ghost-button" data-retry-job="${focusJob.id}">重试任务</button>` : "",
  ]
    .filter(Boolean)
    .join("");

  els.agentFocus.innerHTML = `
    <section class="agent-focus-card agent-surface is-${escapeHtml(focus.tone)}">
      <div class="figma-agent-status">
        <span class="figma-agent-dot" aria-hidden="true"></span>
        <span>智能协作台</span>
      </div>
      <div class="agent-focus-header">
        <div>
          <p class="eyebrow">${escapeHtml(focus.eyebrow)}</p>
          <h4>${escapeHtml(focus.title)}</h4>
        </div>
        <span class="status-chip ${focus.tone === "warn" ? "is-warn" : focus.tone === "success" ? "is-live" : ""}">
          ${escapeHtml(focus.statusLabel)}
        </span>
      </div>
      ${focus.chapterLabel ? `<p class="agent-focus-chapter">${escapeHtml(focus.chapterLabel)}</p>` : ""}
      <p class="agent-focus-summary">${escapeHtml(focus.summary)}</p>
      ${
        focus.detail
          ? `<div class="agent-focus-detail"><strong>当前节点</strong><p>${escapeHtml(focus.detail)}</p></div>`
          : ""
      }
      <div class="agent-focus-meta">
        ${focus.progressLabel ? `<span class="mini-chip">${escapeHtml(focus.progressLabel)}</span>` : ""}
        ${
          workbench.summary.activeJobs
            ? `<span class="mini-chip is-live">${escapeHtml(`${workbench.summary.activeJobs} 条正在协作`)}</span>`
            : ""
        }
        ${
          workbench.summary.awaitingJobs
            ? `<span class="mini-chip is-warn">${escapeHtml(`${workbench.summary.awaitingJobs} 条等待你确认`)}</span>`
            : ""
        }
        ${workbench.summary.completedJobs ? `<span class="mini-chip">${escapeHtml(`${workbench.summary.completedJobs} 条已完成`)}</span>` : ""}
      </div>
      ${focusJob ? renderWorkflowStageRail(focusJob) : ""}
      ${focusActions ? `<div class="agent-focus-actions inline-actions">${focusActions}</div>` : ""}
    </section>
  `;
}

function renderTracePanel() {
  if (!state.selectedJobDetail) {
    els.jobTrace.innerHTML = `
      <section class="trace-shell agent-surface">
        <div class="trace-empty">
          <p class="eyebrow">协作时间线</p>
          <h4>先选择一条任务记录</h4>
          <p class="muted">这里会展开本轮协作中谁参与了生成、谁提出了审校意见、最终采纳了哪些结果。</p>
        </div>
      </section>
    `;
    return;
  }

  const job = state.selectedJobDetail;
  const jobFeedback = describeJobFeedback(job);
  const workflowProgress = resolveWorkflowProgress(job);
  const runs = job.agent_runs || [];
  const pendingInterventions = job.pending_interventions || [];
  els.jobTrace.innerHTML = `
    <section class="trace-shell agent-surface agent-trace-shell">
      <div class="trace-header">
        <div>
          <p class="eyebrow">协作时间线</p>
          <h4>${escapeHtml(formatJobType(job.job_type))}</h4>
        </div>
        <span class="status-chip ${job.status === "awaiting_user" ? "is-warn" : ""}">${escapeHtml(formatJobStatus(job.status))}</span>
      </div>
      ${renderWorkflowStageRail(job)}
      ${
        workflowProgress.currentStepLabel
          ? `
              <div class="trace-banner">
                <div>
                  <strong>当前步骤</strong>
                  <div>${escapeHtml(workflowProgress.currentStepLabel)}</div>
                  ${
                    workflowProgress.latestAgentSummary
                      ? `<div class="muted">${escapeHtml(workflowProgress.latestAgentSummary)}</div>`
                      : ""
                  }
                </div>
              </div>
            `
          : ""
      }
      ${
        jobFeedback.message
          ? `
              <div class="trace-live-banner ${jobFeedback.tone === "danger" ? "is-danger" : ""}">
                <strong>当前进展</strong>
                <div>${escapeHtml(jobFeedback.message)}</div>
                ${job.status_message ? `<div>${escapeHtml(job.status_message)}</div>` : ""}
              </div>
            `
          : ""
      }
      ${
        pendingInterventions.length
          ? `
              <div class="trace-banner">
                ${pendingInterventions
                  .map(
                    (item) => `
                      <div>
                        <strong>${escapeHtml(formatInterventionLabel(item.intervention_type))}</strong>
                        <div>${escapeHtml(item.reviewer_notes)}</div>
                      </div>
                    `,
                  )
                  .join("")}
              </div>
            `
          : ""
      }
      ${
        runs.length
          ? `
              <div class="trace-list">
                ${runs
                  .map(
                    (run) => `
                      <article class="trace-card">
                        <div class="trace-card-header">
                          <div>
                            <p class="eyebrow">${escapeHtml(run.step_key)}</p>
                            <h5>${escapeHtml(run.agent_name)} · ${escapeHtml(run.model_id || "未记录模型")}</h5>
                          </div>
                          <div class="chip-row">
                            <span class="mini-chip">${escapeHtml(run.status)}</span>
                            <span class="mini-chip">${escapeHtml(formatAdoptionState(run.adoption_state))}</span>
                            ${run.decision ? `<span class="mini-chip is-warn">${escapeHtml(run.decision)}</span>` : ""}
                          </div>
                        </div>
                        <p class="muted">耗时：${escapeHtml(computeDurationLabel(run))}</p>
                        ${run.input_summary ? `<div class="trace-block"><strong>输入摘要</strong><div>${escapeHtml(run.input_summary)}</div></div>` : ""}
                        ${
                          run.public_notes?.length
                            ? `<div class="trace-block"><strong>协作思路</strong><div>${run.public_notes.map((note) => escapeHtml(note)).join("<br>")}</div></div>`
                            : ""
                        }
                        ${run.prompt_preview ? `<div class="trace-block"><strong>协作摘要</strong><div>${escapeHtml(run.prompt_preview)}</div></div>` : ""}
                        ${run.output_summary ? `<div class="trace-block"><strong>产出摘要</strong><div>${escapeHtml(run.output_summary)}</div></div>` : ""}
                        ${
                          run.stream_text
                            ? `<div class="trace-block trace-stream-block"><strong>实时生成流</strong><pre class="trace-stream">${escapeHtml(run.stream_text)}</pre></div>`
                            : ""
                        }
                        ${
                          run.issues?.length
                            ? `<div class="trace-block"><strong>问题清单</strong><div>${run.issues.map((issue) => escapeHtml(issue)).join("<br>")}</div></div>`
                            : ""
                        }
                        ${run.error_message ? `<div class="trace-block"><strong>错误</strong><div>${escapeHtml(run.error_message)}</div></div>` : ""}
                      </article>
                    `,
                  )
                  .join("")}
              </div>
            `
          : `<p class="muted">这条任务还没有写入可展示的 Agent trace。</p>`
      }
    </section>
  `;
}

function renderExports(project) {
  const center = buildExportDeliveryCenter(project.exports);
  if (center.state === "empty") {
    els.exportList.innerHTML = `
      <section class="delivery-center agent-surface empty">
        <div class="agent-section-head">
          <div>
            <p class="eyebrow">交付台</p>
            <h4>成品导出</h4>
          </div>
        </div>
        <article class="export-card delivery-empty-card">
          <h4>还没有导出成品</h4>
          <p class="muted">当 PDF / DOCX 合成完成后，这里会显示下载入口、质量状态和交付历史。</p>
        </article>
      </section>
    `;
    return;
  }

  const hero = center.hero;
  const cardLookup = new Map(center.cards.map((card) => [card.id, card]));
  els.exportList.innerHTML = `
    <section class="delivery-center agent-surface ${center.state === "ready" ? "is-ready" : "is-processing"}">
      <div class="agent-section-head">
        <div>
          <p class="eyebrow">交付台</p>
          <h4>导出与下载</h4>
        </div>
        <div class="chip-row">
          <span class="mini-chip">${center.metrics[0]?.value || 0} 个成品</span>
          <span class="mini-chip ${hero.qualityLabel.includes("通过") ? "is-live" : hero.qualityLabel.includes("未通过") ? "is-warn" : ""}">
            ${escapeHtml(hero.qualityLabel)}
          </span>
        </div>
      </div>
      <article class="export-card delivery-hero-card">
        <div class="delivery-hero-copy">
          <h4>${escapeHtml(hero.title)}</h4>
          <p class="muted">${escapeHtml(hero.summary)}</p>
          <div class="chip-row delivery-hero-meta">
            <span class="status-chip ${hero.qualityLabel.includes("通过") ? "is-live" : hero.qualityLabel.includes("未通过") ? "is-warn" : ""}">
              ${escapeHtml(hero.qualityLabel)}
            </span>
            ${hero.meta.map((item) => `<span class="mini-chip">${escapeHtml(item)}</span>`).join("")}
          </div>
        </div>
        <div class="delivery-download-stack">
          ${
            hero.downloads.length
              ? hero.downloads
                  .map(
                    (download) => `
                      <a class="primary-button export-download-link" href="${escapeHtml(download.url)}" download>
                        ${escapeHtml(download.label)}
                      </a>
                    `,
                  )
                  .join("")
              : `<p class="muted">导出任务正在处理中，完成后这里会出现直接下载按钮。</p>`
          }
        </div>
      </article>

      <div class="delivery-metrics-grid">
        ${center.metrics
          .map(
            (metric) => `
              <article class="delivery-metric-card">
                <strong>${escapeHtml(metric.value)}</strong>
                <span>${escapeHtml(metric.label)}</span>
              </article>
            `,
          )
          .join("")}
      </div>

      <div class="delivery-card-grid">
        ${project.exports
          .map((bundle) => {
            const card = cardLookup.get(Number(bundle.id));
            if (!card) {
              return "";
            }
            const qualityStatus = String(bundle.delivery_summary?.quality_status || "").trim();
            const qualityClass =
              qualityStatus === "passed" ? "is-live" : qualityStatus === "failed" ? "is-warn" : "";
            return `
              <article class="export-card delivery-card ${bundle.id === state.featuredExportId ? "is-featured" : ""}">
                <div class="delivery-card-head">
                  <div>
                    <p class="eyebrow">导出包 #${bundle.id}</p>
                    <h4>${escapeHtml(card.formatsLabel || "导出成品")}</h4>
                  </div>
                  <div class="chip-row">
                    <span class="status-chip ${bundle.status === "completed" ? "is-live" : bundle.status === "failed" ? "is-warn" : ""}">
                      ${escapeHtml(card.statusLabel)}
                    </span>
                    <span class="mini-chip ${qualityClass}">${escapeHtml(card.qualityLabel)}</span>
                  </div>
                </div>
                <p class="muted">${escapeHtml(card.summary)}</p>
                <div class="delivery-card-meta">
                  <span>${escapeHtml(card.pageCountLabel)}</span>
                  <span>${escapeHtml(card.sizeLabel)}</span>
                </div>
                ${
                  card.downloads.length
                    ? `
                        <div class="export-download-grid">
                          ${card.downloads
                            .map(
                              (download) => `
                                <a class="ghost-button export-download-link" href="${escapeHtml(download.url)}" download>
                                  ${escapeHtml(download.label)}
                                </a>
                              `,
                            )
                            .join("")}
                        </div>
                      `
                    : `<p class="muted">文件生成中…</p>`
                }
                ${
                  isTerminalJobStatus(bundle.status)
                    ? `<div class="inline-actions"><button class="ghost-button danger-button" data-delete-export="${bundle.id}">删除导出</button></div>`
                    : ""
                }
              </article>
            `;
          })
          .join("")}
      </div>
    </section>
    `;
}

function getDemoChapterStatus(chapter) {
  if (findPendingIntervention(chapter)) {
    return { label: "Review 中", className: "is-warn" };
  }
  if (chapter.status === "scenes_ready") {
    return { label: "场景就绪", className: "is-live" };
  }
  if (chapter.status === "outline_ready") {
    return { label: "大纲就绪", className: "" };
  }
  return { label: formatChapterStatus(chapter.status), className: "" };
}

function renderDemoChapterList(project) {
  return project.chapters
    .map((chapter) => {
      const status = getDemoChapterStatus(chapter);
      const isSelected = chapter.id === state.activeChapterId;
      const statusLabel = status.label === "Review 中" ? "审校中" : status.label === "场景就绪" ? "已完成" : "草稿";
      return `
        <button
          class="demo-list-card demo-chapter-card ${isSelected ? "is-selected" : ""}"
          type="button"
          data-select-chapter="${chapter.id}"
        >
          <span class="demo-list-card-body">
            <span class="demo-list-card-kicker">第 ${escapeHtml(chapter.order_index)} 章</span>
            <strong>${escapeHtml(chapter.title)}</strong>
            <span class="demo-chapter-card-meta">
              <span class="demo-chapter-card-status ${status.className}">
                <span class="demo-status-dot ${status.className}" aria-hidden="true"></span>
                ${escapeHtml(statusLabel)}
              </span>
              <span>${escapeHtml(chapter.scenes.length)} 场景</span>
            </span>
          </span>
          ${isSelected ? `<span class="demo-chapter-card-arrow" aria-hidden="true">›</span>` : `<span class="demo-status-dot ${status.className}" aria-hidden="true"></span>`}
        </button>
      `;
    })
    .join("");
}

function renderDemoCharacterList(project) {
  return project.characters
    .map((character) => {
      const avatar = escapeHtml(String(character.name || "角").slice(0, 1));
      return `
        <button
          class="demo-list-card demo-character-card"
          type="button"
          data-open-character-chat="${character.id}"
          aria-label="与 ${escapeHtml(character.name)} 单独对话"
        >
          <span class="demo-character-avatar">${avatar}</span>
          <span class="demo-list-card-body">
            <strong>${escapeHtml(character.name)}</strong>
            <span>${escapeHtml(character.role || "智能 NPC")}</span>
          </span>
          <span class="demo-chat-cue">单聊</span>
        </button>
      `;
    })
    .join("");
}

function renderDemoWorldList(project) {
  const storyBible = project.story_bible || {};
  const worldCards = [
    { label: "核心设定", value: storyBible.world_notes || project.logline },
    { label: "对白规则", value: storyBible.style_notes || project.tone },
    { label: "互动边界", value: (storyBible.writing_rules || []).join(" / ") || storyBible.addressing_rules },
  ];

  return worldCards
    .map(
      (card) => `
        <article class="demo-world-card">
          <span>${escapeHtml(card.label)}</span>
          <p>${escapeHtml(card.value || "待补充")}</p>
        </article>
      `,
    )
    .join("");
}

function renderDemoIcon(name) {
  const icons = {
    book: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 0 4 24V4.5A2.5 2.5 0 0 1 6.5 2Z"/></svg>',
    users: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    globe: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10Z"/></svg>',
    save: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/></svg>',
    download: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg>',
    settings: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 8.92 4.6H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.64 0 1.22.38 1.48.97.08.2.12.41.12.63s-.04.43-.12.63c-.26.59-.84.97-1.48.97Z"/></svg>',
    wand: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 4V2"/><path d="M15 16v-2"/><path d="M8 9h2"/><path d="M20 9h2"/><path d="m17.8 11.8 1.4 1.4"/><path d="m4.8 4.8 1.4 1.4"/><path d="m17.8 6.2 1.4-1.4"/><path d="m4.8 13.2 1.4-1.4"/><path d="m3 21 9-9"/><path d="M12.2 6.2a3 3 0 1 1 4.24 4.24 3 3 0 0 1-4.24-4.24Z"/></svg>',
    sparkles: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3Z"/><path d="M19 2v4"/><path d="M21 4h-4"/><path d="M5 16v6"/><path d="M8 19H2"/></svg>',
    message: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"/></svg>',
    image: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.6-3.6a2 2 0 0 0-2.8 0L6 20"/></svg>',
    pin: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-6-5.33-6-11a6 6 0 0 1 12 0c0 5.67-6 11-6 11Z"/><circle cx="12" cy="10" r="2.5"/></svg>',
  };
  return icons[name] || "";
}

function findDemoSpeakerCharacter(project, speaker) {
  const normalizedSpeaker = String(speaker || "").replace(/\s+/g, "");
  const projectCharacters = Array.isArray(project?.characters) ? project.characters : [];
  const libraryCharacters =
    typeof state !== "undefined" && Array.isArray(state.characterLibrary) ? state.characterLibrary : [];
  const candidates = [...projectCharacters, ...libraryCharacters];
  return (
    candidates.find((character) => {
      const name = String(character?.name || "").replace(/\s+/g, "");
      const compactSpeaker = normalizedSpeaker.replace(/导师|学员|伙伴/g, "");
      const compactName = name.replace(/导师|学员|伙伴/g, "");
      return (
        normalizedSpeaker.includes(name) ||
        name.includes(normalizedSpeaker) ||
        (compactSpeaker && compactSpeaker === compactName)
      );
    }) || null
  );
}

function getDemoSpeakerVariant(project, speaker) {
  const character = findDemoSpeakerCharacter(project, speaker);
  if (character?.id === 101 || String(speaker || "").includes("薇岚")) {
    return "is-mentor";
  }
  if (character?.id === 102 || String(speaker || "").includes("霁光")) {
    return "is-sprite";
  }
  return "is-rival";
}

function renderDemoDialogueLine(project, scene, dialogue) {
  const speaker = String(dialogue.speaker || "角色");
  const avatar = escapeHtml(speaker.slice(0, 1));
  const emotion = String(dialogue.parenthetical || scene.emotional_tone || "").trim();
  return `
    <article class="demo-dialogue-line">
      <span class="demo-dialogue-avatar ${getDemoSpeakerVariant(project, speaker)}">${avatar}</span>
      <div class="demo-dialogue-line-body">
        <div class="demo-dialogue-line-head">
          <strong>${escapeHtml(speaker)}</strong>
          ${emotion ? `<span class="demo-dialogue-emotion">${escapeHtml(emotion)}</span>` : ""}
        </div>
        <p>${escapeHtml(dialogue.content || "")}</p>
      </div>
    </article>
  `;
}

function renderDemoDialogueWorkbench(project, chapter) {
  const expandedScene = chapter.scenes.find(
    (scene) => Number(state.demoExpandedSceneId || 0) === Number(scene.id),
  );
  if (!expandedScene || !expandedScene.dialogue_blocks?.length) {
    return "";
  }

  const sceneIndex = chapter.scenes.findIndex((scene) => Number(scene.id) === Number(expandedScene.id));
  return `
    <section class="demo-dialogue-workbench">
      <div class="demo-dialogue-workbench-head">
        <div class="demo-dialogue-workbench-copy">
          <span class="demo-dialogue-workbench-kicker">
            <span class="demo-toolbar-icon" aria-hidden="true">${renderDemoIcon("sparkles")}</span>
            NPC 对话预览
          </span>
          <div class="demo-dialogue-workbench-title-row">
            <h3>${escapeHtml(expandedScene.title)}</h3>
            <span class="demo-dialogue-scene-label">Scene ${escapeHtml(sceneIndex + 1)} - ${escapeHtml(expandedScene.title)}</span>
          </div>
        </div>
      </div>
      <div class="demo-dialogue-list">
        ${expandedScene.dialogue_blocks.map((dialogue) => renderDemoDialogueLine(project, expandedScene, dialogue)).join("")}
      </div>
      <div class="demo-dialogue-actions">
        <button class="demo-toolbar-button demo-toolbar-ghost" type="button">编辑对话</button>
        <button class="demo-toolbar-button demo-toolbar-soft" type="button">
          <span class="demo-toolbar-icon" aria-hidden="true">${renderDemoIcon("wand")}</span>
          <span>AI 优化润色</span>
        </button>
      </div>
    </section>
  `;
}

function renderDemoSidebar(project) {
  const activeTab = state.demoSidebarTab || "chapters";
  const panels = {
    chapters: renderDemoChapterList(project),
    characters: renderDemoCharacterList(project),
    world: renderDemoWorldList(project),
  };

  return `
    <aside class="demo-sidebar" aria-label="剧情资源">
      <nav class="demo-sidebar-tabs figma-sidebar-tabs" aria-label="剧情资源分类">
        <button class="${activeTab === "chapters" ? "is-active" : ""}" type="button" data-demo-sidebar-tab="chapters">
          <span class="demo-tab-icon" aria-hidden="true">${renderDemoIcon("book")}</span>
          <span>章节</span>
        </button>
        <button class="${activeTab === "characters" ? "is-active" : ""}" type="button" data-demo-sidebar-tab="characters">
          <span class="demo-tab-icon" aria-hidden="true">${renderDemoIcon("users")}</span>
          <span>角色</span>
        </button>
        <button class="${activeTab === "world" ? "is-active" : ""}" type="button" data-demo-sidebar-tab="world">
          <span class="demo-tab-icon" aria-hidden="true">${renderDemoIcon("globe")}</span>
          <span>世界</span>
        </button>
      </nav>
      <div class="demo-sidebar-scroll">
        ${panels[activeTab] || panels.chapters}
      </div>
    </aside>
  `;
}

function getDemoSceneStatus(scene, chapter) {
  if (scene.dialogue_blocks?.length) {
    return { label: "已完成", className: "is-live", progress: null };
  }
  return { label: "草稿", className: "", progress: null };
}

function renderDemoSceneCard(scene, index, chapter) {
  const status = getDemoSceneStatus(scene, chapter);
  const isExpanded = Number(state.demoExpandedSceneId || 0) === Number(scene.id);
  const summary = scene.objective || scene.visual_prompt || "场景目标待补充";
  const sceneStatusLabel = status.label === "Reviewer 待处理" ? "Reviewer 待处理" : status.label;
  return `
    <article class="demo-scene-card ${isExpanded ? "is-expanded" : ""} ${status.className}">
      <button class="demo-scene-trigger" type="button" data-demo-expand-scene="${scene.id}" aria-pressed="${isExpanded ? "true" : "false"}">
        <span class="demo-scene-number">${escapeHtml(index + 1)}</span>
        <span class="demo-scene-card-body">
          <span class="demo-scene-card-head">
            <strong>${escapeHtml(scene.title)}</strong>
            <span class="demo-scene-card-status">
              <span class="demo-status-dot ${status.className}" aria-hidden="true"></span>
              ${escapeHtml(sceneStatusLabel)}
            </span>
          </span>
          <span class="demo-scene-copy">${escapeHtml(summary)}</span>
        </span>
      </button>
      <div class="demo-scene-meta">
        <span class="demo-scene-meta-item"><span class="demo-toolbar-icon" aria-hidden="true">${renderDemoIcon("message")}</span>${escapeHtml(scene.dialogue_blocks.length)} 段对话</span>
        <span class="demo-scene-meta-item"><span class="demo-toolbar-icon" aria-hidden="true">${renderDemoIcon("image")}</span>${escapeHtml(scene.illustrations.length)} 张场景图</span>
        <span class="demo-scene-meta-item"><span class="demo-toolbar-icon" aria-hidden="true">${renderDemoIcon("pin")}</span>${escapeHtml(scene.location || "地点待定")}</span>
      </div>
      ${
        status.progress
          ? `
            <div class="demo-progress-row">
              <span>正在等待 Reviewer 处理建议</span>
              <strong>${escapeHtml(status.progress)}%</strong>
              <div class="demo-progress-track"><span style="width: ${escapeHtml(status.progress)}%"></span></div>
            </div>
          `
          : ""
      }
    </article>
  `;
}

function renderDemoMainStage(project) {
  const chapter = getActiveChapter() || project.chapters[0];
  if (!chapter) {
    return `
      <main class="demo-main-stage">
        <section class="demo-empty-panel">
          <h2>暂无可展示章节</h2>
          <p>Demo 数据加载后会在这里展示场景流。</p>
        </section>
      </main>
    `;
  }

  const status = getDemoChapterStatus(chapter);
  const dialogueCount = chapter.scenes.reduce((sum, scene) => sum + scene.dialogue_blocks.length, 0);
  const imageCount = chapter.scenes.reduce((sum, scene) => sum + scene.illustrations.length, 0);
  const heroSummary = chapter.summary || project.logline;
  const statusLabel = status.label === "Review 中" ? "Review 中" : `${status.label}`;
  const activeMode = state.demoStageMode || "default";

  return `
    <main class="demo-main-stage">
      <div class="demo-main-stage-shell">
        <section class="demo-chapter-hero">
          <div class="demo-chapter-hero-top">
            <div class="demo-chapter-hero-copy">
              <span class="demo-kicker">第 ${escapeHtml(chapter.order_index)} 章</span>
              <h2>${escapeHtml(chapter.title)}</h2>
              <p class="demo-chapter-hero-summary">${escapeHtml(heroSummary)}</p>
            </div>
            <div class="demo-chapter-actions">
              <button class="demo-hero-action-button" type="button" aria-label="查看角色关系">
                <span class="demo-hero-action-icon" aria-hidden="true">${renderDemoIcon("users")}</span>
                <span>角色关系</span>
              </button>
              <button class="demo-hero-action-button" type="button" aria-label="查看场景生成状态">
                <span class="demo-hero-action-icon" aria-hidden="true">${renderDemoIcon("wand")}</span>
                <span>生成场景</span>
              </button>
            </div>
          </div>
          <div class="demo-chapter-metrics">
            <span><i class="demo-metric-dot is-green" aria-hidden="true"></i><b>${escapeHtml(chapter.scenes.length)}</b> 个场景</span>
            <span><i class="demo-metric-dot is-blue" aria-hidden="true"></i><b>${escapeHtml(dialogueCount)}</b> 段对话</span>
            <span><i class="demo-metric-dot is-purple" aria-hidden="true"></i><b>${escapeHtml(imageCount)}</b> 张场景图</span>
            <span class="demo-chapter-status-pill ${status.className}">${escapeHtml(statusLabel)}</span>
          </div>
        </section>

        <section class="demo-scene-section">
          <div class="demo-section-head">
            <h3>场景流程</h3>
            <div class="stage-mode-switcher" aria-label="章节生成状态">
              <button class="stage-mode-pill ${activeMode === "default" ? "is-active" : ""}" type="button" data-demo-stage-mode="default">默认工作态</button>
              <button class="stage-mode-pill is-tone-blue ${activeMode === "generating" ? "is-active" : ""}" type="button" data-demo-stage-mode="generating">AI 生成中</button>
              <button class="stage-mode-pill is-tone-gold ${activeMode === "reviewing" ? "is-active" : ""}" type="button" data-demo-stage-mode="reviewing">Reviewer 待处理</button>
            </div>
          </div>
          <div class="demo-scene-list">
            ${
              chapter.scenes.length
                ? chapter.scenes.map((scene, index) => renderDemoSceneCard(scene, index, chapter)).join("")
                : `<article class="demo-empty-panel"><h3>本章仍在大纲阶段</h3><p>${escapeHtml(chapter.chapter_goal || "后续可继续拆成场景。")}</p></article>`
            }
          </div>
        </section>
        ${renderDemoDialogueWorkbench(project, chapter)}
      </div>
    </main>
  `;
}

function renderDemoAgentPanel(project) {
  const activeTab = state.demoAgentTab || "agent";
  const workbench = buildAgentWorkbench(project, {
    selectedJobDetail: state.selectedJobDetail,
    activeChapterId: state.activeChapterId,
  });
  const reviewerItems = (state.selectedJobDetail?.pending_interventions || [])
    .map((item) => ({
      title: formatInterventionLabel(item.intervention_type),
      scene: `第 ${getActiveChapter()?.order_index || 1} 章`,
      message: item.reviewer_notes || item.suggested_guidance,
      type: "warning",
    }))
    .concat([
      {
        title: "节奏建议",
        scene: "Scene 1",
        message: "把连续说明拆成导师追问与精灵补充，让玩家更快进入可互动状态。",
        type: "suggestion",
      },
    ]);

  function getTaskTypeLabel(item) {
    const title = String(item.title || "");
    if (title.includes("导出")) {
      return "导出";
    }
    if (title.includes("场景")) {
      return "场景";
    }
    if (title.includes("正文")) {
      return "正文";
    }
    if (title.includes("大纲")) {
      return "大纲";
    }
    return title.split("生成")[0] || "任务";
  }

  function getTaskStatusLabel(item) {
    if (item.isFocus) {
      return "当前焦点";
    }
    if (item.status === "awaiting_user") {
      return "待确认";
    }
    if (item.status === "processing") {
      return "进行中";
    }
    if (item.status === "completed") {
      return "已完成";
    }
    return "排队中";
  }

  function getTaskSortWeight(item) {
    if (item.isFocus) {
      return 0;
    }
    if (item.status === "awaiting_user") {
      return 1;
    }
    if (item.status === "processing") {
      return 2;
    }
    if (item.status === "queued") {
      return 3;
    }
    if (item.status === "completed") {
      return 4;
    }
    return 5;
  }

  const sortedHistory = [...workbench.history]
    .sort((left, right) => {
      const weightDiff = getTaskSortWeight(left) - getTaskSortWeight(right);
      if (weightDiff !== 0) {
        return weightDiff;
      }
      return Number(right.jobId || 0) - Number(left.jobId || 0);
    });

  const taskCards = sortedHistory.length
    ? sortedHistory.slice(0, 4).map(
        (item) => `
          <button class="demo-task-card ${item.isFocus ? "is-focus" : ""}" type="button" data-select-job="${item.jobId}">
            <div class="demo-task-card-head">
              <span class="demo-task-type">${escapeHtml(getTaskTypeLabel(item))}</span>
              <span class="demo-task-status is-subtle">${escapeHtml(getTaskStatusLabel(item))}</span>
            </div>
            <strong>${escapeHtml(item.title)}</strong>
            <span class="demo-task-summary">${escapeHtml(item.summary)}</span>
            <div class="demo-task-meta">
              <span>${escapeHtml(item.chapterLabel || item.currentStepLabel || "StoryCraft Demo")}</span>
              <span>${escapeHtml(item.progressLabel || "100%")}</span>
            </div>
            ${
              item.progressLabel
                ? `<div class="demo-progress-track"><span style="width: ${escapeHtml(item.progressLabel.replace(/[^0-9]/g, "") || 100)}%"></span></div>`
                : ""
            }
          </button>
        `,
      )
    : [
        `<article class="demo-task-card"><strong>暂无任务</strong><span>生成任务会展示在这里。</span></article>`,
      ];

  const reviewerCards = reviewerItems.map(
    (item) => `
      <article class="demo-review-card ${item.type === "warning" ? "is-warn" : ""}">
        <div class="demo-review-card-head">
          <span>${escapeHtml(item.scene)}</span>
          <span class="demo-task-status is-subtle">${item.type === "warning" ? "警告" : "建议"}</span>
        </div>
        <strong>${escapeHtml(item.title)}</strong>
        <p>${escapeHtml(item.message)}</p>
      </article>
    `,
  );

  return `
    <aside class="demo-ai-panel" aria-label="AI 协作面板">
      <nav class="demo-agent-tabs figma-agent-tabs" aria-label="AI 面板分类">
        <button class="${activeTab === "agent" ? "is-active" : ""}" type="button" data-demo-agent-tab="agent">
          <span class="demo-agent-tab-icon" aria-hidden="true">${renderDemoIcon("sparkles")}</span>
          <span>AI Agent</span>
        </button>
        <button class="${activeTab === "reviewer" ? "is-active" : ""}" type="button" data-demo-agent-tab="reviewer">
          <span>Reviewer</span>
          <span class="demo-agent-count-badge" aria-label="${escapeHtml(reviewerItems.length)} 条审校反馈">${escapeHtml(reviewerItems.length)}</span>
        </button>
      </nav>
      <div class="demo-ai-scroll">
        ${
          activeTab === "reviewer"
            ? `
              <div class="demo-panel-label">审校反馈</div>
              <div class="demo-review-list">${reviewerCards.join("")}</div>
            `
            : `
              <div class="demo-panel-label">生成任务队列</div>
              <div class="demo-task-list">${taskCards.join("")}</div>
            `
        }
      </div>
    </aside>
  `;
}

function renderDemoProjectWorkspace(project) {
  return `
    <div class="figma-demo-workspace">
      <header class="figma-demo-topbar">
        <div class="demo-brand">
          <span class="demo-brand-mark" aria-hidden="true">✦</span>
          <strong>StoryCraft Studio</strong>
        </div>
        <div class="demo-topbar-meta">
          <span>当前项目</span>
          <strong>${escapeHtml(project.title)}</strong>
        </div>
        <div class="demo-topbar-meta">
          <span>当前章节</span>
          <strong>${escapeHtml(getActiveChapter()?.title || project.chapters[0]?.title || "未选择")}</strong>
        </div>
        <div class="demo-topbar-actions">
          <button class="demo-toolbar-button demo-toolbar-ghost" type="button"><span class="demo-toolbar-icon" aria-hidden="true">${renderDemoIcon("save")}</span><span>保存草稿</span></button>
          <button class="demo-toolbar-button is-primary" type="button"><span class="demo-toolbar-icon" aria-hidden="true">${renderDemoIcon("download")}</span><span>导出交付</span></button>
          <button class="demo-square-button" type="button" aria-label="设置"><span class="demo-toolbar-icon" aria-hidden="true">${renderDemoIcon("settings")}</span></button>
        </div>
      </header>
      <div class="figma-demo-grid">
        ${renderDemoSidebar(project)}
        ${renderDemoMainStage(project)}
        ${renderDemoAgentPanel(project)}
      </div>
    </div>
  `;
}

function renderProjectWorkspace() {
  const preservedScrollState = captureScrollState(getWorkspaceScrollTargets());
  syncWorkspaceMode();
  if (!state.currentProject) {
    els.emptyState.classList.remove("hidden");
    els.projectWorkspace.classList.add("hidden");
    els.projectWorkspace.style.removeProperty("--workspace-grid-height");
    els.exportReadyBanner.innerHTML = "";
    els.exportReadyBanner.classList.add("hidden");
    els.chapterTabs.innerHTML = "";
    els.chapterDetail.innerHTML = "";
    els.chapterPager.innerHTML = "";
    els.agentFocus.innerHTML = "";
    els.jobList.innerHTML = "";
    els.jobTrace.innerHTML = "";
    els.exportList.innerHTML = "";
    els.projectHeroMeta.innerHTML = "";
    els.deleteProjectButton.dataset.deleteProject = "";
    els.deleteProjectButton.disabled = true;
    els.openStoryBibleButton.disabled = true;
    els.storyBiblePanel.innerHTML = "";
    els.storyBibleDetail.innerHTML = "";
    els.characterLibrarySummary.textContent = `全局角色库 ${state.characterLibrary.length} 个`;
    els.workspaceHeading.textContent = "独立项目创作中";
    closeCharacterChat();
    closeStoryBibleModal();
    renderCharacterModal();
    updateAuthUI();
    restoreScrollState(preservedScrollState, (key) => getWorkspaceScrollTargets()[key]);
    return;
  }

  const project = state.currentProject;
  els.emptyState.classList.add("hidden");
  els.projectWorkspace.classList.remove("hidden");
  els.projectWorkspace.dataset.layoutMode = state.layoutMode;
  if (demoSession) {
    els.projectWorkspace.classList.add("is-figma-demo");
    els.projectWorkspace.dataset.layoutMode = "wide";
    els.projectWorkspace.innerHTML = renderDemoProjectWorkspace(project);
    renderCharacterChat();
    updateAuthUI();
    restoreScrollState(preservedScrollState, (key) => getWorkspaceScrollTargets()[key]);
    return;
  }

  els.projectWorkspace.classList.remove("is-figma-demo");
  els.deleteProjectButton.disabled = false;
  els.openStoryBibleButton.disabled = false;
  els.workspaceHeading.textContent = `《${project.title}》工作空间`;
  els.projectHero.style.backgroundImage = project.cover_image_url ? `url(${project.cover_image_url})` : "";
  els.projectHeroMeta.innerHTML = `
    <p class="eyebrow">${escapeHtml(project.genre)} · ${escapeHtml(project.era)}</p>
    <h2>${escapeHtml(project.title)}</h2>
    <p>${escapeHtml(project.logline)}</p>
    <div class="hero-metrics">
      <span class="status-chip">${project.target_chapter_count} 章</span>
      <span class="status-chip">${escapeHtml(project.target_length)}</span>
      <span class="status-chip">${escapeHtml(project.status)}</span>
    </div>
  `;
  els.deleteProjectButton.dataset.deleteProject = String(project.id);

  renderStoryBiblePanel(project);
  renderCharacters(project);
  renderCharacterModal();
  renderChapterTabs(project);
  renderChapterDetail(project);
  renderAgentFocusPanel(project);
  renderJobList(project);
  renderTracePanel();
  renderExports(project);
  renderExportReadyBanner();
  renderCharacterChat();
  updateAuthUI();
  window.requestAnimationFrame(syncWorkspaceMetrics);
  restoreScrollState(preservedScrollState, (key) => getWorkspaceScrollTargets()[key]);
}

async function loadJobDetail(jobId) {
  state.selectedJobId = Number(jobId);
  state.selectedJobDetail = await api(`/api/jobs/${jobId}`);
  if (state.currentProject && state.selectedJobDetail.chapter_id) {
    state.activeChapterId = resolveActiveChapterId(state.currentProject, state.selectedJobDetail.chapter_id);
  }
  syncSelectedJobStream();
}

async function loadCharacterLibrary() {
  if (!state.token) {
    state.characterLibrary = [];
    renderCharacterModal();
    return;
  }
  state.characterLibrary = await api("/api/characters");
  renderCharacterModal();
}

async function loadProjects() {
  state.projects = await api("/api/projects");
  await loadCharacterLibrary();
  renderDashboard();
  if (!window.location.hash) {
    const initialRoute = demoSession ? resolveDemoInitialRoute(demoSession) : { view: "dashboard", projectId: null };
    replaceStudioHash(initialRoute.view, initialRoute.projectId);
  }
  await syncStudioRoute();
}

async function loadProjectDetail(projectId, options = {}) {
  state.view = "workspace";
  state.currentProjectId = Number(projectId);
  state.currentProject = await api(`/api/projects/${projectId}`);
  const requestedChapterId = options.focusChapterId ?? state.activeChapterId;
  state.activeChapterId = resolveActiveChapterId(state.currentProject, requestedChapterId);

  const availableJobIds = new Set(state.currentProject.jobs.map((job) => job.id));
  if (options.focusJobId !== undefined) {
    state.selectedJobId = options.focusJobId;
  } else if (state.selectedJobId && !availableJobIds.has(state.selectedJobId)) {
    state.selectedJobId = state.currentProject.jobs[0]?.id ?? null;
  } else if (!state.selectedJobId && state.currentProject.jobs[0]) {
    state.selectedJobId = state.currentProject.jobs[0].id;
  }

  if (state.selectedJobId && availableJobIds.has(state.selectedJobId)) {
    try {
      await loadJobDetail(state.selectedJobId);
    } catch {
      closeJobStream();
      state.selectedJobDetail = null;
    }
  } else {
    closeJobStream();
    state.selectedJobDetail = null;
  }

  await Promise.all([loadStoryBibleRevisions(projectId), loadChapterRevisions(state.activeChapterId)]);

  if (state.activeStoryBibleDiffId && !state.storyBibleRevisions.some((revision) => revision.id === state.activeStoryBibleDiffId)) {
    state.activeStoryBibleDiffId = null;
  }
  const activeChapterRevisions = state.chapterRevisions[state.activeChapterId] || [];
  if (
    state.activeChapterRevisionDiffId &&
    !activeChapterRevisions.some((revision) => revision.id === state.activeChapterRevisionDiffId)
  ) {
    state.activeChapterRevisionDiffId = null;
  }

  renderDashboard();
  renderProjectWorkspace();
  syncSelectedJobStream();
}

async function loadStoryBibleRevisions(projectId) {
  if (!projectId) {
    state.storyBibleRevisions = [];
    return;
  }
  try {
    state.storyBibleRevisions = await api(`/api/projects/${projectId}/story-bible/revisions`);
  } catch {
    state.storyBibleRevisions = [];
  }
}

async function loadStoryBibleRevisionDiff(projectId, revisionId) {
  if (!projectId || !revisionId) {
    return null;
  }
  const cacheKey = `${projectId}:${revisionId}`;
  if (!state.storyBibleDiffs[cacheKey]) {
    state.storyBibleDiffs[cacheKey] = await api(`/api/projects/${projectId}/story-bible/revisions/${revisionId}/diff`);
  }
  return state.storyBibleDiffs[cacheKey];
}

async function loadChapterRevisions(chapterId) {
  const normalizedChapterId = Number(chapterId || 0);
  if (!normalizedChapterId) {
    return;
  }
  try {
    state.chapterRevisions[normalizedChapterId] = await api(`/api/chapters/${normalizedChapterId}/revisions`);
  } catch {
    state.chapterRevisions[normalizedChapterId] = [];
  }
}

async function loadChapterRevisionDiff(chapterId, revisionId) {
  const normalizedChapterId = Number(chapterId || 0);
  const normalizedRevisionId = Number(revisionId || 0);
  if (!normalizedChapterId || !normalizedRevisionId) {
    return null;
  }
  if (!state.chapterRevisionDiffs[normalizedChapterId]) {
    state.chapterRevisionDiffs[normalizedChapterId] = {};
  }
  if (!state.chapterRevisionDiffs[normalizedChapterId][normalizedRevisionId]) {
    state.chapterRevisionDiffs[normalizedChapterId][normalizedRevisionId] = await api(
      `/api/chapters/${normalizedChapterId}/revisions/${normalizedRevisionId}/diff`,
    );
  }
  return state.chapterRevisionDiffs[normalizedChapterId][normalizedRevisionId];
}

async function trackJob(jobId, options = {}) {
  state.activeJobs.add(jobId);
  state.selectedJobId = jobId;
  if (options.focusChapterId) {
    state.activeChapterId = Number(options.focusChapterId);
  }
  try {
    await loadJobDetail(jobId);
  } catch {
    state.selectedJobDetail = null;
  }
  renderProjectWorkspace();
  syncSelectedJobStream();
  ensurePolling();
}

function ensurePolling() {
  if (state.pollHandle || !state.activeJobs.size) {
    return;
  }

  state.pollHandle = window.setInterval(async () => {
    if (!state.activeJobs.size) {
      window.clearInterval(state.pollHandle);
      state.pollHandle = null;
      return;
    }

    for (const jobId of [...state.activeJobs]) {
      try {
        const job = await api(`/api/jobs/${jobId}`);
        if (state.selectedJobId === jobId) {
          state.selectedJobDetail = job;
        }
        if (isTerminalJobStatus(job.status)) {
          await handleTerminalJob(job);
        } else if (state.selectedJobId === jobId) {
          renderWorkspaceDynamicPanels();
        }
      } catch (error) {
        state.activeJobs.delete(jobId);
        showToast(error.message);
      }
    }

    if (!state.activeJobs.size && state.pollHandle) {
      window.clearInterval(state.pollHandle);
      state.pollHandle = null;
    }
  }, 900);
}

authTabButtons.forEach((button) => {
  button.addEventListener("click", () => setAuthMode(button.dataset.authMode));
});

els.authForm.addEventListener(
  "invalid",
  (event) => {
    event.preventDefault();
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
      return;
    }
    showAuthFeedback(getAuthValidationMessage(state.authMode, target));
  },
  true,
);

els.authForm.addEventListener("input", () => {
  clearAuthFeedback();
});

els.authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const validation = validateAuthFields(state.authMode, {
    email: els.authEmail.value,
    password: els.authPassword.value,
    penName: els.authPenName.value,
  });
  if (validation) {
    showAuthFeedback(validation.message);
    const focusTarget =
      validation.field === "email"
        ? els.authEmail
        : validation.field === "password"
          ? els.authPassword
          : els.authPenName;
    focusTarget?.focus();
    return;
  }

  try {
    clearAuthFeedback();
    setAuthSubmitBusy(true);
    const payload =
      state.authMode === "register"
        ? {
            email: els.authEmail.value.trim(),
            password: els.authPassword.value,
            pen_name: els.authPenName.value.trim(),
          }
        : {
            email: els.authEmail.value.trim(),
            password: els.authPassword.value,
          };

    const endpoint = state.authMode === "register" ? "/api/auth/register" : "/api/auth/login";
    const data = await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
    setSession(data.user, data.token);
    state.view = "dashboard";
    if (!window.location.hash) {
      replaceStudioHash("dashboard");
    }
    updateAuthUI();
    await loadProjects();
    showToast(state.authMode === "register" ? "欢迎来到工作台" : "欢迎回来");
  } catch (error) {
    const feedback = getAuthErrorFeedback(state.authMode, error.message);
    if (feedback.switchMode) {
      setAuthMode(feedback.switchMode);
    }
    showAuthFeedback(feedback.message, feedback.tone);
    showToast(feedback.message);
  } finally {
    setAuthSubmitBusy(false);
  }
});

els.logoutButton.addEventListener("click", () => {
  if (demoSession) {
    showDemoReadOnlyToast();
    return;
  }
  clearSession();
  replaceStudioHash("dashboard");
  updateAuthUI();
  renderDashboard();
  renderProjectWorkspace();
  showToast("已退出登录");
});

els.projectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (demoSession) {
    showDemoReadOnlyToast();
    return;
  }
  let createdProjectId = null;
  try {
    await withSubmitForm(event, async (form) => {
      const formData = new FormData(form);
      const payload = buildProjectPayload(Object.fromEntries(formData.entries()));
      const project = await api("/api/projects", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      createdProjectId = project.id;
      state.activeChapterId = null;
      state.selectedJobId = null;
      state.selectedJobDetail = null;
      form.reset();
    });
    await loadProjects();
    if (createdProjectId) {
      await navigateToWorkspace(createdProjectId, { forceReload: true });
    }
    showToast("作品已创建，已进入工作空间");
  } catch (error) {
    showToast(error.message);
  }
});

els.newCharacterButton.addEventListener("click", () => {
  openCharacterModal("create");
});

els.characterChatForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  sendCharacterChatMessage();
});

els.characterChatInput?.addEventListener("input", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) {
    return;
  }
  state.characterChatDraft = target.value;
});

els.characterChatInput?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") {
    return;
  }
  event.preventDefault();
  sendCharacterChatMessage();
});

els.openCharacterLibraryButton.addEventListener("click", () => {
  openCharacterModal("library");
});

els.openStoryBibleButton.addEventListener("click", () => {
  openStoryBibleModal();
});

els.closeCharacterModalButton.addEventListener("click", () => {
  closeCharacterModal();
});

els.closeStoryBibleModalButton.addEventListener("click", () => {
  closeStoryBibleModal();
});

characterModalTabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setCharacterModalMode(button.dataset.characterModalTab);
    renderCharacterModal();
  });
});

els.characterCreateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (demoSession) {
    showDemoReadOnlyToast();
    return;
  }
  let attachedToCurrentProject = false;
  try {
    await withSubmitForm(event, async (form) => {
      const formData = new FormData(form);
      attachedToCurrentProject = Boolean(state.currentProjectId && els.attachCharacterToProject.checked);
      if (attachedToCurrentProject) {
        formData.set("project_id", String(state.currentProjectId));
      } else {
        formData.delete("project_id");
      }
      await api("/api/characters", {
        method: "POST",
        body: formData,
      });
      form.reset();
    });
    await loadCharacterLibrary();
    if (state.currentProjectId) {
      await loadProjectDetail(state.currentProjectId);
    } else {
      renderProjectWorkspace();
    }
    closeCharacterModal();
    showToast(attachedToCurrentProject ? "角色已创建并加入当前作品" : "角色已加入角色库");
  } catch (error) {
    showToast(error.message);
  }
});

document.addEventListener("submit", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLFormElement) || target.id !== "storyBibleForm") {
    return;
  }
  event.preventDefault();
  if (demoSession) {
    showDemoReadOnlyToast();
    return;
  }
  if (!state.currentProject) {
    return;
  }
  try {
    const formData = new FormData(target);
    const payload = buildStoryBiblePayload(Object.fromEntries(formData.entries()));
    await api(`/api/projects/${state.currentProject.id}/story-bible`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    await loadProjectDetail(state.currentProject.id, { focusChapterId: state.activeChapterId });
    showToast("Story Bible 已保存为新的设定版本");
  } catch (error) {
    showToast(error.message);
  }
});

els.generateOutlineButton.addEventListener("click", async () => {
  if (!state.currentProjectId) {
    return;
  }
  if (demoSession) {
    showDemoReadOnlyToast();
    return;
  }
  try {
    const job = await api(`/api/projects/${state.currentProjectId}/generate/outline`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    await trackJob(job.id);
    showToast("章节大纲生成中");
  } catch (error) {
    showToast(error.message);
  }
});

els.createSnapshotButton.addEventListener("click", async () => {
  if (!state.currentProject) {
    return;
  }
  if (demoSession) {
    showDemoReadOnlyToast();
    return;
  }
  try {
    const payload = buildSnapshotPayload(state.currentProject.title, "");
    await api(`/api/projects/${state.currentProject.id}/snapshots`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await loadProjectDetail(state.currentProject.id, { focusChapterId: state.activeChapterId });
    showToast("已为当前作品创建快照");
  } catch (error) {
    showToast(error.message);
  }
});

els.duplicateProjectButton.addEventListener("click", async () => {
  if (!state.currentProject) {
    return;
  }
  if (demoSession) {
    showDemoReadOnlyToast();
    return;
  }
  try {
    const payload = buildProjectDuplicatePayload(state.currentProject.title, "");
    const duplicate = await api(`/api/projects/${state.currentProject.id}/duplicate`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await loadProjects();
    await navigateToWorkspace(duplicate.id, { forceReload: true });
    showToast("已创建项目副本，建议在副本里继续大改");
  } catch (error) {
    showToast(error.message);
  }
});

els.exportBundleButton.addEventListener("click", async () => {
  if (!state.currentProjectId) {
    return;
  }
  if (demoSession) {
    showDemoReadOnlyToast();
    return;
  }
  try {
    clearExportNotice();
    state.featuredExportId = null;
    renderExportReadyBanner();
    const job = await api(`/api/projects/${state.currentProjectId}/exports`, {
      method: "POST",
      body: JSON.stringify({ formats: ["pdf", "docx"] }),
    });
    await trackJob(job.id);
    showToast("导出任务已创建");
  } catch (error) {
    showToast(error.message);
  }
});

els.refreshProjectsButton.addEventListener("click", async () => {
  try {
    await loadProjects();
    showToast("已刷新");
  } catch (error) {
    showToast(error.message);
  }
});

els.backToDashboardButton.addEventListener("click", async () => {
  try {
    await navigateToDashboard();
  } catch (error) {
    showToast(error.message);
  }
});

els.returnToDashboardButton.addEventListener("click", async () => {
  try {
    await navigateToDashboard();
  } catch (error) {
    showToast(error.message);
  }
});

els.refreshWorkspaceButton.addEventListener("click", async () => {
  if (!state.currentProjectId) {
    return;
  }
  try {
    await loadProjectDetail(state.currentProjectId, { focusChapterId: state.activeChapterId });
    showToast("当前作品已刷新");
  } catch (error) {
    showToast(error.message);
  }
});

document.addEventListener("input", (event) => {
  const target = event.target;
  if (target instanceof HTMLTextAreaElement && target.dataset.interventionGuidance) {
    state.interventionDrafts[target.dataset.interventionGuidance] = target.value;
    return;
  }
  if (target instanceof HTMLTextAreaElement && target.dataset.illustrationGuidance) {
    patchIllustrationWorkbenchState(Number(target.dataset.illustrationGuidance), {
      extraGuidance: target.value,
    });
    return;
  }
  if (
    (target instanceof HTMLTextAreaElement || target instanceof HTMLInputElement) &&
    target.dataset.blockDraft
  ) {
    state.blockDrafts[target.dataset.blockDraft] = target.value;
    return;
  }
  if (
    (target instanceof HTMLTextAreaElement || target instanceof HTMLInputElement) &&
    target.dataset.sceneDraftField
  ) {
    const sceneId = Number(target.dataset.sceneDraftField);
    state.sceneDrafts[sceneId] = {
      ...(state.sceneDrafts[sceneId] || {}),
      [target.dataset.field]: target.value,
    };
    return;
  }
  if (
    (target instanceof HTMLTextAreaElement || target instanceof HTMLInputElement) &&
    target.dataset.dialogueDraftField
  ) {
    const dialogueId = Number(target.dataset.dialogueDraftField);
    state.dialogueDrafts[dialogueId] = {
      ...(state.dialogueDrafts[dialogueId] || {}),
      [target.dataset.field]: target.value,
    };
  }
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLSelectElement)) {
    return;
  }
  if (target.dataset.illustrationCount) {
    patchIllustrationWorkbenchState(Number(target.dataset.illustrationCount), {
      candidateCount: Number(target.value),
    });
  }
});

document.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  const action = target.closest(
    "[data-open-project], [data-demo-sidebar-tab], [data-demo-agent-tab], [data-demo-stage-mode], [data-demo-expand-scene], [data-delete-project], [data-open-character-modal], [data-open-story-bible-modal], [data-open-character-chat], [data-close-character-chat], [data-send-character-chat], [data-quick-character-reply], [data-attach-character], [data-detach-character], [data-delete-library-character], [data-close-character-modal], [data-close-story-bible-modal], [data-generate-draft], " +
      "[data-generate-scenes], [data-generate-illustrations], [data-select-illustration], [data-mark-canonical], [data-delete-illustration], " +
      "[data-delete-export], [data-dismiss-export-banner], [data-delete-job], [data-lock-chapter], [data-select-chapter], [data-select-job], " +
      "[data-retry-intervention], [data-dismiss-intervention], [data-character-modal-tab], [data-restore-revision], [data-view-story-bible-diff], [data-view-chapter-diff], [data-edit-block], [data-save-block], [data-cancel-block], [data-toggle-block-lock], [data-edit-scene], [data-save-scene], [data-cancel-scene], [data-toggle-scene-lock], [data-edit-dialogue], [data-save-dialogue], [data-cancel-dialogue], [data-toggle-dialogue-lock], [data-retry-job]",
  );
  if (!(action instanceof HTMLElement) || action.matches(":disabled")) {
    return;
  }

  try {
    const { dataset } = action;

    if (
      demoSession &&
      !dataset.openProject &&
      !dataset.demoSidebarTab &&
      !dataset.demoAgentTab &&
      !dataset.demoStageMode &&
      !dataset.demoExpandScene &&
      !dataset.openCharacterModal &&
      !dataset.openCharacterChat &&
      dataset.closeCharacterChat === undefined &&
      dataset.sendCharacterChat === undefined &&
      !dataset.quickCharacterReply &&
      dataset.openStoryBibleModal === undefined &&
      dataset.closeCharacterModal === undefined &&
      dataset.closeStoryBibleModal === undefined &&
      !dataset.characterModalTab &&
      !dataset.selectChapter &&
      !dataset.selectJob &&
      !dataset.selectIllustration &&
      !dataset.viewStoryBibleDiff &&
      !dataset.viewChapterDiff &&
      !dataset.dismissExportBanner &&
      !dataset.editBlock &&
      !dataset.cancelBlock &&
      !dataset.editScene &&
      !dataset.cancelScene &&
      !dataset.editDialogue &&
      !dataset.cancelDialogue
    ) {
      showDemoReadOnlyToast();
      return;
    }

    if (dataset.demoSidebarTab) {
      state.demoSidebarTab = dataset.demoSidebarTab;
      renderProjectWorkspace();
      return;
    }

    if (dataset.demoAgentTab) {
      state.demoAgentTab = dataset.demoAgentTab;
      renderProjectWorkspace();
      return;
    }

    if (dataset.demoStageMode) {
      state.demoStageMode = dataset.demoStageMode;
      renderProjectWorkspace();
      return;
    }

    if (dataset.demoExpandScene) {
      state.demoExpandedSceneId = state.demoExpandedSceneId === Number(dataset.demoExpandScene) ? null : Number(dataset.demoExpandScene);
      renderProjectWorkspace();
      return;
    }

    if (dataset.openProject) {
      await navigateToWorkspace(dataset.openProject, { forceReload: true });
      return;
    }

    if (dataset.openCharacterModal) {
      openCharacterModal(dataset.openCharacterModal);
      return;
    }

    if (dataset.openStoryBibleModal !== undefined) {
      openStoryBibleModal();
      return;
    }

    if (dataset.openCharacterChat) {
      openCharacterChat(dataset.openCharacterChat);
      return;
    }

    if (dataset.closeCharacterChat !== undefined) {
      closeCharacterChat();
      return;
    }

    if (dataset.quickCharacterReply) {
      state.characterChatDraft = dataset.quickCharacterReply;
      renderCharacterChat();
      return;
    }

    if (dataset.sendCharacterChat !== undefined) {
      sendCharacterChatMessage();
      return;
    }

    if (dataset.closeCharacterModal !== undefined) {
      closeCharacterModal();
      return;
    }

    if (dataset.closeStoryBibleModal !== undefined) {
      closeStoryBibleModal();
      return;
    }

    if (dataset.characterModalTab) {
      setCharacterModalMode(dataset.characterModalTab);
      renderCharacterModal();
      return;
    }

    if (dataset.selectChapter) {
      state.activeChapterId = Number(dataset.selectChapter);
      const nextChapter = getActiveChapter();
      const expandedSceneStillExists = nextChapter?.scenes?.some(
        (scene) => Number(scene.id) === Number(state.demoExpandedSceneId || 0),
      );
      if (!expandedSceneStillExists) {
        state.demoExpandedSceneId = null;
      }
      if (demoSession) {
        renderProjectWorkspace();
        return;
      }
      await loadChapterRevisions(state.activeChapterId);
      renderProjectWorkspace();
      return;
    }

    if (dataset.selectJob) {
      await loadJobDetail(dataset.selectJob);
      renderProjectWorkspace();
      return;
    }

    if (dataset.deleteProject) {
      const confirmed = window.confirm("删除作品后，角色、章节、剧照、导出与历史任务都会一并移除，且不可恢复。确定继续吗？");
      if (!confirmed) {
        return;
      }
      await api(`/api/projects/${dataset.deleteProject}`, { method: "DELETE" });
      if (Number(dataset.deleteProject) === state.currentProjectId) {
        state.currentProjectId = null;
        state.currentProject = null;
        state.activeChapterId = null;
        state.selectedJobId = null;
        state.selectedJobDetail = null;
        replaceStudioHash("dashboard");
      }
      await loadProjects();
      showToast("作品已删除");
      return;
    }

    if (dataset.attachCharacter) {
      if (!state.currentProjectId) {
        showToast("请先选择作品");
        return;
      }
      await api(`/api/projects/${state.currentProjectId}/characters/attach`, {
        method: "POST",
        body: JSON.stringify({ character_id: Number(dataset.attachCharacter) }),
      });
      await Promise.all([loadCharacterLibrary(), loadProjectDetail(state.currentProjectId)]);
      showToast("角色已加入当前作品");
      return;
    }

    if (dataset.detachCharacter) {
      if (!state.currentProjectId) {
        showToast("请先选择作品");
        return;
      }
      const confirmed = window.confirm("确定把这个角色从当前作品中移出吗？角色本体会继续保留在全局角色库里。");
      if (!confirmed) {
        return;
      }
      await api(`/api/projects/${state.currentProjectId}/characters/${dataset.detachCharacter}`, { method: "DELETE" });
      await Promise.all([loadCharacterLibrary(), loadProjectDetail(state.currentProjectId)]);
      showToast("角色已移出当前作品");
      return;
    }

    if (dataset.deleteLibraryCharacter) {
      const confirmed = window.confirm("确定彻底删除这个角色吗？它会从角色库以及所有挂接作品中移除，参考图和视觉档案也会一起删除。");
      if (!confirmed) {
        return;
      }
      await api(`/api/characters/${dataset.deleteLibraryCharacter}`, { method: "DELETE" });
      await loadCharacterLibrary();
      if (state.currentProjectId) {
        await loadProjectDetail(state.currentProjectId);
      } else {
        renderDashboard();
        renderProjectWorkspace();
      }
      showToast("角色已从角色库删除");
      return;
    }

    if (dataset.generateDraft) {
      const chapterId = Number(dataset.generateDraft);
      const chapter = findChapterById(chapterId);
      if (countProtectedContent(chapter).total) {
        const confirmed = window.confirm("这一章包含已锁定或人工编辑的内容。系统会尽量保留它们，但仍建议先创建快照。继续生成吗？");
        if (!confirmed) {
          return;
        }
      }
      const job = await api(`/api/chapters/${chapterId}/generate-draft`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      await trackJob(job.id, { focusChapterId: chapterId });
      showToast("章节正文生成中");
      return;
    }

    if (dataset.generateScenes) {
      const chapterId = Number(dataset.generateScenes);
      const chapter = findChapterById(chapterId);
      if (countProtectedContent(chapter).total) {
        const confirmed = window.confirm("这一章包含已锁定或人工编辑的内容。系统会尽量保留它们，但仍建议先创建快照。继续生成场景吗？");
        if (!confirmed) {
          return;
        }
      }
      const job = await api(`/api/chapters/${chapterId}/generate-scenes`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      await trackJob(job.id, { focusChapterId: chapterId });
      showToast("场景结构生成中");
      return;
    }

    if (dataset.generateIllustrations) {
      const sceneId = Number(dataset.generateIllustrations);
      const scene = findSceneById(sceneId);
      const chapter = findSceneChapter(sceneId);
      const requestPayload = buildIllustrationRequestPayload(getIllustrationWorkbenchState(sceneId));
      const job = await api(`/api/scenes/${sceneId}/generate-illustrations`, {
        method: "POST",
        body: JSON.stringify(requestPayload),
      });
      await trackJob(job.id, { focusChapterId: chapter?.id });
      showToast(scene?.illustrations?.find((item) => item.is_canonical) ? "参考主图重生成中" : "剧照生成中");
      return;
    }

    if (dataset.selectIllustration) {
      patchIllustrationWorkbenchState(Number(dataset.sceneId), {
        selectedIllustrationId: Number(dataset.selectIllustration),
      });
      renderProjectWorkspace();
      return;
    }

    if (dataset.markCanonical) {
      await api(`/api/illustrations/${dataset.markCanonical}/canonical`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      await loadProjectDetail(state.currentProjectId, { focusChapterId: state.activeChapterId });
      showToast("已设为主图");
      return;
    }

    if (dataset.deleteIllustration) {
      const confirmed = window.confirm("确定删除这张剧照候选图吗？");
      if (!confirmed) {
        return;
      }
      await api(`/api/illustrations/${dataset.deleteIllustration}`, { method: "DELETE" });
      await loadProjectDetail(state.currentProjectId, { focusChapterId: state.activeChapterId });
      showToast("剧照已删除");
      return;
    }

    if (dataset.deleteExport) {
      const confirmed = window.confirm("确定删除这条导出记录和对应文件吗？");
      if (!confirmed) {
        return;
      }
      await api(`/api/exports/${dataset.deleteExport}`, { method: "DELETE" });
      if (Number(dataset.deleteExport) === Number(state.featuredExportId)) {
        state.featuredExportId = null;
      }
      if (Number(dataset.deleteExport) === Number(state.exportNotice?.bundle?.id)) {
        clearExportNotice();
      }
      await loadProjectDetail(state.currentProjectId, { focusChapterId: state.activeChapterId });
      showToast("导出已删除");
      return;
    }

    if (dataset.dismissExportBanner) {
      clearExportNotice();
      renderExportReadyBanner();
      return;
    }

    if (dataset.deleteJob) {
      const confirmed = window.confirm("确定删除这条任务记录吗？");
      if (!confirmed) {
        return;
      }
      await api(`/api/jobs/${dataset.deleteJob}`, { method: "DELETE" });
      if (state.selectedJobId === Number(dataset.deleteJob)) {
        state.selectedJobId = null;
        state.selectedJobDetail = null;
      }
      await loadProjectDetail(state.currentProjectId, { focusChapterId: state.activeChapterId });
      showToast("任务记录已删除");
      return;
    }

    if (dataset.retryJob) {
      const job = await api(`/api/jobs/${dataset.retryJob}/retry`, {
        method: "POST",
      });
      await trackJob(job.id, { focusChapterId: job.chapter_id ?? state.activeChapterId });
      showToast("已重新提交失败任务");
      return;
    }

    if (dataset.lockChapter) {
      const chapter = findChapterById(dataset.lockChapter);
      if (!chapter) {
        return;
      }
      await api(`/api/chapters/${dataset.lockChapter}/lock`, {
        method: "PATCH",
        body: JSON.stringify({ locked: !chapter.is_locked }),
      });
      await loadProjectDetail(state.currentProjectId, { focusChapterId: chapter.id });
      showToast(chapter.is_locked ? "章节已取消锁定" : "章节已锁定");
      return;
    }

    if (dataset.viewStoryBibleDiff) {
      const revisionId = Number(dataset.viewStoryBibleDiff);
      if (!state.currentProjectId) {
        return;
      }
      if (state.activeStoryBibleDiffId === revisionId) {
        state.activeStoryBibleDiffId = null;
        renderProjectWorkspace();
        return;
      }
      await loadStoryBibleRevisionDiff(state.currentProjectId, revisionId);
      state.activeStoryBibleDiffId = revisionId;
      renderProjectWorkspace();
      return;
    }

    if (dataset.viewChapterDiff) {
      const chapterId = Number(dataset.chapterId || state.activeChapterId);
      const revisionId = Number(dataset.viewChapterDiff);
      if (!chapterId || !revisionId) {
        return;
      }
      if (state.activeChapterRevisionDiffId === revisionId) {
        state.activeChapterRevisionDiffId = null;
        renderProjectWorkspace();
        return;
      }
      await loadChapterRevisionDiff(chapterId, revisionId);
      state.activeChapterRevisionDiffId = revisionId;
      renderProjectWorkspace();
      return;
    }

    if (dataset.restoreRevision) {
      const chapterId = Number(dataset.chapterId || state.activeChapterId);
      const confirmed = window.confirm("恢复后会把当前章节回到该历史版本，建议先保留快照。确定继续吗？");
      if (!confirmed) {
        return;
      }
      await api(`/api/chapters/${chapterId}/revisions/${dataset.restoreRevision}/restore`, {
        method: "POST",
      });
      await loadProjectDetail(state.currentProjectId, { focusChapterId: chapterId });
      showToast("章节已恢复到所选历史版本");
      return;
    }

    if (dataset.editBlock) {
      const block = getActiveChapter()?.narrative_blocks?.find((item) => item.id === Number(dataset.editBlock));
      if (!block) {
        return;
      }
      state.blockDrafts[block.id] = state.blockDrafts[block.id] ?? block.content;
      renderProjectWorkspace();
      return;
    }

    if (dataset.cancelBlock) {
      delete state.blockDrafts[dataset.cancelBlock];
      renderProjectWorkspace();
      return;
    }

    if (dataset.saveBlock) {
      const content = state.blockDrafts[dataset.saveBlock];
      await api(`/api/narrative-blocks/${dataset.saveBlock}`, {
        method: "PATCH",
        body: JSON.stringify({ content }),
      });
      delete state.blockDrafts[dataset.saveBlock];
      await loadProjectDetail(state.currentProjectId, { focusChapterId: state.activeChapterId });
      showToast("正文块已保存");
      return;
    }

    if (dataset.toggleBlockLock) {
      const block = getActiveChapter()?.narrative_blocks?.find((item) => item.id === Number(dataset.toggleBlockLock));
      if (!block) {
        return;
      }
      await api(`/api/narrative-blocks/${dataset.toggleBlockLock}`, {
        method: "PATCH",
        body: JSON.stringify({ is_locked: !block.is_locked }),
      });
      await loadProjectDetail(state.currentProjectId, { focusChapterId: state.activeChapterId });
      showToast(block.is_locked ? "正文块已取消锁定" : "正文块已锁定");
      return;
    }

    if (dataset.editScene) {
      const scene = findSceneById(dataset.editScene);
      if (!scene) {
        return;
      }
      state.sceneDrafts[scene.id] = state.sceneDrafts[scene.id] || {
        title: scene.title,
        scene_type: scene.scene_type,
        location: scene.location,
        time_of_day: scene.time_of_day,
        objective: scene.objective,
        emotional_tone: scene.emotional_tone,
      };
      renderProjectWorkspace();
      return;
    }

    if (dataset.cancelScene) {
      delete state.sceneDrafts[dataset.cancelScene];
      renderProjectWorkspace();
      return;
    }

    if (dataset.saveScene) {
      await api(`/api/scenes/${dataset.saveScene}`, {
        method: "PATCH",
        body: JSON.stringify(state.sceneDrafts[dataset.saveScene] || {}),
      });
      delete state.sceneDrafts[dataset.saveScene];
      await loadProjectDetail(state.currentProjectId, { focusChapterId: state.activeChapterId });
      showToast("场景已保存");
      return;
    }

    if (dataset.toggleSceneLock) {
      const scene = findSceneById(dataset.toggleSceneLock);
      if (!scene) {
        return;
      }
      await api(`/api/scenes/${dataset.toggleSceneLock}`, {
        method: "PATCH",
        body: JSON.stringify({ is_locked: !scene.is_locked }),
      });
      await loadProjectDetail(state.currentProjectId, { focusChapterId: state.activeChapterId });
      showToast(scene.is_locked ? "场景已取消锁定" : "场景已锁定");
      return;
    }

    if (dataset.editDialogue) {
      const scene = getActiveChapter()?.scenes?.find((item) =>
        item.dialogue_blocks.some((dialogue) => dialogue.id === Number(dataset.editDialogue)),
      );
      const dialogue = scene?.dialogue_blocks.find((item) => item.id === Number(dataset.editDialogue));
      if (!dialogue) {
        return;
      }
      state.dialogueDrafts[dialogue.id] = state.dialogueDrafts[dialogue.id] || {
        speaker: dialogue.speaker,
        parenthetical: dialogue.parenthetical,
        content: dialogue.content,
      };
      renderProjectWorkspace();
      return;
    }

    if (dataset.cancelDialogue) {
      delete state.dialogueDrafts[dataset.cancelDialogue];
      renderProjectWorkspace();
      return;
    }

    if (dataset.saveDialogue) {
      await api(`/api/dialogue-blocks/${dataset.saveDialogue}`, {
        method: "PATCH",
        body: JSON.stringify(state.dialogueDrafts[dataset.saveDialogue] || {}),
      });
      delete state.dialogueDrafts[dataset.saveDialogue];
      await loadProjectDetail(state.currentProjectId, { focusChapterId: state.activeChapterId });
      showToast("对白已保存");
      return;
    }

    if (dataset.toggleDialogueLock) {
      const scene = getActiveChapter()?.scenes?.find((item) =>
        item.dialogue_blocks.some((dialogue) => dialogue.id === Number(dataset.toggleDialogueLock)),
      );
      const dialogue = scene?.dialogue_blocks.find((item) => item.id === Number(dataset.toggleDialogueLock));
      if (!dialogue) {
        return;
      }
      await api(`/api/dialogue-blocks/${dataset.toggleDialogueLock}`, {
        method: "PATCH",
        body: JSON.stringify({ is_locked: !dialogue.is_locked }),
      });
      await loadProjectDetail(state.currentProjectId, { focusChapterId: state.activeChapterId });
      showToast(dialogue.is_locked ? "对白已取消锁定" : "对白已锁定");
      return;
    }

    if (dataset.retryIntervention) {
      const interventionId = dataset.retryIntervention;
      const chapter = getActiveChapter();
      const extraGuidance = state.interventionDrafts[interventionId] || "";
      const job = await api(`/api/review-interventions/${interventionId}/retry`, {
        method: "POST",
        body: JSON.stringify({ extra_guidance: extraGuidance }),
      });
      delete state.interventionDrafts[interventionId];
      await trackJob(job.id, { focusChapterId: chapter?.id });
      showToast("已提交新的协作回合");
      return;
    }

    if (dataset.dismissIntervention) {
      await api(`/api/review-interventions/${dataset.dismissIntervention}/dismiss`, {
        method: "POST",
      });
      delete state.interventionDrafts[dataset.dismissIntervention];
      await loadProjectDetail(state.currentProjectId, { focusChapterId: state.activeChapterId });
      showToast("已忽略本次 Reviewer 干预");
    }
  } catch (error) {
    showToast(error.message);
  }
});

setAuthMode("register");
updateAuthUI();
applyDemoBadge();
ensureWorkspaceObserver();
window.addEventListener("resize", syncWorkspaceMode);
window.addEventListener("hashchange", () => {
  if (!state.token && !demoSession) {
    return;
  }
  syncStudioRoute().catch((error) => {
    showToast(error.message);
  });
});
syncWorkspaceMode();
window.visualViewport?.addEventListener("resize", syncWorkspaceMetrics);

if (state.token || demoSession) {
  loadProjects().catch((error) => {
    clearSession();
    updateAuthUI();
    renderDashboard();
    renderProjectWorkspace();
    showToast(error.message);
  });
} else {
  renderDashboard();
  renderProjectWorkspace();
}
