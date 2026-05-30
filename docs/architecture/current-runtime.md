# Current runtime

`xianyu-tools / 闲鱼工具箱` currently preserves the ai-goofish-monitor runtime
architecture.

## Fork delta from upstream

This fork is maintained as `xianyu-tools / 闲鱼工具箱` after diverging from
upstream `ai-goofish-monitor`. Runtime compatibility is intentional: the task
process still reaches `scrape_xianyu(task_config, debug_limit)`, while newer
services and persistence paths are introduced through a strangler-style gradual
refactor instead of a full repository rewrite.

- Docker Compose builds `xianyu-tools:local` from the local source tree by
  default. The upstream official image does not include, or does not guarantee,
  this fork's local-only changes.
- The primary runtime stack is FastAPI, Vue, Playwright, and SQLite.
- SQLite is the primary store for tasks, results, and price history, with
  compatibility import from legacy `config.json`, `jsonl/`, and
  `price_history/` sources.
- Notification delivery supports WeCom App, Telegram, and generic Webhook.
  The Web UI can persist settings into `.env`. Legacy `ntfy`, Bark, WeChat bot,
  and Gotify values are compatibility / ignored settings rather than active
  delivery channels.
- Task search filtering wires through `yhb_only` / YHB inspection, free
  shipping, personal seller, publish time, region, and price filters. The Web
  UI task form groups these settings into collapsible sections.
- Result browsing and CSV export share YHB, free-shipping, and AI
  `seller_type` personal-seller filtering semantics.
- Account and proxy rotation, task-account binding, and retry handling are part
  of the runtime path. `failure_guard` detects cookie changes with a fingerprint
  made from `mtime_ns`, `size`, and `sha256`, avoiding recovery failures when
  file `mtime` does not advance.

## Flow

1. `src/app.py` creates the FastAPI application and wires API routes.
2. Task start requests flow through `src/services/process_service.py`.
3. `ProcessService` launches `spider_v2.py --task-name ...` as a task process.
4. `spider_v2.py` loads task configuration and calls
   `src.scraper.scrape_xianyu(task_config, debug_limit)`.
5. `src/scraper.py` drives Playwright browser/session setup, Xianyu search,
   pagination, item detail collection, seller profile collection, filtering,
   AI or keyword analysis, result persistence, and notification. Task search
   filters include personal seller, free shipping, YHB/验货宝-only,
   fresh-listing window, region, and price range.
6. Search pagination helpers live in `src/services/search_pagination.py`.
7. AI analysis is split across `src/ai_handler.py`,
   `src/services/item_analysis_dispatcher.py`, and related compatibility code.
8. Results are stored through SQLite-backed services and legacy-compatible JSONL
   paths.
9. Notification delivery uses `src/services/notification_service.py` and
   clients under `src/infrastructure/external/notification_clients/`.

## Storage

- SQLite is the primary store for tasks, results, and price history.
- Legacy `config.json`, `jsonl/`, and `price_history/` data are still imported
  for compatibility.
- `state/`, `prompts/`, `logs/`, and `images/` remain filesystem-backed runtime
  directories.
- Docker Compose bind-mounts `.env` to `/app/.env`, so Web UI settings writes
  are persisted to the repository `.env` when using the default compose file.

## Hotspots

- `src/scraper.py`: browser/session setup, task normalization, scraping loop,
  data extraction, analysis dispatch, storage, and notifications are still in
  one module.
- Configuration is split across environment, task dictionaries, repository
  models, and runtime-only normalization.
- AI request and response handling has compatibility layers in multiple modules.
- `web-ui/src/components/tasks/TaskForm.vue` owns form state, validation,
  scheduling, account strategy, AI mode, keyword mode, region selection, seller
  publication filters, and notification targets.
