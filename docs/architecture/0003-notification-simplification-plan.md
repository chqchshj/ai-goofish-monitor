# ADR 0003: Notification channel simplification plan

Status: Proposed
Date: 2026-05-29
Task: `t_06ea21e6`

## Context

The repository currently carries notification support inherited from upstream plus fork-local additions. The user's simplification preference is to keep Enterprise WeChat application messages (`wecom_app`) and task-level notification routing (`notification_targets`), and to retire notification channels that are not commonly used, but only after an audit and compatibility plan.

This ADR is documentation-only. It does not remove code, env keys, UI, tests, or persisted task data.

## Current notification channels

Backend global channels are assembled by `src/infrastructure/external/notification_clients/factory.py::build_notification_clients()` from `NotificationSettings` in `src/infrastructure/config/settings.py` and env values loaded through `src/services/notification_config_service.py`.

Current globally configurable channels:

- `ntfy`
  - Env: `NTFY_TOPIC_URL`
  - Client: `src/infrastructure/external/notification_clients/ntfy_client.py`
  - Enabled when topic URL is present.
- `bark`
  - Env: `BARK_URL`
  - Client: `bark_client.py`
  - Enabled when Bark URL is present.
- `gotify`
  - Env: `GOTIFY_URL`, `GOTIFY_TOKEN`
  - Client: `gotify_client.py`
  - Enabled only when URL and token are both present.
- `wecom`
  - Env: `WX_BOT_URL`
  - Client: `wecom_bot_client.py`
  - Enterprise WeChat group bot webhook. Enabled when webhook URL is present.
- `wecom_app`
  - Env: `WECOM_APP_CORPID`, `WECOM_APP_SECRET`, `WECOM_APP_AGENTID`, optional `WECOM_APP_TOUSER`
  - Client: `wecom_app_client.py`
  - Enterprise WeChat application TextCard messages. Enabled when corpid, secret, and agentid are present; default recipient falls back to `@all` if `WECOM_APP_TOUSER` is empty.
- `telegram`
  - Env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, optional `TELEGRAM_API_BASE_URL`
  - Client: `telegram_client.py`
  - Enabled only when bot token and chat id are both present.
- `webhook`
  - Env: `WEBHOOK_URL`, `WEBHOOK_METHOD`, `WEBHOOK_HEADERS`, `WEBHOOK_CONTENT_TYPE`, `WEBHOOK_QUERY_PARAMETERS`, `WEBHOOK_BODY`
  - Client: `webhook_client.py`
  - Enabled when URL is present; supports GET/POST, JSON/FORM, headers/query/body templates.

Shared behavior:

- `NotificationClient._build_message()` centralizes title, price, reason, desktop/mobile links, and main image extraction.
- `PCURL_TO_MOBILE` controls whether desktop Goofish item links are converted to mobile links.
- `NotificationService.send_notification()` sends to all resolved enabled clients concurrently and returns per-channel status.
- Empty or missing task targets preserve legacy behavior: send to all globally enabled clients.

## Current call paths

Recommendation notification path:

1. `src/scraper.py::scrape_xianyu()` loads `runtime_config.notification_targets`.
2. For each candidate item, scraper builds `ItemAnalysisJob(..., notification_targets=notification_targets)`.
3. `src/services/item_analysis_dispatcher.py` saves the record, then calls `_notify_if_recommended()` only when `analysis_result.is_recommended` is truthy.
4. `_notify_if_recommended()` calls the injected notifier, currently `src.ai_handler.send_ntfy_notification()`.
5. `send_ntfy_notification()` builds `NotificationService` and calls `send_notification(product_data, reason, targets)`.
6. `NotificationService._resolve_clients()` uses global clients when targets are empty, otherwise calls `build_notification_clients_for_targets(settings, targets)`.

Task failure / pause notification path:

- `src/scraper.py::_notify_task_failure()` and failure guard pause paths call `send_ntfy_notification(product_data, notify_reason)` without task-level targets, so they always use global default channels.
- `src/services/process_service.py::_notify_skip()` also calls `send_ntfy_notification()` for failure-guard skip notifications.

Settings API path:

