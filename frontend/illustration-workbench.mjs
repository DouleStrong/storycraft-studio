function clampCandidateCount(value) {
  const parsed = Number.parseInt(String(value ?? "").trim(), 10);
  if (Number.isNaN(parsed)) {
    return 2;
  }
  return Math.min(4, Math.max(1, parsed));
}

export function buildIllustrationRequestPayload({ candidateCount, extraGuidance }) {
  return {
    candidate_count: clampCandidateCount(candidateCount),
    extra_guidance: String(extraGuidance ?? "").trim(),
  };
}

export function resolveFeaturedIllustration(scene, selectedIllustrationId) {
  const illustrations = scene?.illustrations || [];
  if (!illustrations.length) {
    return null;
  }
  const explicit = illustrations.find((item) => item.id === Number(selectedIllustrationId));
  if (explicit) {
    return explicit;
  }
  return illustrations.find((item) => item.is_canonical) || illustrations[0];
}
