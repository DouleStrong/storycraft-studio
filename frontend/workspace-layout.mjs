export function computeWorkspaceHeight({
  viewportHeight,
  gridTop,
  bottomOffset = 32,
  minHeight = 520,
  maxHeight = 980,
} = {}) {
  const safeViewportHeight = Number(viewportHeight || 0);
  const safeGridTop = Number(gridTop || 0);
  const safeBottomOffset = Number(bottomOffset || 0);

  if (!Number.isFinite(safeViewportHeight) || safeViewportHeight <= 0) {
    return minHeight;
  }

  const remaining = Math.round(safeViewportHeight - safeGridTop - safeBottomOffset);
  return Math.max(minHeight, Math.min(maxHeight, remaining));
}

export function resolveWorkspaceDensity({
  viewportHeight,
  workspaceHeight,
  compactViewportHeight = 940,
  compactWorkspaceHeight = 700,
} = {}) {
  const safeViewportHeight = Number(viewportHeight || 0);
  const safeWorkspaceHeight = Number(workspaceHeight || 0);

  if (Number.isFinite(safeViewportHeight) && safeViewportHeight > 0 && safeViewportHeight <= compactViewportHeight) {
    return "compact";
  }

  if (Number.isFinite(safeWorkspaceHeight) && safeWorkspaceHeight > 0 && safeWorkspaceHeight <= compactWorkspaceHeight) {
    return "compact";
  }

  return "relaxed";
}