- `GET /api/settings/notifications` returns masked settings via `build_notification_settings_response()`.
- `PUT /api/settings/notifications` validates and persists env changes via `prepare_notification_settings_update()` and `env_manager.apply_changes()`.
- `POST /api/settings/notifications/test` builds a temporary `NotificationSettings` model and sends test notifications. A channel-specific test uses only that channel's env fields plus `PCURL_TO_MOBILE`.
- `GET /api/settings/notifications/wecom-app/departments` and `/users` fetch Enterprise WeChat contacts using the configured app credentials for the task recipient picker.

Task API and persistence path:

- Domain models in `src/domain/models/task.py` validate `notification_targets` and allow only `telegram`, `wecom_app`, `wecom`, and `default` for task-level routing.
- SQLite stores task targets in `tasks.notification_targets_json`; legacy `config.json` import preserves `notification_targets` into that column.
- API create/generate/update payloads carry `notification_targets` through task models and `TaskGenerationRunner`.

Frontend path:

- Global settings UI: `web-ui/src/components/settings/NotificationSettingsPanel.vue` exposes all seven global channels and per-channel test buttons.
- Task form UI: `web-ui/src/components/tasks/TaskNotificationTargets.vue` exposes task-level targets for `telegram`, `wecom_app`, `wecom`, and `default`; it intentionally does not expose `ntfy`, `bark`, `gotify`, or generic `webhook` as per-task targets.
- `wecom_app` task targets include a user/department picker backed by the settings API, while still storing a plain `recipient` string (`@all` or `userid1|userid2`).

## Active vs legacy / low-value assessment

Actively used or strategically important:

- `wecom_app`: keep. It is the fork-specific channel, supports direct Enterprise WeChat app delivery, has contact picker support, and matches the user's stated preference.
- `notification_targets`: keep. It is the desired task-level routing layer. Empty targets must continue to mean global defaults.
- `default` target sentinel: keep. It lets a task mix explicit recipients with global channels and is required for backward-compatible UI semantics.

Compatibility-useful but lower priority:

- `telegram`: keep for now, but do not expand. It is already part of task-level routing and common for external users; removal would break existing task configs more often than niche channels.
- `wecom`: deprecate rather than immediately remove. It overlaps with `wecom_app` but remains useful as a simple group-bot fallback and is already supported in task-level routing. Prefer migrating real usage to `wecom_app`.

Legacy / low-value candidates for retirement:

- `ntfy`: deprecate globally. It is inherited upstream/default-simple notification support but has no task-level target routing and is not part of the preferred local workflow.
- `bark`: deprecate globally. iOS-specific, no task-level target routing, and adds UI/config/test surface with little value for this fork.
- `gotify`: deprecate globally. Self-hosted push channel, no task-level target routing, likely redundant with `wecom_app` or `webhook`.
- `webhook`: keep as an advanced/hidden compatibility channel for one release, then decide. It is generic and useful for integrations, but it has the broadest settings surface and highest UI complexity. If the project aims at a minimal local tool, move it behind an advanced section before removing.

## Proposed keep / deprecate / remove list

Keep as first-class:

- `wecom_app`
- task-level `notification_targets`
- task-level target channels: `wecom_app`, `telegram`, `wecom`, `default`
- `PCURL_TO_MOBILE`

Deprecate in the next code-changing step, without runtime breakage:

- `ntfy`
- `bark`
- `gotify`
- `wecom` group bot, with migration guidance to `wecom_app`

Move to advanced compatibility before possible removal:

- `telegram`
- `webhook`

Remove only after a compatibility window:

- Global settings cards, env docs, client factory entries, status flags, and tests for deprecated channels that have no configured usage.
- The old function name `send_ntfy_notification` should be renamed only after notification simplification stabilizes. Keep a wrapper alias during migration because scraper/process code still imports it.

## Migration and backward-compatibility plan

Phase 1: Deprecation-only UI/docs cleanup

- Add visible labels in docs/UI that `wecom_app` is preferred.
- Move `ntfy`, `bark`, `gotify`, and optionally `webhook` under an advanced/legacy section rather than deleting immediately.
- Keep all env keys readable and keep `build_notification_clients()` behavior unchanged.
- Add tests proving `CONFIGURED_CHANNELS` and `/api/settings/status` still report existing configured legacy channels.

