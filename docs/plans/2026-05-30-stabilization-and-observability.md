# xianyu-tools Stabilization and Observability Plan

> **For Hermes:** Use review-gated implementation. Every code-changing task should land as a small commit with explicit verification evidence before moving to the next task.

**Goal:** Turn the current fork from a feature-complete prototype into a stable, observable, maintainable product while preserving the existing `scrape_xianyu(task_config, debug_limit)` runtime contract.

**Architecture:** Keep FastAPI + Vue + Playwright + SQLite. Continue strangler-style refactors around the current scraper path. Do not rewrite the whole project or bypass the existing task process model.

**Global constraints:**
- Do not modify production `.env`, `state/`, cookies, NAS deployment files, or real user data without explicit confirmation.
- Any database write against a non-disposable DB must first show the exact payload / SQL and wait for confirmation.
- Preserve Xianyu login, risk-control, account binding, proxy rotation, notification, and `scrape_xianyu(task_config, debug_limit)` compatibility.
- Keep Docker Compose default behavior: build local `xianyu-tools:local` from the working tree.
- Keep user-facing handoff notes in Chinese.

---

## Phase Overview

### P0: Non-mutating local smoke and runbook

**Status (2026-05-30): 已完成。** `docs/runbooks/local-smoke.md` 和 `scripts/smoke_check.py` 已落地到 `master`；M9-3 disposable smoke 验证通过（16 targeted tests, web-ui build, smoke_check, openapi check）。

**Objective:** Make current `master` deployment verification repeatable without touching production data.

**Files:**
- Create: `docs/runbooks/local-smoke.md`
- Optional create: `scripts/smoke_check.py`

**Tasks:**
1. Document a non-mutating local smoke flow:
   - verify git clean state and branch
   - build local Docker image
   - start a disposable container / compose stack with temporary data directories
   - check `/health`, `/`, and static assets
   - check API schema / docs route if available
   - inspect container logs for obvious startup errors
2. If adding `scripts/smoke_check.py`, keep it read-only:
   - GET health/index/docs endpoints only
   - no task creation
   - no settings write
   - no DB mutation
3. Verification:
   - `git diff --check`
   - run the smoke script against a local test endpoint if a disposable container is started

**Acceptance:** A developer can reproduce a safe local smoke without guessing which files or runtime data are touched.

---

### P1: Structured task-run status and error reasons

**Objective:** Make task failures diagnosable from structured status instead of raw logs only.

**Likely files:**
- Modify: `src/services/process_service.py`
- Modify: `src/services/task_service.py`
- Modify: `src/services/dashboard_service.py`
- Modify: `src/api/routes/tasks.py`
- Modify: `web-ui/src/components/tasks/TasksTable.vue`
- Optional create: `src/services/task_run_service.py`
- Tests: `tests/unit/test_process_service.py`, `tests/integration/test_api_tasks.py`

**Runtime stages to model:**
- `account_selected`
- `browser_started`
- `search_loaded`
- `filters_applied`
- `page_scanned`
- `detail_loaded`
- `ai_analyzed`
- `result_saved`
- `notification_sent`

**Error categories to model:**
- login state expired
- anti-bot / captcha / risk control
- search page load failure
- detail page parse failure
- AI call failure
- notification failure
- database write failure
- unknown runtime exception

**Tasks:**
1. Add a minimal task-run status model / DTO without changing scraper behavior.
2. Record process start/stop/error metadata from the existing process boundary.
3. Surface the latest status through task APIs.
4. Show latest status and last error reason in the task table.
5. Add unit/integration tests around status serialization and API response shape.

**Verification:**
```bash
cd /root/projects/xianyu-tools
/tmp/xianyu-tools-r4-venv/bin/python -m compileall -q src tests
/tmp/xianyu-tools-r4-venv/bin/python -m pytest tests/unit/test_process_service.py tests/integration/test_api_tasks.py -q
cd web-ui && npm run build
```

---

### P2: First safe scraper seam extraction

**Objective:** Reduce `src/scraper.py` risk by extracting one low-risk pipeline seam while preserving the public entry point.

**Recommended first seam:** result persistence + notification dispatch.

**Likely files:**
- Modify: `src/scraper.py`
- Modify/Create: `src/services/result_pipeline_service.py`
- Modify: `src/services/result_storage_service.py`
- Modify: `src/services/notification_service.py`
- Tests: `tests/unit/test_item_processing.py`, `tests/unit/test_notification_service.py`, new `tests/unit/test_result_pipeline_service.py`

**Tasks:**
1. Identify the exact result-save + notification block in `src/scraper.py`.
2. Write tests for the current behavior before moving code.
3. Create `ResultPipelineService` that accepts already-parsed item/analysis/task context.
4. Replace the inline scraper block with a service call.
5. Keep behavior identical: no notification routing changes, no result schema changes.

**Verification:**
```bash
cd /root/projects/xianyu-tools
/tmp/xianyu-tools-r4-venv/bin/python -m compileall -q src tests
/tmp/xianyu-tools-r4-venv/bin/python -m pytest tests/unit/test_item_processing.py tests/unit/test_notification_service.py tests/integration/test_pipeline_parse.py -q
/tmp/xianyu-tools-r4-venv/bin/python -m pytest -q
```

