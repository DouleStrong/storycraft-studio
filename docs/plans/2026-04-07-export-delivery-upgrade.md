# Export Delivery Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade StoryCraft Studio exports into polished deliverables with a composed PDF layout, a PDF quality-check step, and a richer export delivery workspace in the frontend.

**Architecture:** Split export responsibilities into a small backend composer layer that builds PDF and DOCX bundles plus a quality-check payload, then expose richer export metadata through existing REST responses. On the frontend, turn the current export list into a delivery board with summary cards, quality signals, and direct download actions.

**Tech Stack:** FastAPI, SQLAlchemy, ReportLab, python-docx, pypdf, vanilla JS, CSS.

---

### Task 1: Add backend export tests for composed PDF bundles

**Files:**
- Create: `backend/tests/test_export_delivery.py`
- Modify: `backend/app/services.py`
- Test: `backend/tests/test_export_delivery.py`

**Step 1: Write failing tests**
- Add a test that builds a project-like object and asserts PDF exports include metadata for page count, size, and quality status.
- Add a test that asserts the PDF text contains role headings like cover, characters, and chapter content.
- Add a test that asserts DOCX and PDF entries are both returned with delivery summary information.

**Step 2: Run the new test file**
- Run: `conda run --no-capture-output -n AGI pytest backend/tests/test_export_delivery.py -q`
- Expected: FAIL because quality metadata and composed summary fields do not exist yet.

**Step 3: Implement minimal backend export composer changes**
- Extract PDF building helpers and quality-check helpers.
- Enrich `export_package.files` entries with metadata like `size_bytes`, optional `page_count`, and `quality_check`.
- Add a delivery summary serializer for exports.

**Step 4: Run the test file again**
- Run: `conda run --no-capture-output -n AGI pytest backend/tests/test_export_delivery.py -q`
- Expected: PASS.

### Task 2: Upgrade PDF composition and quality checks

**Files:**
- Modify: `backend/app/services.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_export_delivery.py`

**Step 1: Refactor PDF generation**
- Replace the current line-by-line canvas writing with a composed layout that includes:
  - cover page
  - character page
  - chapter sections
  - inserted canonical illustrations
  - page numbering

**Step 2: Add PDF quality checks**
- Use `pypdf` to read the produced PDF and validate:
  - file exists and is non-empty
  - page count is at least 1
  - extracted text contains the project title
  - extracted text contains at least one chapter heading when chapters exist
- If `pdftoppm` is available later, keep room for optional render-based checks, but do not block export when the tool is missing.

**Step 3: Make export metadata visible**
- Ensure `serialize_export()` includes richer file info and delivery summary so the frontend can render a delivery board instead of a plain list.

**Step 4: Re-run targeted backend tests**
- Run: `conda run --no-capture-output -n AGI pytest backend/tests/test_export_delivery.py backend/tests/test_story_platform_api.py -q`
- Expected: PASS for the new export tests and no regression in API export flows.

### Task 3: Add frontend export delivery helpers and tests

**Files:**
- Create: `frontend/export-center.mjs`
- Create: `frontend/tests/export-center.test.mjs`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Modify: `frontend/index.html`

**Step 1: Write failing frontend tests**
- Add a helper test that converts export payloads into a delivery-center summary with:
  - hero copy
  - total finished bundles
  - available download actions
  - quality status labels

**Step 2: Run the new frontend test**
- Run: `node --test frontend/tests/export-center.test.mjs`
- Expected: FAIL because the helper does not exist yet.

**Step 3: Implement the helper and wire it into the UI**
- Build a “成品交付台” summary layer that groups:
  - latest ready export
  - quality badge
  - included content metrics
  - download buttons
- Keep the current async export flow, but replace the list-heavy presentation with a richer board layout.

**Step 4: Re-run frontend tests**
- Run: `node --test frontend/tests/export-center.test.mjs frontend/tests/export-feedback.test.mjs`
- Expected: PASS.

### Task 4: Polish and verify the full flow

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Modify: `backend/app/services.py`

**Step 1: Run syntax and regression checks**
- Run: `node --experimental-default-type=module --check frontend/app.js`
- Run: `node --test frontend/tests/*.test.mjs`
- Run: `conda run --no-capture-output -n AGI pytest backend/tests/test_export_delivery.py backend/tests/test_story_platform_api.py -q`

**Step 2: Generate a real export artifact locally**
- Use the existing export flow to produce a PDF and DOCX bundle.
- Inspect the resulting export metadata and confirm the files are downloadable.

**Step 3: Summarize residual risks**
- Note whether render-level PDF inspection remains optional because `pdftoppm` is unavailable in the environment.
