"""
购买动作候选领域模型。

定义购买动作模式、候选状态、候选记录和审计日志的数据契约。
设计文档: docs/notes/m11-2-safe-purchase-action-design.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PurchaseActionMode(str, Enum):
    """购买动作模式（四级能力）。"""

    NOTIFY_ONLY = "notify_only"  # 默认：只通知，不做任何购买动作
    MANUAL_CONFIRM = "manual_confirm"  # 生成候选，用户确认后执行安全动作
    DRAFT_ORDER_DRY_RUN = "draft_order_dry_run"  # 模拟购买路径，不提交订单
    AUTO_CLICK = "auto_click"  # 自动点击下单（M11 不实现）


class CandidateStatus(str, Enum):
    """候选记录状态。"""

    PENDING = "pending"  # 待处理
    CONFIRMED = "confirmed"  # 用户已确认执行
    CANCELLED = "cancelled"  # 用户取消
    EXPIRED = "expired"  # 超时过期
    EXECUTED = "executed"  # 已执行（打开页面/复制链接等）


class ActionType(str, Enum):
    """动作类型。"""

    OPEN_ITEM_PAGE = "open_item_page"  # 打开商品页面
    COPY_LINK = "copy_link"  # 复制链接
    DRY_RUN_ORDER = "dry_run_order"  # 模拟下单（不提交）
    # AUTO_SUBMIT_ORDER = "auto_submit_order"  # M11 不实现


class SkipReason(str, Enum):
    """跳过候选生成的原因。"""

    GLOBAL_DISABLED = "global_disabled"  # 全局开关关闭
    MODE_NOTIFY_ONLY = "mode_notify_only"  # 模式为 notify_only
    PRICE_EXCEEDS_LIMIT = "price_exceeds_limit"  # 价格超过上限
    DAILY_BUDGET_EXHAUSTED = "daily_budget_exhausted"  # 日预算耗尽
    COOLDOWN_ACTIVE = "cooldown_active"  # 冷却期内
    SELLER_NOT_IN_ALLOWLIST = "seller_not_in_allowlist"  # 卖家不在白名单
    NOT_RECOMMENDED = "not_recommended"  # AI 未推荐
    ITEM_SOLD_OUT = "item_sold_out"  # 商品已售出


@dataclass
class PolicyConfig:
    """购买动作策略配置（从环境变量加载）。"""

    global_enabled: bool = False
    mode: PurchaseActionMode = PurchaseActionMode.NOTIFY_ONLY
    max_price: float | None = None  # 单品价格上限（元）
    daily_budget: float | None = None  # 日预算上限（元）
    cooldown_seconds: int = 300  # 同一商品冷却时间
    require_seller_allowlist: bool = True  # 是否要求卖家在白名单
    allow_auto_click: bool = False  # 是否允许自动点击（M11 始终 False）

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "global_enabled": self.global_enabled,
            "mode": self.mode.value,
            "max_price": self.max_price,
            "daily_budget": self.daily_budget,
            "cooldown_seconds": self.cooldown_seconds,
            "require_seller_allowlist": self.require_seller_allowlist,
            "allow_auto_click": self.allow_auto_click,
        }


@dataclass
class PolicyDecision:
    """策略决策结果。"""

    allow: bool  # 是否允许生成候选
    reason: str  # 决策原因（人类可读）
    skip_reason: SkipReason | None = None  # 跳过原因枚举（如果 allow=False）
    suggested_action: ActionType | None = None  # 建议的动作类型

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "allow": self.allow,
            "reason": self.reason,
            "skip_reason": self.skip_reason.value if self.skip_reason else None,
            "suggested_action": self.suggested_action.value if self.suggested_action else None,
        }


@dataclass
class PurchaseActionCandidate:
    """购买动作候选记录。"""

    id: str  # UUID
    item_id: str  # 商品 ID
    task_id: int | None  # 关联的任务 ID
    status: CandidateStatus
    action_type: ActionType
    price: float  # 商品价格
    seller_id: str | None  # 卖家 ID
    seller_name: str | None  # 卖家名称
    item_title: str  # 商品标题
    item_url: str  # 商品链接
    ai_reason: str  # AI 推荐理由
    policy_reason: str  # 策略允许理由
    created_at: str  # ISO 格式时间戳
    updated_at: str  # ISO 格式时间戳
    expires_at: str | None = None  # 过期时间
    confirmed_at: str | None = None  # 确认时间
    executed_at: str | None = None  # 执行时间
    extra_data: dict[str, Any] = field(default_factory=dict)  # 扩展数据

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "id": self.id,
            "item_id": self.item_id,
            "task_id": self.task_id,
            "status": self.status.value,
            "action_type": self.action_type.value,
            "price": self.price,
            "seller_id": self.seller_id,
            "seller_name": self.seller_name,
            "item_title": self.item_title,
            "item_url": self.item_url,
            "ai_reason": self.ai_reason,
            "policy_reason": self.policy_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "confirmed_at": self.confirmed_at,
            "executed_at": self.executed_at,
            "extra_data": self.extra_data,
        }


@dataclass
class PurchaseActionAuditLog:
    """购买动作审计日志。"""

    id: str  # UUID
    candidate_id: str  # 关联的候选 ID
    action: str  # 动作名称（confirm, cancel, execute, expire）
    actor: str  # 执行者（user, system, scheduler）
    details: dict[str, Any]  # 详细信息
    created_at: str  # ISO 格式时间戳

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "action": self.action,
            "actor": self.actor,
            "details": self.details,
            "created_at": self.created_at,
        }


@dataclass
class ItemContext:
    """商品上下文（用于策略评估）。"""

    item_id: str
    price: float
    seller_id: str | None
    is_recommended: bool  # AI 是否推荐
    is_sold_out: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
