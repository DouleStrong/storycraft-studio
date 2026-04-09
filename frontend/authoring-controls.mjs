export function buildStoryBiblePayload(fields) {
  const rules = String(fields.writing_rules_text || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);

  return {
    world_notes: String(fields.world_notes || "").trim(),
    style_notes: String(fields.style_notes || "").trim(),
    writing_rules: rules,
    addressing_rules: String(fields.addressing_rules || "").trim(),
    timeline_rules: String(fields.timeline_rules || "").trim(),
  };
}

export function buildProjectDuplicatePayload(projectTitle, explicitTitle = "") {
  const title = String(explicitTitle || "").trim();
  return {
    title: title || `${String(projectTitle || "").trim()}·副本`,
  };
}

export function buildSnapshotPayload(projectTitle, explicitLabel = "") {
  const label = String(explicitLabel || "").trim();
  return {
    label: label || `${String(projectTitle || "").trim()} · 自动快照`,
  };
}

export function countProtectedContent(chapter) {
  const narrativeBlocks = (chapter?.narrative_blocks || []).filter((item) => item.is_locked || item.is_user_edited).length;
  const scenes = (chapter?.scenes || []).filter((item) => item.is_locked || item.is_user_edited).length;
  const dialogueBlocks = (chapter?.scenes || []).reduce(
    (sum, scene) =>
      sum +
      (scene.dialogue_blocks || []).filter((item) => item.is_locked || item.is_user_edited).length,
    0,
  );
  return {
    narrativeBlocks,
    scenes,
    dialogueBlocks,
    total: narrativeBlocks + scenes + dialogueBlocks,
  };
}
