# PR Draft: Parallel Refactor Batch — P3-1b / P3-2 / P4-2 + P4-1

**Branch:** local `master` (not pushed; includes the commits listed below)
**Prepared:** 2026-05-30
**Verified by:** R5 validation pass (sonnet46), then operator review

---

## Summary

This batch lands three parallel refactor phases plus one follow-up seam, all
delivered by the Codex/Opus47 worker lane and reviewed here:

| Phase | Title | Commits |
|-------|-------|---------|
| P3-1b | Result sort regression tests + resultQuery refactor | 513402e |
| P3-2  | Processed/contacted user flags (API + UI) | 25e7c3e |
| P4-2  | Notification content enrichment (region, tags, badges, seller persona) | d3ab828 |
| docs  | Stabilization & observability plan update | cd5966c |
| P4-1  | Notification threshold + dedup seam (filter + policy + InMemoryDedupStore) | 4d0fdb7 + 0514187 + merge a705edb |
| P4-3  | Notification per-seller throttle seam | merge (kb/p4-3-notification-seller-throttle) |

---

## Changes by Phase

### P3-1b — Result sort regression tests + resultQuery refactor
**Commit:** `513402e`

- `tests/integration/test_api_results.py`: +25 sort regression cases
- `web-ui/src/composables/resultQuery.assertions.ts`: new assertion helpers (86 lines)
- `web-ui/src/composables/resultQuery.ts`: extracted from useResults, +91 lines
- `web-ui/src/composables/useResults.ts`: slimmed down (-85 lines, delegates to resultQuery)

No backend schema changes. No service restart needed.

### P3-2 — Processed/contacted user flags
**Commit:** `25e7c3e`

Backend:
- `src/infrastructure/persistence/sqlite_connection.py`: **SQLite migration** — adds
  `is_processed INTEGER NOT NULL DEFAULT 0` and `is_contacted INTEGER NOT NULL DEFAULT 0`
  to `result_items` via `ALTER TABLE ... ADD COLUMN` (idempotent, safe on existing DB)
- `src/api/routes/results.py`: new `PATCH /{filename}/items/{item_id}/flags` endpoint
- `src/services/result_storage_service.py`: flag toggle + query filter logic (+92 lines)
- Query params: `processed_only`, `contacted_only`, `hide_processed`
- Export endpoint propagates filters

Frontend:
- `ResultCard.vue`: flag toggle buttons in card footer
- `ResultsFilterBar.vue`: filter checkboxes
- `ResultsGrid.vue`, `ResultsView.vue`: wired up
- `resultQuery.ts` / `useResults.ts`: URL query persistence
- i18n: `zh-CN.ts` + `en-US.ts` keys added

**Deployment impact:**
- Requires service restart (new API routes + migration runs on startup)
- SQLite migration is additive/idempotent — safe on existing production DB
- Frontend build required (included in this batch)

### P4-2 — Notification content enrichment
**Commit:** `d3ab828`

- `src/infrastructure/external/notification_clients/base.py`: `NotificationMessage`
  extended with `region`, `tags`, `free_shipping`, `inspection_service`,
  `seller_nickname`, `seller_type_persona/status/comment`
- `telegram_client.py`, `webhook_client.py`, `wecom_app_client.py`: render new fields
- `result_pipeline_service.py`: passes `_seller_type_*` context keys from AI analysis
- WeCom App TextCard: plain-text description only, no raw HTML links
- Webhook: 8 new template vars (`${region}`, `${tags}`, `${badges}`, etc.)
- 8 new unit tests; all 191 existing tests still pass

**Deployment impact:**
- Requires service restart
- No schema changes
- No frontend build required (backend-only)
- Enriched fields are optional and default safely — zero behavior change if source
  data is absent

### P4-1 — Notification threshold + dedup seam
**Commits:** `4d0fdb7`, `0514187`, merge `a705edb`

- `src/services/notification_filter.py` (new, 374 lines):
  - `derive_recommendation_score()` / `derive_recommendation_level()` pure functions
  - `InMemoryDedupStore` (TTL-based, no DB writes)
  - `NotificationPolicy` dataclass
  - `evaluate_notification()` decision function
