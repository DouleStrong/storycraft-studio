function normalizeFiles(bundle) {
  return Array.isArray(bundle?.files)
    ? bundle.files
        .map((file) => {
          const format = String(file?.format || "").trim().toLowerCase();
          const url = String(file?.url || "").trim();
          if (!format || !url) {
            return null;
          }
          return {
            format,
            formatLabel: format.toUpperCase(),
            downloadLabel: `下载 ${format.toUpperCase()}`,
            url,
          };
        })
        .filter(Boolean)
    : [];
}

export function describeReadyExport(bundle) {
  if (String(bundle?.status || "").trim() !== "completed") {
    return null;
  }

  const files = normalizeFiles(bundle);
  if (!files.length) {
    return null;
  }

  const summary = `${files.map((file) => file.formatLabel).join(" + ")} 已生成，可直接下载到本地。`;
  return {
    title: "导出成品已就绪",
    summary,
    files,
  };
}
