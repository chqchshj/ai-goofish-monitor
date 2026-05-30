# xianyu-tools Next Phase Implementation Plan

> **For Hermes:** Use Kanban review-gated implementation. Every code-changing task must commit a small checkpoint and block with `review-required:` for parent review.

**Goal:** Stabilize the newly refactored fork, prove the real runtime path, then continue UI and product improvements without losing scraper compatibility.

**Architecture:** Keep the existing FastAPI + Vue + Playwright + SQLite architecture. Continue strangler-style refactors: small seams, narrow commits, and explicit verification. Do not rewrite the scraper or change `scrape_xianyu(task_config, debug_limit)` compatibility.

**Global constraints:**
- Do not touch production `.env`, `state/`, cookies, NAS data, or secrets except through already-mounted Web UI settings flows explicitly requested by the user.
- Any database write must first be described with the exact task/payload and must wait for human confirmation unless the task is explicitly limited to disposable test DB files.
- Preserve Playwright login, risk-control, account, proxy, and notification semantics.
- Keep user-facing summaries and Kanban comments in Chinese.

---

## Task Graph

1. **T0 Publish current follow-up fixes**
   - Push local commits for collapsed notification UI, restored `yhb_only`, and docs.
   - Open or update a small follow-up PR against `master`.
   - Block `review-required` with PR URL, commit list, and verification evidence.

2. **T1 Local smoke plan and non-mutating verification** — parent: T0
   - Verify container, settings page, task form UI, and API/schema without writing production DB.
   - If a real create-task smoke is needed, prepare exact payload and block for human confirmation before POSTing.

3. **T2 Task form UI consolidation** — parent: T1
   - Collapse the long create/edit task dialog into clear sections: 基础信息、判断方式、搜索筛选、定时/账号、通知对象.
   - Keep field order and payload semantics stable.
   - Commit and block `review-required`.

4. **T3 Results filtering improvements** — parent: T2
   - Add or refine result-page filters for YHB/验货宝, 包邮, and 个人卖家 via AI `seller_type` persona where data is available.
   - Add tests around query parameters/filter persistence.
   - Commit and block `review-required`.

5. **T4 Deployment/docs cleanup and handoff** — parent: T3
   - Clean `.env.example` / README / docs for retained notification channels and default compose mounts.
   - Run final targeted/full verification and Docker smoke.
   - Open/update final PR and block `review-required` for merge.

---

## Verification Commands

Baseline commands expected across tasks:

```bash
cd /root/projects/xianyu-tools
/tmp/xianyu-tools-r4-venv/bin/python -m compileall -q src tests
/tmp/xianyu-tools-r4-venv/bin/python -m pytest tests/unit/test_domain_task.py tests/unit/test_task_runtime_config.py tests/unit/test_sqlite_task_repository.py tests/unit/test_xianyu_filters.py tests/integration/test_api_tasks.py -q
cd web-ui && npm run build
```

For payload helper changes:

```bash
cd /root/projects/xianyu-tools
tmpdir=$(mktemp -d)
cp web-ui/src/components/tasks/taskFormPayload.ts web-ui/src/components/tasks/taskFormPayload.assertions.ts "$tmpdir"/
perl -0pi -e "s/from '\\.\/taskFormPayload'/from '.\/taskFormPayload.ts'/" "$tmpdir/taskFormPayload.assertions.ts"
node --experimental-strip-types "$tmpdir/taskFormPayload.assertions.ts"
```

For final handoff:

```bash
cd /root/projects/xianyu-tools
/tmp/xianyu-tools-r4-venv/bin/python -m pytest -q
cd web-ui && npm run build
docker build --pull=false -t xianyu-tools:review .
```

## Final Handoff Notes

- Retained notification channels are WeCom app, Telegram, and generic Webhook. Legacy `NTFY_TOPIC_URL`, `GOTIFY_*`, `BARK_URL`, and `WX_BOT_URL` remain documented as ignored compatibility values rather than active channels.
- Default Compose deployment builds `xianyu-tools:local` from the working tree and mounts `data/`, `state/`, `prompts/`, `logs/`, `images/`, plus legacy import sources `config.json`, `jsonl/`, and `price_history/`.
- Task-form UI uses collapsible sections; `yhb_only` is preserved from form payload through runtime config to Xianyu search filters.
- Results and export filters now cover 验货宝, 包邮, and 仅看个人卖家. The personal-seller filter uses AI `ai_analysis.criteria_analysis.seller_type`; missing/keyword/legacy records do not match it.
