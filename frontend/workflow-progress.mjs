const DEFAULT_STAGES = [
  { stage: "queued", label: "排队" },
  { stage: "context", label: "载入上下文" },
  { stage: "generate", label: "生成" },
  { stage: "review", label: "审校" },
  { stage: "persist", label: "回填" },
  { stage: "complete", label: "完成" },
];

function mapStageState(status) {
  if (status === "completed") {
    return "done";
  }
  if (status === "processing") {
    return "active";
  }
  if (status === "awaiting_user") {
    return "awaiting_user";
  }
  if (status === "failed") {
    return "failed";
  }
  if (status === "skipped") {
    return "skipped";
  }
  return "pending";
}

export function resolveWorkflowProgress(job = {}) {
  const liveState = job?.result?.live_state || {};
  const historyLookup = new Map(
    (Array.isArray(liveState.stage_history) ? liveState.stage_history : []).map((item) => [String(item.stage || ""), item]),
  );
  const rawStages =
    Array.isArray(liveState.stages) && liveState.stages.length
      ? liveState.stages
      : DEFAULT_STAGES.map((stage) => ({
          ...stage,
          status: historyLookup.get(stage.stage)?.status || "",
        }));
  const stages = rawStages.map((stage, index) => {
    const key = String(stage.stage || stage.key || DEFAULT_STAGES[index]?.stage || `stage_${index}`);
    const label = String(stage.label || DEFAULT_STAGES[index]?.label || key);
    return {
      key,
      label,
      rawStatus: String(stage.status || ""),
      state: mapStageState(String(stage.status || "")),
    };
  });

  return {
    currentStage: String(liveState.current_stage || ""),
    currentStep: String(liveState.current_step || ""),
    currentStepLabel: String(liveState.current_step_label || ""),
    latestAgentName: String(liveState.latest_agent_name || ""),
    latestAgentSummary: String(liveState.latest_agent_summary || ""),
    stages,
    stageHistory: Array.isArray(liveState.stage_history) ? liveState.stage_history : [],
  };
}
