import test from "node:test";
import assert from "node:assert/strict";

import {
  buildIllustrationRequestPayload,
  resolveFeaturedIllustration,
} from "../illustration-workbench.mjs";

test("resolveFeaturedIllustration prefers explicit selection, then canonical, then first candidate", () => {
  const scene = {
    illustrations: [
      { id: 11, is_canonical: false, candidate_index: 1 },
      { id: 12, is_canonical: true, candidate_index: 2 },
      { id: 13, is_canonical: false, candidate_index: 3 },
    ],
  };

  assert.equal(resolveFeaturedIllustration(scene, 13)?.id, 13);
  assert.equal(resolveFeaturedIllustration(scene, null)?.id, 12);
  assert.equal(resolveFeaturedIllustration({ illustrations: [{ id: 21, is_canonical: false }] }, null)?.id, 21);
  assert.equal(resolveFeaturedIllustration({ illustrations: [] }, null), null);
});

test("buildIllustrationRequestPayload trims guidance and normalizes candidate count", () => {
  assert.deepEqual(
    buildIllustrationRequestPayload({ candidateCount: " 3 ", extraGuidance: "  保留主图里的灯光层次  " }),
    {
      candidate_count: 3,
      extra_guidance: "保留主图里的灯光层次",
    },
  );

  assert.deepEqual(
    buildIllustrationRequestPayload({ candidateCount: "99", extraGuidance: "" }),
    {
      candidate_count: 4,
      extra_guidance: "",
    },
  );
});
