"""
结果持久化与推荐通知分发。

P4-1 起接入了通知降噪 seam:
- 可选 ``policy`` (``NotificationPolicy``) 控制阈值与去重窗口。
- 可选 ``dedup_store`` 配合 ``policy.dedup_window_seconds`` 抑制短窗口重复通知。

默认行为完全兼容: 不传 ``policy`` 时等价于 P3 时期的逻辑 ——
``ai_analysis.is_recommended`` 为真即通知, 否则不通知, 落盘照常。
"""
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from src.services.notification_filter import (
    DedupStore,
    InMemoryDedupStore,
    NotificationDecision,
    NotificationPolicy,
    evaluate_notification,
)


Notifier = Callable[[dict, str, Optional[list[dict]]], Awaitable[None]]
Saver = Callable[[dict, str], Awaitable[bool]]


def _policy_from_env(
    settings,
) -> tuple[Optional[NotificationPolicy], Optional[DedupStore]]:
    """从 NotificationSettings 构造 (policy, dedup_store) 二元组。

    settings 缺失或所有字段为默认值时返回 (None, None), 调用方据此保留旧行为。
    settings 可以是 ``NotificationSettings``, 也可以是 duck-typed 对象, 只要有
    同名属性即可。这样 P4-2 把 UI 配置接进来时不需要改这里。
    """
    if settings is None:
        return None, None

    min_score = getattr(settings, "notification_min_score", None)
    min_level_raw = getattr(settings, "notification_min_level", None)
    dedup_window = getattr(settings, "notification_dedup_window_seconds", 0) or 0

    min_level: Optional[str] = None
    if isinstance(min_level_raw, str):
        candidate = min_level_raw.strip().lower()
        if candidate in {"low", "medium", "high"}:
            min_level = candidate

    if min_score is None and min_level is None and dedup_window <= 0:
        return None, None

    policy = NotificationPolicy(
        min_score=float(min_score) if min_score is not None else None,
        min_level=min_level,
        dedup_window_seconds=int(dedup_window),
    )
    store: Optional[DedupStore] = (
        InMemoryDedupStore() if dedup_window > 0 else None
    )
    return policy, store


@dataclass(frozen=True)
class ResultPipelineOutcome:
    saved: bool
    notified: bool
    save_count_increment: int
    skip_reason: Optional[str] = None
    decision: Optional[NotificationDecision] = None


class ResultPipelineService:
    """处理分析结果的落盘和推荐通知。"""

    def __init__(
        self,
        *,
        saver: Saver,
        notifier: Notifier,
        policy: Optional[NotificationPolicy] = None,
        dedup_store: Optional[DedupStore] = None,
    ) -> None:
        self._saver = saver
        self._notifier = notifier
        self._policy = policy
        self._dedup_store = dedup_store

    @classmethod
    def from_settings(
        cls,
        *,
        saver: Saver,
        notifier: Notifier,
        notification_settings=None,
    ) -> "ResultPipelineService":
        """从 NotificationSettings 自动构造带降噪 seam 的 pipeline。

        没有任何阈值/去重配置时, 返回的实例与不带 policy 的实例语义一致 ——
        旧调用方完全不感知此 seam 的存在。
        """
        if notification_settings is None:
            try:
                from src.services.notification_config_service import (
                    load_notification_settings,
                )
                notification_settings = load_notification_settings()
            except Exception:
                notification_settings = None
        policy, store = _policy_from_env(notification_settings)
        return cls(saver=saver, notifier=notifier, policy=policy, dedup_store=store)

    async def persist_and_notify(
        self,
        record: dict,
        keyword: str,
        notification_targets: Optional[list[dict]] = None,
    ) -> ResultPipelineOutcome:
        saved = await self._saver(record, keyword)
        notified, skip_reason, decision = await self._notify_if_recommended(
            record, notification_targets
        )
        return ResultPipelineOutcome(
            saved=saved,
            notified=notified,
            save_count_increment=1 if saved else 0,
            skip_reason=skip_reason,
            decision=decision,
        )

    async def _notify_if_recommended(
        self,
        record: dict,
        notification_targets: Optional[list[dict]],
    ) -> tuple[bool, Optional[str], Optional[NotificationDecision]]:
        analysis_result = record.get("ai_analysis", {}) or {}
        if not analysis_result.get("is_recommended"):
            return False, None, None

        decision: Optional[NotificationDecision] = None
        if self._policy is not None and not self._policy.is_inert():
            decision = evaluate_notification(
                record,
                policy=self._policy,
                dedup_store=self._dedup_store,
            )
            if not decision.should_notify:
                # 显式打印一行降噪日志, 便于运维确认 seam 在工作。
                print(
                    f"   [通知] 已被降噪策略过滤: {decision.skip_reason} "
                    f"(score={decision.score:.1f}, level={decision.level}, "
                    f"key={decision.dedup_key})"
                )
                return False, decision.skip_reason, decision
        elif self._policy is not None and self._dedup_store is not None:
            # inert 策略下也允许写入 dedup 时间, 让评估期切换不丢数据。
            decision = evaluate_notification(
                record,
                policy=self._policy,
                dedup_store=self._dedup_store,
            )

        try:
            # Enrich item_data with seller_type context from ai_analysis
            # (underscore-prefixed keys to avoid collision with real fields)
            item_data = dict(record.get("商品信息", {}) or {})
            criteria = (analysis_result.get("criteria_analysis", {}) or {})
            seller_type = criteria.get("seller_type", {}) or {}
            if seller_type:
                item_data["_seller_type_persona"] = str(
                    seller_type.get("persona", "")
                )
                item_data["_seller_type_status"] = str(
                    seller_type.get("status", "")
                )
                item_data["_seller_type_comment"] = str(
                    seller_type.get("comment", "")
                )
            await self._notifier(
                item_data,
                analysis_result.get("reason", "无"),
                notification_targets,
            )
        except Exception as exc:
            print(f"   [通知] 发送推荐通知失败: {exc}")
            return False, f"send failed: {exc}", decision
        return True, None, decision
