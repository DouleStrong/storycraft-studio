import assert from "node:assert/strict";
import test from "node:test";

import { withSubmitForm } from "../form-utils.mjs";

test("captures the submit form before async cleanup so reset still works", async () => {
  let resetCalls = 0;
  const form = {
    reset() {
      resetCalls += 1;
    },
  };
  const event = { currentTarget: form };

  await withSubmitForm(event, async (capturedForm) => {
    event.currentTarget = null;
    await Promise.resolve();
    capturedForm.reset();
  });

  assert.equal(resetCalls, 1);
});

test("throws a helpful error when the submit event no longer has a form target", async () => {
  await assert.rejects(
    () => withSubmitForm({ currentTarget: null }, async () => {}),
    /Form submission target is unavailable\./,
  );
});
