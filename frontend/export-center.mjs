function normalizeArray(value) {
  return Array.isArray(value) ? value : [];
}

function normalizeExports(exports) {
  return [...normalizeArray(exports)].sort((left, right) => {
    const leftTime = Date.parse(left?.completed_at || left?.created_at || "") || 0;
    const rightTime = Date.parse(right?.completed_at || right?.created_at || "") || 0;
    return rightTime - leftTime || Number(right?.id || 0) - Number(left?.id || 0);
  });
}

function qualityLabel(status) {
  return {
    passed: "质量校验通过",
    warn: "建议人工复核",
    failed: "质量校验未通过",
    pending: "待质量校验",
  }[String(status || "").trim()] || "待质量校验";
}

function statusLabel(status) {
  return {
    queued: "排队中",
    processing: "处理中",
    awaiting_user: "等待确认",
    completed: "已完成",
    failed: "失败",
  }[String(status || "").trim()] || String(status || "未知状态");
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function buildDownloads(files) {
  return normalizeArray(files)
    .filter((file) => file?.url)
    .map((file) => ({
      format: String(file.format || "").toLowerCase(),
      label: `下载 ${String(file.format || "").toUpperCase()}`,
      url: String(file.url),
      pageCount: Number(file.page_count || 0),
    }));
}

function buildCard(bundle) {
  const summary = bundle?.delivery_summary || {};
  const downloads = buildDownloads(bundle?.files);
  return {
    id: Number(bundle?.id || 0),
    status: String(bundle?.status || ""),
    statusLabel: statusLabel(bundle?.status),
    qualityLabel: qualityLabel(summary.quality_status),
    formatsLabel: normalizeArray(bundle?.formats)
      .map((item) => String(item || "").toUpperCase())
      .filter(Boolean)
      .join(" + "),
    summary: `${summary.chapter_count || 0} 章 · ${summary.character_count || 0} 角 · ${summary.illustration_count || 0} 幅图`,
    sizeLabel: formatBytes(summary.total_size_bytes),
    pageCountLabel: `${summary.total_page_count || 0} 页`,
    downloads,
  };
}

export function buildExportDeliveryCenter(exports) {
  const normalized = normalizeExports(exports);
  if (!normalized.length) {
    return {
      state: "empty",
      hero: null,
      metrics: [],
      cards: [],
    };
  }

  const cards = normalized.map(buildCard);
  const readyCards = cards.filter((card) => card.status === "completed" && card.downloads.length);
  const latestReady = readyCards[0] || null;
  const passedCount = normalized.filter(
    (bundle) => String(bundle?.delivery_summary?.quality_status || "").trim() === "passed",
  ).length;
  const totalPageCount = normalized.reduce(
    (sum, bundle) => sum + Number(bundle?.delivery_summary?.total_page_count || 0),
    0,
  );

  return {
    state: latestReady ? "ready" : "processing",
    hero: latestReady
      ? {
          title: "成品交付台",
          summary: `${latestReady.formatsLabel} 已合成完成，当前可直接下载或继续查看历史成品。`,
          qualityLabel: latestReady.qualityLabel,
          downloads: latestReady.downloads,
          meta: [
            `${latestReady.summary}`,
            `${latestReady.pageCountLabel}`,
            `${latestReady.sizeLabel}`,
          ],
        }
      : {
          title: "成品交付台",
          summary: "导出任务已经启动，当前还没有可下载成品。",
          qualityLabel: "待质量校验",
          downloads: [],
          meta: [],
        },
    metrics: [
      { label: "已完成导出", value: String(readyCards.length) },
      { label: "校验通过", value: String(passedCount) },
      { label: "总页数", value: String(totalPageCount) },
    ],
    cards,
  };
}
