function resolveCreatedAt(createdAt) {
  const timestamp = Date.parse(String(createdAt || ""));
  return Number.isFinite(timestamp) ? timestamp : null;
}

export function describeJobFeedback(job, now = Date.now()) {
  const status = String(job?.status || "").trim();
  const statusMessage = String(job?.status_message || "").trim();
  const errorMessage = String(job?.error_message || "").trim();
  if (statusMessage) {
    return {
      message: statusMessage,
      tone: status === "failed" ? "danger" : status === "awaiting_user" ? "warn" : "info",
    };
  }

  if (status === "queued") {
    const createdAt = resolveCreatedAt(job?.created_at);
    if (createdAt !== null && now - createdAt >= 30_000) {
      return {
        message: "排队时间偏长，通常不是正常生成，优先检查 worker 或重试这条任务。",
        tone: "warn",
      };
    }
    return {
      message: "任务已入队，正在等待 worker 接手。",
      tone: "info",
    };
  }

  if (status === "processing") {
    return {
      message: "Agent 正在处理当前任务。",
      tone: "info",
    };
  }

  if (status === "awaiting_user") {
    return {
      message: "Reviewer 需要你确认后再继续。",
      tone: "warn",
    };
  }

  if (status === "failed") {
    return {
      message: errorMessage ? `任务失败：${errorMessage}` : "任务失败，请查看 worker 日志后重试。",
      tone: "danger",
    };
  }

  if (status === "completed") {
    return {
      message: "本轮协作已完成。",
      tone: "info",
    };
  }

  return {
    message: "",
    tone: "info",
  };
}
