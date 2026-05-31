# Notification Throttle Ops Runbook

> 通知降噪 / 限流 4 个 env-only 开关的运维侧最小说明。代码契约见 `AGENTS.md` 第 “P4-1 通知降噪契约” 一节；评估与方案背景见 `docs/plans/2026-05-30-stabilization-and-observability.md` § P4。本手册只覆盖运维启用/回滚步骤。

## 适用范围

- 仅作用于 AI 推荐链路 `ResultPipelineService._notify_if_recommended`：仅当 `ai_analysis.is_recommended=True` 才会进入决策。
- **不影响**任务暂停/失败告警（`scraper.py` / `process_service.py` 走原通道）。
- 4 个开关默认全部关闭，未配置时行为与 P3 完全一致（AI 推荐即通知）。
- 4 个字段**刻意不出现在** `/settings/notification` UI；只能通过 `.env` / 环境变量配置后重启服务生效。

## 4 个开关

| 环境变量 | 默认 | 含义 | 启用值示例 |
|----------|------|------|-----------|
| `NOTIFICATION_MIN_SCORE` | 留空 = 不过滤 | 推荐分阈值（0..100 浮点）；低于该分跳过通知 | `60` |
| `NOTIFICATION_MIN_LEVEL` | 留空 = 不过滤 | 推荐等级阈值；取 `low` / `medium` / `high` | `medium` |
| `NOTIFICATION_DEDUP_WINDOW_SECONDS` | `0` = 关闭 | 同商品（按 `商品ID > 规范化商品链接`）短窗口去重秒数 | `3600` |
| `NOTIFICATION_SELLER_THROTTLE_WINDOW_SECONDS` | `0` = 关闭 | 同卖家（按 `seller_id > 卖家信息.卖家ID > 卖家昵称 > 卖家主页`）短窗口限流秒数 | `1800` |

注意：

- `min_score` 与 `min_level` 互相独立，同时设置时**两者都要满足**才放行。
- 所有非空字段为 0 / None 时 `_policy_from_env` 直接返回空策略，等价于不启用。
- dedup 与 seller throttle 互相独立：同卖家不同商品各发一次，同商品同卖家在窗口内只发一次。
- 缺失全部卖家字段时 seller throttle 自动放行，不影响 item dedup。
- 状态在进程内（`InMemoryDedupStore`），重启服务即清空，不写 SQLite，不持久化。

## 推荐启用顺序

按从“最容易回滚”到“最影响范围”依次开启，每步至少观察一个完整任务周期：

1. **先开 dedup**：`NOTIFICATION_DEDUP_WINDOW_SECONDS=3600`
   - 风险最低；只压制同一商品的重复通知。
   - 观察 1–2 个任务运行周期，确认未漏掉新商品。
2. **再开 seller throttle**：`NOTIFICATION_SELLER_THROTTLE_WINDOW_SECONDS=1800`
   - 多账号刷同卖家时收效明显；需注意同卖家不同商品也会被合并到一次通知。
   - 缺失全部卖家字段时自动放行，关键词任务通常不受影响。
3. **再加分级阈值**：`NOTIFICATION_MIN_LEVEL=medium`（或 `high`）
   - 直接砍掉 low 推荐；如果误杀价值商品，先回退到此步前。
4. **最后再上 score**：`NOTIFICATION_MIN_SCORE=60`
   - 评分启发式仍是基于 `criteria_analysis` PASS/WARN/FAIL/UNKNOWN 的过渡实现，建议作为最后一档微调。

启用任何一档都需要重启服务（env 仅在启动时读入）。

## 回滚

每个开关都可以独立回滚。两种方式：

- **完全回滚到 P3 行为**：把 4 个变量从 `.env` 删除（或全部置空 / `0`），然后重启服务。`_policy_from_env` 返回空，`ResultPipelineService` 退回 `is_recommended=True` 即通知的旧路径。
- **部分回滚**：只回滚最近一档（例如刚开 score 后误杀，把 `NOTIFICATION_MIN_SCORE` 删掉，保留 dedup/seller/level），再重启服务。

## 切换平滑性

- 启用窗口的瞬间，`evaluate_notification` 在 inert 策略下也会 `dedup_store.mark` / `seller_throttle_store.mark`，避免一开窗口就把历史 key 全部当“首次出现”重发。
- 即便如此，第一次启用 dedup / seller throttle 的“开关瞬间”仍可能发出当前批次内已经被 AI 推荐过的少量通知；建议在低峰期切换。

## 排障

- 启用后通知数量没下降：先确认 `.env` 已挂载到容器（Docker 部署时 `docker compose config | grep NOTIFICATION_`），再确认服务**已重启**。
- 想查看具体 skip 原因：`ResultPipelineOutcome` 带有 `skip_reason` / `decision` 字段；这些字段目前只在内部日志/单测里出现，并未透出到 UI。
- 误以为关掉了 UI 设置就关掉了降噪：UI `/settings/notification` 与这 4 个开关**没有任何耦合**，UI 改动不会影响降噪策略。

## 相关代码与契约

- 决策入口：`src/services/notification_filter.py::evaluate_notification`
- 策略派生：`src/services/result_pipeline_service.py::_policy_from_env`
- 字段定义：`src/infrastructure/config/settings.py::NotificationSettings`（带刻意不进 UI 的设计注释）
- 契约描述（开发侧）：`AGENTS.md` § “P4-1 通知降噪契约”
- 评估方案（背景）：`docs/plans/2026-05-30-stabilization-and-observability.md` § P4
