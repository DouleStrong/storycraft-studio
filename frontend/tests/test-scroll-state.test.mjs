import test from "node:test";
import assert from "node:assert/strict";

import { captureScrollState, restoreScrollState } from "../scroll-state.mjs";

test("captureScrollState only stores existing panel positions", () => {
  const snapshot = captureScrollState({
    characterList: { scrollTop: 48, scrollLeft: 4 },
    jobList: null,
    chapterDetail: { scrollTop: 260, scrollLeft: 0 },
  });

  assert.deepEqual(snapshot, {
    characterList: { scrollTop: 48, scrollLeft: 4 },
    chapterDetail: { scrollTop: 260, scrollLeft: 0 },
  });
});

test("restoreScrollState reapplies saved positions after a rerender", () => {
  const nextPanels = {
    characterList: { scrollTop: 0, scrollLeft: 0 },
    chapterDetail: { scrollTop: 0, scrollLeft: 0 },
  };

  restoreScrollState(
    {
      characterList: { scrollTop: 72, scrollLeft: 6 },
      chapterDetail: { scrollTop: 320, scrollLeft: 0 },
    },
    (key) => nextPanels[key],
  );

  assert.equal(nextPanels.characterList.scrollTop, 72);
  assert.equal(nextPanels.characterList.scrollLeft, 6);
  assert.equal(nextPanels.chapterDetail.scrollTop, 320);
});
