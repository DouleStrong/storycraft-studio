function normalizeText(value) {
  return String(value || "").trim();
}

function excerpt(value, fallback, limit = 72) {
  const normalized = normalizeText(value);
  if (!normalized) {
    return fallback;
  }
  if (normalized.length <= limit) {
    return normalized;
  }
  return `${normalized.slice(0, limit - 1).trimEnd()}…`;
}

function normalizeRules(value) {
  return Array.isArray(value)
    ? value
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];
}

function resolveCurrentRevision(storyBible, storyBibleRevisions) {
  if (storyBible?.current_revision) {
    return storyBible.current_revision;
  }
  return Array.isArray(storyBibleRevisions) && storyBibleRevisions.length ? storyBibleRevisions[0] : null;
}

function resolveLastUpdatedValue(storyBibleRevisions) {
  const latestRevision = Array.isArray(storyBibleRevisions) && storyBibleRevisions.length ? storyBibleRevisions[0] : null;
  if (!latestRevision?.created_at) {
    return "尚未写入修订历史";
  }
  const timestamp = Date.parse(String(latestRevision.created_at || ""));
  if (!Number.isFinite(timestamp)) {
    return "尚未写入修订历史";
  }
  return new Date(timestamp).toLocaleString();
}

function resolveLastUpdatedCompactValue(storyBibleRevisions) {
  const latestRevision = Array.isArray(storyBibleRevisions) && storyBibleRevisions.length ? storyBibleRevisions[0] : null;
  if (!latestRevision?.created_at) {
    return "未更新";
  }
  const timestamp = Date.parse(String(latestRevision.created_at || ""));
  if (!Number.isFinite(timestamp)) {
    return "未更新";
  }
  const date = new Date(timestamp);
  return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function resolveTargetLengthChip(project, targetChapterLabel) {
  const targetLength = normalizeText(project?.target_length);
  if (!targetLength) {
    return "";
  }
  const normalizedTargetLength = targetLength.replace(/\s+/g, "");
  const normalizedChapterLabel = normalizeText(targetChapterLabel).replace(/\s+/g, "");
  if (!normalizedTargetLength || normalizedTargetLength === normalizedChapterLabel) {
    return "";
  }
  return targetLength;
}

export function buildStoryBibleWorkbench(project = {}, options = {}) {
  const storyBible = project?.story_bible || {};
  const storyBibleRevisions = Array.isArray(options.storyBibleRevisions) ? options.storyBibleRevisions : [];
  const currentRevision = resolveCurrentRevision(storyBible, storyBibleRevisions);
  const writingRules = normalizeRules(storyBible.writing_rules);
  const targetChapterLabel = `${Number(project?.target_chapter_count || 0) || 0}章`;
  const filledSections = [
    normalizeText(storyBible.world_notes),
    normalizeText(storyBible.style_notes),
    normalizeText(storyBible.addressing_rules),
    normalizeText(storyBible.timeline_rules),
  ].filter(Boolean).length;

  return {
    summary: {
      currentRevisionLabel: currentRevision
        ? `当前版本 #${currentRevision.revision_index || currentRevision.id}`
        : "未记录版本",
      targetChapterLabel,
      targetLengthLabel: normalizeText(project?.target_length) || "未写目标篇幅",
      targetLengthChip: resolveTargetLengthChip(project, targetChapterLabel),
      ruleCountLabel: `${writingRules.length} 条规则`,
      revisionCountLabel: `${storyBibleRevisions.length} 次修订`,
      filledSectionLabel: `${filledSections} 项已填写`,
      lastUpdatedLabel: "最近更新",
      lastUpdatedValue: resolveLastUpdatedValue(storyBibleRevisions),
      lastUpdatedCompactValue: resolveLastUpdatedCompactValue(storyBibleRevisions),
      previewSections: [
        {
          label: "世界观",
          excerpt: excerpt(storyBible.world_notes, "当前还没有填写世界观摘要。"),
        },
        {
          label: "风格说明",
          excerpt: excerpt(storyBible.style_notes, "当前还没有填写风格说明。"),
        },
        {
          label: "称呼与时间线",
          excerpt: excerpt(
            [storyBible.addressing_rules, storyBible.timeline_rules].filter(Boolean).join(" "),
            "当前还没有补充称呼规则和时间线约束。",
          ),
        },
      ],
      helperText: "设定已折叠为摘要卡。点击“设定详情”查看完整世界观、风格规则和版本历史。",
    },
    detail: {
      worldNotes: normalizeText(storyBible.world_notes),
      styleNotes: normalizeText(storyBible.style_notes),
      writingRules,
      writingRulesText: writingRules.join("\n"),
      addressingRules: normalizeText(storyBible.addressing_rules),
      timelineRules: normalizeText(storyBible.timeline_rules),
      currentRevision,
    },
  };
}