---

### P3: Result management usability

**Status (2026-05-30): 已完成。** P3-1b/P3-2/P3-3/P3-4/P3-5 全部落地到 `master`；包含 sort/filter URL 持久化、processed/contacted 标记、批量操作、卖家聚合、seller panel top-N 展开，以及 M9-2 seller click-through filter。

**Objective:** Make accumulated results easier to use day-to-day.

**Likely files:**
- Modify: `src/api/routes/results.py`
- Modify: `src/services/result_storage_service.py`
- Modify: `src/services/result_export_service.py`
- Modify: `web-ui/src/views/ResultsView.vue`
- Modify: `web-ui/src/components/results/ResultsFilterBar.vue`
- Modify/Create: result state / blacklist services as needed
- Tests: `tests/integration/test_api_results.py`, `tests/unit/test_result_blacklist_service.py`

**Candidate features:**
- Persist filters in URL query or localStorage.
- Add sort options: discovered time, publish time, price ascending/descending, AI score/recommendation level.
- Add hidden / processed / contacted state.
- Add batch operations for hide/export/mark processed.
- Add seller-level aggregation when enough seller profile data exists.

**Result query contract:**
- The combined `sort` query parameter is canonical and takes precedence over legacy `sort_by` / `sort_order` when both are present; invalid combined `sort` values fall back to the legacy pair for compatibility.
- Result filters are represented in the URL query so the result page can be refreshed or shared without losing state.
- `lastSelectedResultFile` is only a fallback when the URL has no `file` query parameter.
- User-state flags are stored separately from visibility `status`: `_is_processed` and `_is_contacted` are boolean markers on result items, while `status` continues to represent active/hidden/expired visibility.
- `processed_only`, `contacted_only`, and `hide_processed` are URL/API filters and are also honored by CSV export.
- P3-3 batch operations: `PATCH /api/results/{filename}/items/batch` accepts `item_ids`, `status` (active/hidden), `is_processed`, `is_contacted`; returns `requested_count` and `updated_count`. The batch endpoint reuses the same `_build_item_update_sets` helper as the single-item endpoints.
- Frontend batch UX: each result card has a checkbox; select-all/clear for the current page; toolbar with mark-processed, mark-contacted, batch-hide, batch-unhide, clear-selection, and export-current-filter.

**Verification:**
```bash
cd /root/projects/xianyu-tools
/tmp/xianyu-tools-r4-venv/bin/python -m pytest tests/integration/test_api_results.py tests/unit/test_result_blacklist_service.py -q
cd web-ui && npm run build
```

---

### P4: Notification strategy refinement

**Objective:** Reduce noise while keeping high-value alerts fast.

**Status (2026-05-30): 已完成。** P4-1（阈值 + item dedup）、P4-2（通知内容丰富化）、P4-3（per-seller throttle）全部落地到 `master`；4 个 env-only 开关默认全部关闭；运维启用顺序、风险与回滚步骤见 `docs/runbooks/notification-throttle-ops.md`；开发侧契约见 `AGENTS.md` § "P4-1 通知降噪契约"。

**Likely files:**
- Modify: `src/services/notification_service.py`
- Modify: `src/services/notification_config_service.py`
- Modify: `src/services/result_storage_service.py`
- Modify: `web-ui/src/components/settings/NotificationSettingsPanel.vue`
- Modify: `web-ui/src/components/tasks/TaskNotificationTargets.vue`
- Tests: `tests/unit/test_notification_service.py`, `tests/integration/test_api_settings.py`

**Candidate features:**
- Task-level notification templates.
- Recommendation-level threshold: strong recommendations notify immediately, weak/mid records only save.
- Dedup window by item ID / normalized URL.
- Per-seller throttling window.
- Richer notification content: price, region, YHB/free-shipping labels, AI personal-seller reason, direct link.

**Notification content contract:**
- Channel clients build notifications from a shared `NotificationMessage` object; enriched fields are optional and must default safely when source data is absent.
- Product data may contribute `发货地区`, `商品标签`, `卖家昵称`, and boolean badge semantics for 验货宝 / 包邮.
- Seller-persona context is passed through underscore-prefixed pipeline keys such as `_seller_type_persona`, `_seller_type_status`, and `_seller_type_comment` to avoid colliding with raw product fields.
- Enterprise WeChat TextCard descriptions must remain plain readable text: do not embed raw HTML links in `description`; put the clickable URL in `textcard.url`.
- Webhook templates may use `${region}`, `${tags}`, `${badges}`, `${free_shipping}`, `${inspection_service}`, `${seller_nickname}`, `${seller_type_persona}`, `${seller_type_status}`, and `${seller_type_comment}`.

**Verification:**
```bash
cd /root/projects/xianyu-tools
/tmp/xianyu-tools-r4-venv/bin/python -m pytest tests/unit/test_notification_service.py tests/integration/test_api_settings.py -q
cd web-ui && npm run build
```

---

## Recommended Execution Order

1. P0 safe local smoke + runbook.
2. P1 structured status / error reasons.
3. P2 first scraper seam extraction.
4. P3 result management improvements.
5. P4 notification strategy refinement.

Each phase should finish with:
- a small PR or direct branch checkpoint
- exact verification output
- note whether production restart/redeploy is needed
