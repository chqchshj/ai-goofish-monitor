"""
购买动作策略纯函数。

evaluate_purchase_action 是核心决策函数，只返回 allow/skip 决策，不执行任何动作。
设计参考: P4-1 通知降噪 seam (evaluate_notification)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from src.domain.models.purchase_action import (
    ActionType,
    ItemContext,
    PolicyConfig,
    PolicyDecision,
    PurchaseActionMode,
    SkipReason,
)

if TYPE_CHECKING:
    import sqlite3


def load_policy_config_from_env() -> PolicyConfig:
    """从环境变量加载策略配置。"""
    return PolicyConfig(
        global_enabled=os.getenv("PURCHASE_ACTION_GLOBAL_ENABLED", "false").lower() == "true",
        mode=PurchaseActionMode(
            os.getenv("PURCHASE_ACTION_MODE", PurchaseActionMode.NOTIFY_ONLY.value)
        ),
        max_price=_parse_float(os.getenv("PURCHASE_ACTION_MAX_PRICE")),
        daily_budget=_parse_float(os.getenv("PURCHASE_ACTION_DAILY_BUDGET")),
        cooldown_seconds=int(os.getenv("PURCHASE_ACTION_COOLDOWN_SECONDS", "300")),
        require_seller_allowlist=os.getenv(
            "PURCHASE_ACTION_REQUIRE_SELLER_ALLOWLIST", "true"
        ).lower() == "true",
        allow_auto_click=os.getenv("PURCHASE_ACTION_ALLOW_AUTO_CLICK", "false").lower() == "true",
    )


def _parse_float(value: str | None) -> float | None:
    """解析浮点数，None 或空字符串返回 None。"""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def evaluate_purchase_action(
    item: ItemContext,
    config: PolicyConfig,
    *,
    seller_allowlist: set[str] | None = None,
    daily_spend: float = 0.0,
    last_candidate_time: datetime | None = None,
) -> PolicyDecision:
    """
    评估是否应为商品生成购买动作候选。

    这是一个纯函数，不访问数据库或执行任何副作用。
    所有外部状态（日消费、冷却时间、白名单）由调用方传入。

    Args:
        item: 商品上下文
        config: 策略配置
        seller_allowlist: 卖家白名单（seller_id 集合）
        daily_spend: 当日已消费金额
        last_candidate_time: 该商品上次生成候选的时间

    Returns:
        PolicyDecision: 决策结果
    """
    # 1. 全局开关检查
    if not config.global_enabled:
        return PolicyDecision(
            allow=False,
            reason="购买动作全局开关已关闭",
            skip_reason=SkipReason.GLOBAL_DISABLED,
        )

    # 2. 模式检查
    if config.mode == PurchaseActionMode.NOTIFY_ONLY:
        return PolicyDecision(
            allow=False,
            reason="当前模式为仅通知，不生成购买候选",
            skip_reason=SkipReason.MODE_NOTIFY_ONLY,
        )

    # 3. AI 推荐检查
    if not item.is_recommended:
        return PolicyDecision(
            allow=False,
            reason="AI 未推荐该商品",
            skip_reason=SkipReason.NOT_RECOMMENDED,
        )

    # 4. 商品状态检查
    if item.is_sold_out:
        return PolicyDecision(
            allow=False,
            reason="商品已售出",
            skip_reason=SkipReason.ITEM_SOLD_OUT,
        )

    # 5. 价格上限检查（安全硬规则：未设价格上限不得进入 manual_confirm 以上）
    if config.max_price is None:
        return PolicyDecision(
            allow=False,
            reason="未设置价格上限，安全规则禁止生成候选",
            skip_reason=SkipReason.PRICE_EXCEEDS_LIMIT,
        )
    if item.price > config.max_price:
        return PolicyDecision(
            allow=False,
            reason=f"商品价格 {item.price} 超过上限 {config.max_price}",
            skip_reason=SkipReason.PRICE_EXCEEDS_LIMIT,
        )

    # 6. 日预算检查
    if config.daily_budget is not None:
        if daily_spend + item.price > config.daily_budget:
            return PolicyDecision(
                allow=False,
                reason=f"日预算已耗尽（已消费 {daily_spend}，预算 {config.daily_budget}）",
                skip_reason=SkipReason.DAILY_BUDGET_EXHAUSTED,
            )

    # 7. 冷却期检查
    if last_candidate_time is not None:
        cooldown_end = last_candidate_time + timedelta(seconds=config.cooldown_seconds)
        now = datetime.now(timezone.utc)
        if now < cooldown_end:
            remaining = (cooldown_end - now).total_seconds()
            return PolicyDecision(
                allow=False,
                reason=f"商品在冷却期内，剩余 {int(remaining)} 秒",
                skip_reason=SkipReason.COOLDOWN_ACTIVE,
            )

    # 8. 卖家白名单检查
    if config.require_seller_allowlist:
        if seller_allowlist is None or not seller_allowlist:
            return PolicyDecision(
                allow=False,
                reason="要求卖家白名单但白名单为空",
                skip_reason=SkipReason.SELLER_NOT_IN_ALLOWLIST,
            )
        if item.seller_id and item.seller_id not in seller_allowlist:
            return PolicyDecision(
                allow=False,
                reason=f"卖家 {item.seller_id} 不在白名单中",
                skip_reason=SkipReason.SELLER_NOT_IN_ALLOWLIST,
            )

    # 所有检查通过，允许生成候选
    suggested_action = _suggest_action_type(config.mode)
    return PolicyDecision(
        allow=True,
        reason=f"通过所有检查，建议动作: {suggested_action.value}",
        suggested_action=suggested_action,
    )


def _suggest_action_type(mode: PurchaseActionMode) -> ActionType:
    """根据模式建议动作类型。"""
    if mode == PurchaseActionMode.MANUAL_CONFIRM:
        return ActionType.OPEN_ITEM_PAGE
    elif mode == PurchaseActionMode.DRAFT_ORDER_DRY_RUN:
        return ActionType.DRY_RUN_ORDER
    # AUTO_CLICK 模式 M11 不实现，fallback 到 OPEN_ITEM_PAGE
    return ActionType.OPEN_ITEM_PAGE


def evaluate_with_db_context(
    item: ItemContext,
    config: PolicyConfig,
    conn: "sqlite3.Connection",
    *,
    seller_allowlist: set[str] | None = None,
) -> PolicyDecision:
    """
    带数据库上下文的评估函数。

    自动从数据库获取日消费和冷却时间，然后调用纯函数 evaluate_purchase_action。
    这是一个便捷包装，用于实际业务场景。

    Args:
        item: 商品上下文
        config: 策略配置
        conn: 数据库连接
        seller_allowlist: 卖家白名单

    Returns:
        PolicyDecision: 决策结果
    """
    from src.domain.repositories import purchase_action_repository as repo

    # 获取当日消费
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_spend = repo.get_daily_spend(conn, today)

    # 获取该商品上次候选时间
    last_candidate_time = None
    if config.cooldown_seconds > 0:
        since = (
            datetime.now(timezone.utc) - timedelta(seconds=config.cooldown_seconds)
        ).isoformat()
        last_candidate = repo.get_candidate_by_item_id(conn, item.item_id, since=since)
        if last_candidate:
            last_candidate_time = datetime.fromisoformat(
                last_candidate.created_at.replace("Z", "+00:00")
            )

    return evaluate_purchase_action(
        item,
        config,
        seller_allowlist=seller_allowlist,
        daily_spend=daily_spend,
        last_candidate_time=last_candidate_time,
    )