- `src/infrastructure/config/settings.py`: 4 new env-only fields (P4-1 三项 + P4-3 一项):
  - `NOTIFICATION_MIN_SCORE` (default: unset = no threshold)
  - `NOTIFICATION_MIN_LEVEL` (default: unset = no threshold)
  - `NOTIFICATION_DEDUP_WINDOW_SECONDS` (default: 0 = no dedup)
  - `NOTIFICATION_SELLER_THROTTLE_WINDOW_SECONDS` (default: 0 = no seller throttle, P4-3)
  - Intentionally NOT in `NOTIFICATION_FIELD_MAP` — not exposed via `/settings/notification` UI
- `src/services/result_pipeline_service.py`: accepts optional `policy`/`dedup_store`;
  `from_settings()` factory auto-derives from env; `ResultPipelineOutcome` gains
  `skip_reason`/`decision` audit fields
- `src/services/item_analysis_dispatcher.py`: default path uses `from_settings()`
- 21 new unit tests (filter), +8 pipeline tests; 221 total pass

**Deployment impact:**
- Requires service restart
- No schema changes, no frontend build
- **Zero behavior change by default** — all thresholds unset, dedup disabled
- To activate: set env vars in `.env` and restart

---

## In-Progress Phases (not in this batch)

| Phase | Status | Notes |
|-------|--------|-------|
| P4-1  | Landed | Included above (merged after batch started) |
| P3-3  | Running | Result batch operations: select, mark, hide, export |
| P3-4  | Running | Seller aggregation result view seam |

---

## Verification Results (R5, 2026-05-30)

```
git diff --check origin/master..HEAD   → EXIT:0 (no whitespace errors)
python3 -m compileall src/ -q          → COMPILE_EXIT:0 (clean)
pytest -q                              → 221 passed, 3 skipped, 1 warning in 2.53s
vite build                             → ✓ built in 8.98s
```

Test breakdown:
- 221 unit + integration tests pass
- 3 skipped (marked `live` — require real credentials/external services)
- 1 warning: httpx/starlette deprecation (cosmetic, not a failure)

---

## Deployment Checklist

- [ ] `git push origin master` (or open PR from this branch)
- [ ] On NAS: `docker compose pull && docker compose up -d` (or rebuild from fork)
- [ ] Verify migration ran: check `result_items` has `is_processed`/`is_contacted` columns
- [ ] Verify new flag buttons appear in ResultCard footer
- [ ] Optional: set `NOTIFICATION_MIN_SCORE` / `NOTIFICATION_DEDUP_WINDOW_SECONDS` / `NOTIFICATION_SELLER_THROTTLE_WINDOW_SECONDS` in `.env`
      to activate P4-1 threshold/dedup or P4-3 per-seller throttle (safe to leave unset; see `docs/runbooks/notification-throttle-ops.md` for staged rollout and rollback)
- [ ] No rollback risk on schema: all `ALTER TABLE` are additive with DEFAULT values

---

## Files Changed (summary)

Backend (src/):
- `src/api/routes/results.py` (+39)
- `src/infrastructure/config/settings.py` (+20)
- `src/infrastructure/external/notification_clients/base.py` (+28)
- `src/infrastructure/external/notification_clients/telegram_client.py` (+11)
- `src/infrastructure/external/notification_clients/webhook_client.py` (+17)
- `src/infrastructure/external/notification_clients/wecom_app_client.py` (+14)
- `src/infrastructure/persistence/sqlite_connection.py` (+22, migration)
- `src/services/item_analysis_dispatcher.py` (+8)
- `src/services/notification_filter.py` (new, +374)
- `src/services/result_pipeline_service.py` (+126+17=+143)
- `src/services/result_storage_service.py` (+92)

Tests:
- `tests/integration/test_api_results.py` (+160+25=+185)
- `tests/unit/test_notification_filter.py` (new, +258)
- `tests/unit/test_notification_service.py` (+356)
- `tests/unit/test_result_pipeline_service.py` (+187+8=+195)

Frontend (web-ui/src/):
- `api/results.ts` (+15)
- `components/results/ResultCard.vue` (+35)
- `components/results/ResultsFilterBar.vue` (+33)
- `components/results/ResultsGrid.vue` (+3)
- `composables/resultQuery.assertions.ts` (new, +86)
- `composables/resultQuery.ts` (+91+12=+103)
- `composables/useResults.ts` (+15-85=-70)
- `i18n/messages/en-US.ts` (+9)
- `i18n/messages/zh-CN.ts` (+9)
- `types/result.d.ts` (+2)
- `views/ResultsView.vue` (+6)

Docs:
- `AGENTS.md` (+15)
- `docs/plans/2026-05-30-stabilization-and-observability.md` (+14)
