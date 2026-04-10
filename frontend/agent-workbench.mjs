import { describeJobFeedback } from "./job-feedback.mjs";
import { findPendingIntervention, isTerminalJobStatus } from "./studio-state.mjs";
import { resolveWorkflowProgress } from "./workflow-progress.mjs";

function normalizeJobs(project) {
  return [...(project?.jobs || [])].sort((left, right) => {
    const leftTime = Date.parse(left?.updated_at || left?.created_at || left?.completed_at || "") || 0;
    const rightTime = Date.parse(right?.updated_at || right?.created_at || right?.completed_at || "") || 0;
    return rightTime - leftTime || Number(right?.id || 0) - Number(left?.id || 0);
  });
}

function findChapter(project, chapterId) {
  return (project?.chapters || []).find((chapter) => Number(chapter.id) === Number(chapterId)) || null;
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
  }[jobType] || String(jobType || "协作任务");
}

function formatJobStatus(status) {
  return {
    queued: "排队中",
    processing: "处理中",
    awaiting_user: "等待你确认",
    completed: "已完成",
    failed: "失败",
  }[status] || String(status || "未知状态");
}

function formatChapterLabel(chapter) {
  if (!chapter) {
    return "";
  }
  return `第 ${chapter.order_index} 章 · ${chapter.title}`;
}

function resolveFocusJob(jobs, selectedJobDetail) {
  if (selectedJobDetail?.id) {
    return selectedJobDetail;
  }
  return jobs.find((job) => job.status === "awaiting_user")
    || jobs.find((job) => !isTerminalJobStatus(job.status))
    || jobs[0]
    || null;
}

function resolveTone(job) {
  if (job?.status === "awaiting_user") {
    return "warn";
  }
  if (job?.status === "failed") {
    return "danger";
  }
  if (job?.status === "completed") {
    return "success";
  }
  return "live";
}

function buildHistory(jobs, project, selectedJobDetail, focusJob) {
  const selectedJobId = Number(selectedJobDetail?.id || focusJob?.id || 0);

  return jobs.slice(0, 8).map((job) => {
    const workflowProgress = resolveWorkflowProgress(job);
    const jobFeedback = describeJobFeedback(job);
    const chapter = findChapter(project, job.chapter_id);
    return {
      jobId: Number(job.id || 0),
      chapterId: Number(chapter?.id || 0) || null,
      title: formatJobType(job.job_type),
      status: String(job.status || ""),
      statusLabel: formatJobStatus(job.status),
      chapterLabel: formatChapterLabel(chapter),
      summary:
        workflowProgress.latestAgentSummary
        || job.status_message
        || jobFeedback.message
        || "这条任务还没有写入更多公开协作摘要。",
      currentStepLabel: workflowProgress.currentStepLabel || "",
      progressLabel: `${Number(job.progress || 0)}%`,
      tone: resolveTone(job),
      isSelected: Number(job.id || 0) === selectedJobId,
      isFocus: Number(job.id || 0) === Number(focusJob?.id || 0),
    };
  });
}

export function buildAgentWorkbench(project, options = {}) {
  const jobs = normalizeJobs(project);
  const selectedJobDetail = options.selectedJobDetail || null;
  const activeChapter = findChapter(project, options.activeChapterId);
  const focusJob = resolveFocusJob(jobs, selectedJobDetail);
  const pendingIntervention = findPendingIntervention(activeChapter);

  const summary = {
    totalJobs: jobs.length,
    activeJobs: jobs.filter((job) => !isTerminalJobStatus(job.status)).length,
    awaitingJobs: jobs.filter((job) => job.status === "awaiting_user").length,
    failedJobs: jobs.filter((job) => job.status === "failed").length,
    completedJobs: jobs.filter((job) => job.status === "completed").length,
  };

  if (focusJob) {
    const focusChapter = findChapter(project, focusJob.chapter_id) || activeChapter;
    const workflowProgress = resolveWorkflowProgress(focusJob);
    const jobFeedback = describeJobFeedback(focusJob);
    return {
      summary,
      history: buildHistory(jobs, project, selectedJobDetail, focusJob),
      focus: {
        kind: "job",
        jobId: Number(focusJob.id || 0),
        chapterId: Number(focusChapter?.id || 0) || null,
        title: formatJobType(focusJob.job_type),
        eyebrow: focusJob.status === "awaiting_user" ? "等待作者决策" : "当前协作焦点",
        status: String(focusJob.status || ""),
        statusLabel: formatJobStatus(focusJob.status),
        chapterLabel: formatChapterLabel(focusChapter),
        summary:
          workflowProgress.latestAgentSummary
          || jobFeedback.message
          || focusJob.status_message
          || "协作链路已建立，等待你查看这一轮生成结果。",
        detail:
          workflowProgress.currentStepLabel
          || (focusJob.error_message ? `异常：${focusJob.error_message}` : ""),
        progressLabel: `${Number(focusJob.progress || 0)}%`,
        currentStepLabel: workflowProgress.currentStepLabel || "",
        latestAgentSummary: workflowProgress.latestAgentSummary || "",
        tone: resolveTone(focusJob),
      },
    };
  }

  if (pendingIntervention && activeChapter) {
    return {
      summary,
      history: [],
      focus: {
        kind: "intervention",
        jobId: null,
        chapterId: Number(activeChapter.id || 0) || null,
        title: "这一章正在等待你的决定",
        eyebrow: "待处理干预",
        status: "awaiting_user",
        statusLabel: "等待你确认",
        chapterLabel: formatChapterLabel(activeChapter),
        summary: pendingIntervention.reviewer_notes || "Reviewer 提出了新的修订建议。",
        detail: pendingIntervention.suggested_guidance || "",
        progressLabel: "",
        currentStepLabel: "",
        latestAgentSummary: "",
        tone: "warn",
      },
    };
  }

  if (activeChapter) {
    return {
      summary,
      history: [],
      focus: {
        kind: "chapter_idle",
        jobId: null,
        chapterId: Number(activeChapter.id || 0) || null,
        title: formatChapterLabel(activeChapter),
        eyebrow: "当前创作上下文",
        status: "idle",
        statusLabel: "可继续创作",
        chapterLabel: formatChapterLabel(activeChapter),
        summary: "当前没有运行中的 Agent，你可以继续生成正文、生成场景，或整理这一章的剧照候选。",
        detail: "",
        progressLabel: "",
        currentStepLabel: "",
        latestAgentSummary: "",
        tone: "neutral",
      },
    };
  }

  return {
    summary,
    history: [],
    focus: {
      kind: "empty",
      jobId: null,
      chapterId: null,
      title: "协作台待启动",
      eyebrow: "当前协作焦点",
      status: "idle",
      statusLabel: "尚未开始",
      chapterLabel: "",
      summary: "生成大纲后，右侧会开始显示多 Agent 协作进度、轨迹和交付状态。",
      detail: "",
      progressLabel: "",
      currentStepLabel: "",
      latestAgentSummary: "",
      tone: "neutral",
    },
  };
}
