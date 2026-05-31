# PR Draft: xianyu-tools Stabilization & Result Management Batch

**Branch:** local `master` (not pushed; currently ahead of `origin/master`)
**Prepared:** 2026-05-30
**Status:** local release-readiness draft; do not push/open PR/deploy until operator approval.

---

## Summary

This batch turns the fork from a feature-complete prototype into a more stable day-to-day monitoring tool while preserving the runtime contract `scrape_xianyu(task_config, debug_limit)`.

Key outcomes:

- Result management is now usable for real follow-up work: sort/query persistence, processed/contacted flags, batch operations, seller aggregation, and small seller-panel UX improvements.
- Notifications are less noisy and more informative: enriched message content, env-only threshold/dedup controls, and per-seller throttling.
- Operational handoff is clearer: local smoke runbook/script, fork upgrade checklist, notification throttle runbook, and final QA coverage.

---

## Landed phases in this local branch

| Phase | Title | Representative commits |
|-------|-------|------------------------|
| P3-1b | Result sort regression tests + resultQuery refactor | `513402e` |
| P3-2 | Processed/contacted result user flags | `25e7c3e` |
| P4-2 | Notification content enrichment | `d3ab828` |
| P4-1 | Notification threshold + item dedup seam | `4d0fdb7`, `0514187`, merge `a705edb` |
| P3-3 | Result batch operations | `4d1e270`, `803f295`, merge `f118968` |
| D6 | Fork upgrade / redeploy checklist | `0c8a135`, merge `d7ac1ee` |
| P4-3 | Per-seller notification throttling seam | `ec9ab61`, merge `c3d417a` |
| P3-4 | Seller aggregation endpoint + panel | `1ed5235`, `bcedb6f`, merge `cb5d459` |
| A8 | Result API/frontend type contract tightening | `f533b84`, merge `9d8d569` |
| Q7 | Result-management QA edge-case tests | `297111e`, merge `742f162` |
| D7 | Notification throttle runbook / env docs | `c682263`, merge `c51e017` |
| P3-5 | Seller-level next-step design + top-N seller panel UX | `69630dc`, merge `fe5a789` |
| R7 | PR draft refresh + validation | `d25113c`, merge `44aed76` |
| M9-2 | Seller click-through filter UX | `21ebd93`, merge `bfc3a04` |
| M9-3 | Disposable smoke + packaging verification | (smoke-only; no source change) |

---

## Changes by area

### Result management

- URL/query behavior:
  - canonical combined `sort` param with legacy `sort_by` / `sort_order` compatibility
  - result filters survive refresh/share via URL query
- User-state flags:
  - `_is_processed` and `_is_contacted` stored separately from visibility `_status`
  - filters: `processed_only`, `contacted_only`, `hide_processed`
  - CSV export honors active filters
- Batch operations:
  - `PATCH /api/results/{filename}/items/batch`
  - supports batch `status`, `is_processed`, `is_contacted`
  - frontend selection toolbar: mark processed/contacted, hide/unhide, clear, export current filter
- Seller aggregation:
  - `GET /api/results/{filename}/sellers`
  - seller count, item count, price range, latest crawl time, recommendation count, seller-persona summary
  - SellersPanel shows top sellers, now with top-N expand/collapse
- Seller click-through filter (M9-2):
  - `seller` query parameter filters result list and CSV export by seller nickname
  - no schema change; matching uses `卖家信息.卖家昵称` with `商品信息.卖家昵称` fallback
  - SellersPanel click applies the URL-persisted seller filter and shows a clearable active-filter chip

### Notification strategy

- Enriched content:
  - region, tags, free shipping, inspection-service badge, seller nickname, seller-persona context
  - WeCom App TextCard keeps description plain text and URL in `textcard.url`
- Env-only noise controls, all disabled by default:
  - `NOTIFICATION_MIN_SCORE`
  - `NOTIFICATION_MIN_LEVEL`
  - `NOTIFICATION_DEDUP_WINDOW_SECONDS`
  - `NOTIFICATION_SELLER_THROTTLE_WINDOW_SECONDS`
- Runtime behavior:
  - zero behavior change when env vars are unset / `0`
  - item dedup and seller throttle are in-memory TTL stores; restart clears them
  - operational rollout/rollback documented in `docs/runbooks/notification-throttle-ops.md`

### Documentation and operations

- `docs/runbooks/local-smoke.md` and `scripts/smoke_check.py` for non-mutating local smoke.
- README fork upgrade / redeploy checklist refreshed.
- `docs/runbooks/notification-throttle-ops.md` added as notification-throttle runbook.
- `docs/notes/p3-5-seller-level-next-step.md` records seller-level next-step decision:
  - seller details/filter/compare can reuse existing result items and aggregation data without schema changes
  - persistent seller watch/notes require a new table or config store and should be a separate confirmed feature

---

## Deployment impact

- Requires service restart to load backend/API changes and env-only notification controls.
- Requires frontend rebuild because result UI and settings/result components changed.
- SQLite migration impact:
  - P3-2 adds `is_processed` and `is_contacted` to `result_items`
  - additive/idempotent `ALTER TABLE ... ADD COLUMN`
  - no destructive migration
- No production `.env`, cookies, `state/`, NAS files, or real user data were changed by this local work.
- Optional notification-throttle env vars are safe to leave unset.

---

## Verification snapshot

Latest local verification after merging M9-2 (seller click filter) and M9-3 (disposable smoke):

```bash
git diff --check                                            # pass
/tmp/xianyu-tools-r4-venv/bin/python -m pytest -q         # 248 passed, 3 skipped (M9-3 smoke run)
cd web-ui && npm run build                                  # pass
```

Earlier review gates also ran targeted/full suites, including:

- M9-3: disposable smoke + packaging verification; 16 targeted tests, web-ui build, smoke_check, openapi check — all pass
- M9-2: seller click filter — backend result/export seller query coverage added to `test_api_results.py`; targeted result/seller suite passed; no schema change
- Q7: result API + QA edge tests, full suite reported green by worker (`242 passed, 3 skipped` at that point)
- A8: result API/seller aggregation targeted tests + frontend build
- D7: markdown-only `git diff --check`
- P3/P4 implementation cards: targeted unit/integration tests per task handoff

Before push/deploy, run final quality gate:

```bash
cd /root/projects/xianyu-tools
git diff --check
/tmp/xianyu-tools-r4-venv/bin/python -m pytest -q
cd web-ui && npm run build
```

---

## Release checklist

- [x] M9-3 quality gate passed: `git diff --check`, `pytest -q` (248 passed, 3 skipped), `web-ui npm run build`.
- [ ] Push local `master` or open a PR only after user approval.
- [ ] Rebuild/redeploy target service only after user approval.
- [ ] Confirm production `.env` intentionally leaves notification thresholds unset, or apply staged rollout from `docs/runbooks/notification-throttle-ops.md`.
- [ ] After restart, verify:
  - result page loads and flags/batch operations render
  - seller panel renders and expand/collapse works
  - existing task execution still calls `scrape_xianyu(task_config, debug_limit)` normally
  - notification channels still work with existing settings

---

## Known follow-ups / not included

- Seller detail/filter route can be a small no-schema follow-up PR.
- Persistent seller watchlist / seller notes need schema or config-store design and explicit confirmation before implementation.
- No GitHub push, PR creation, NAS deploy, production restart, or production DB write has been executed in this batch.