Phase 2: Compatibility telemetry / explicit warnings

- On settings load, surface configured legacy channels in a warning banner: configured legacy channels still work, but new task routing should use `wecom_app`.
- Add a small helper such as `get_deprecated_notification_channels(settings)` so API/UI/tests do not hard-code warning logic in several places.
- Do not write to `.env`, production DB, state files, or NAS deployment files automatically.

Phase 3: Safe retirement

- Remove global settings UI cards for `ntfy`, `bark`, and `gotify` only after confirming no active deployment depends on their env keys.
- Keep backend env parsing and clients for at least one release after UI removal so old `.env` files still send notifications.
- After the compatibility window, remove backend clients and env fields in a dedicated small commit.
- For existing tasks:
  - `notification_targets=[]` keeps using remaining global defaults.
  - Unknown removed target channels should be ignored with a warning rather than failing task load.
  - `wecom` targets can be migrated manually to `wecom_app` recipients if the webhook represented the same audience.

Phase 4: Naming cleanup

- Rename `send_ntfy_notification()` to `send_product_notification()` and leave `send_ntfy_notification = send_product_notification` as a compatibility alias for one release.
- Update scraper/process imports in a separate small commit.

## Existing task config implications

Current persisted task targets can only contain `telegram`, `wecom_app`, `wecom`, or `default`; `ntfy`, `bark`, `gotify`, and `webhook` are global-only today. Therefore retiring global-only channels does not require a SQLite task migration for `notification_targets_json`.

The key compatibility risks are:

- Tasks with empty targets will send to fewer global channels after removal.
- Failure-guard and task-failure notifications currently have no task targets and always use global defaults; they must still have at least one configured global channel after simplification, preferably `wecom_app`.
- Global `.env` files may contain legacy channel secrets. Removal should not delete env values automatically; cleanup should be explicit and operator-controlled.

## Test plan

Backend unit tests:

- `tests/unit/test_notification_service.py`
  - Empty targets use globally configured clients.
  - `telegram`, `wecom_app`, and `wecom` task targets override recipients/webhook URL correctly.
  - Duplicate target channels are indexed as `channel`, `channel:2`, etc.
  - Unknown or deprecated target channels are handled according to the chosen migration behavior.
- Client tests:
  - `wecom_app` TextCard payload keeps links in `textcard.url`, not raw HTML in `description`.
  - `webhook` template rendering remains covered while webhook is retained.

Backend integration tests:

- `tests/integration/test_api_settings.py`
  - `GET /api/settings/notifications` masks secrets and returns configured channels.
  - `PUT /api/settings/notifications` validates required groups/pairs.
  - Channel-specific test requests only send the requested channel.
  - WeCom app contacts endpoints require app credentials and propagate API errors.
- Task API tests:
  - Create/update/generate preserve `notification_targets`.
  - Legacy empty targets continue to mean global defaults.
  - Existing SQLite task rows with `notification_targets_json=[]` still load.

Frontend tests / checks:

- Build: `cd web-ui && npm run build`.
- Task form regression:
  - Create/edit preserves field order and existing task values.
  - `TaskNotificationTargets.vue` can add/remove targets without submitting the form accidentally.
  - `default` target clears recipient.
  - `wecom_app` picker loads departments/users and writes `userid1|userid2` or `@all`.
- Settings UI regression:
  - Preferred `wecom_app` settings remain first-class.
  - Deprecated channels, if hidden/moved, are still visible when already configured or accessible in advanced mode.
  - Secret fields remain masked and clearing a channel only clears the intended fields.

Manual smoke tests, only with explicit credentials/scope:

- Send `wecom_app` test notification to `@all` and one explicit user id.
- Run one low-frequency task with `notification_targets=[{"channel":"wecom_app","recipient":"..."}]` and confirm only the intended recipient is notified.
- Run one task with empty targets and confirm global fallback still works.

## Decision

Proceed with a small follow-up implementation that keeps `wecom_app` and `notification_targets` as the primary path, deprecates inherited global-only channels in UI/docs first, and delays backend removal until after a compatibility window. Do not combine notification retirement with scraper, Playwright, account/proxy, scheduler, or database schema refactors.
