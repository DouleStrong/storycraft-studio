export function captureScrollState(targets) {
  const snapshot = {};
  for (const [key, element] of Object.entries(targets || {})) {
    if (!element) {
      continue;
    }
    snapshot[key] = {
      scrollTop: Number(element.scrollTop || 0),
      scrollLeft: Number(element.scrollLeft || 0),
    };
  }
  return snapshot;
}

export function restoreScrollState(snapshot, resolver) {
  for (const [key, position] of Object.entries(snapshot || {})) {
    const element = typeof resolver === "function" ? resolver(key) : resolver?.[key];
    if (!element) {
      continue;
    }
    element.scrollTop = Number(position.scrollTop || 0);
    element.scrollLeft = Number(position.scrollLeft || 0);
  }
}
