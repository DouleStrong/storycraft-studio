export function resolveActiveChapterId(project, currentChapterId) {
  const chapters = project?.chapters || [];
  if (!chapters.length) {
    return null;
  }

  const requestedId = Number(currentChapterId);
  if (Number.isFinite(requestedId) && chapters.some((chapter) => chapter.id === requestedId)) {
    return requestedId;
  }

  return chapters[0].id;
}

export function buildProjectPayload(fields) {
  return {
    ...fields,
    target_chapter_count: Number(fields.target_chapter_count || 0),
  };
}

export function parseStudioRoute(hash) {
  const normalized = String(hash || "")
    .trim()
    .replace(/^#/, "");
  if (!normalized || normalized === "/" || normalized === "/dashboard") {
    return { view: "dashboard", projectId: null };
  }

  const workspaceMatch = normalized.match(/^\/projects\/(\d+)$/);
  if (workspaceMatch) {
    return {
      view: "workspace",
      projectId: Number(workspaceMatch[1]),
    };
  }

  return { view: "dashboard", projectId: null };
}

export function buildStudioRoute(view, projectId = null) {
  if (view === "workspace" && Number.isFinite(Number(projectId))) {
    return `#/projects/${Number(projectId)}`;
  }
  return "#/dashboard";
}

export function resolveWorkspaceProjectId(projects, routeProjectId, currentProjectId) {
  const availableProjectIds = new Set((projects || []).map((project) => Number(project.id)));
  const preferredProjectId = Number(routeProjectId);
  if (Number.isFinite(preferredProjectId) && availableProjectIds.has(preferredProjectId)) {
    return preferredProjectId;
  }

  const fallbackProjectId = Number(currentProjectId);
  if (Number.isFinite(fallbackProjectId) && availableProjectIds.has(fallbackProjectId)) {
    return fallbackProjectId;
  }

  return null;
}

export function findPendingIntervention(chapter) {
  return (chapter?.pending_interventions || []).find((item) => item.status === "pending") || null;
}

export function isTerminalJobStatus(status) {
  return ["awaiting_user", "completed", "failed"].includes(status);
}

export function resolveWorkspaceMode(editorWidth) {
  const width = Number(editorWidth || 0);
  if (width >= 1500) {
    return "wide";
  }
  if (width >= 1120) {
    return "balanced";
  }
  return "stacked";
}

export function partitionCharacterLibrary(characters, project) {
  const projectId = Number(project?.id);
  if (!Number.isFinite(projectId)) {
    return {
      attached: [],
      available: [...(characters || [])],
    };
  }

  const attached = [];
  const available = [];
  for (const character of characters || []) {
    const linkedProjectIds = character?.linked_project_ids || [];
    if (linkedProjectIds.includes(projectId)) {
      attached.push(character);
    } else {
      available.push(character);
    }
  }

  return { attached, available };
}
