"""
卖家跟进工作台领域模型。

定义卖家跟进状态、备注、收藏等数据契约。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SellerStatus(str, Enum):
    """卖家跟进状态。"""

    NORMAL = "normal"  # 正常/未标记
    FAVORITE = "favorite"  # 收藏/关注
    IGNORED = "ignored"  # 忽略（不再提醒）
    BLACKLISTED = "blacklisted"  # 拉黑（隐藏该卖家商品）


@dataclass
class SellerTracking:
    """
    卖家跟进记录。

    用于持久化用户对特定卖家的跟进状态、备注等信息。
    seller_key 使用卖家昵称作为唯一标识（与现有 result_items.seller_nickname 一致）。
    """

    seller_key: str  # 卖家唯一标识（昵称）
    status: SellerStatus = SellerStatus.NORMAL
    notes: str = ""  # 用户备注
    tags: list[str] = field(default_factory=list)  # 自定义标签
    created_at: str = ""  # ISO 格式时间戳
    updated_at: str = ""  # ISO 格式时间戳

    def to_dict(self) -> dict[str, Any]:
        """转换为 API 响应格式。"""
        return {
            "seller_key": self.seller_key,
            "status": self.status.value,
            "notes": self.notes,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SellerTracking:
        """从字典创建实例。"""
        return cls(
            seller_key=data.get("seller_key", ""),
            status=SellerStatus(data.get("status", "normal")),
            notes=data.get("notes", ""),
            tags=data.get("tags") or [],
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class SellerDetail:
    """
    卖家详情聚合视图。

    组合卖家跟进状态与商品聚合统计，用于工作台展示。
    """

    # 基础信息
    seller_key: str
    seller_nickname: str

    # 跟进状态
    status: SellerStatus = SellerStatus.NORMAL
    notes: str = ""
    tags: list[str] = field(default_factory=list)

    # 聚合统计（来自 result_items）
    item_count: int = 0
    recommended_count: int = 0
    min_price: float | None = None
    max_price: float | None = None
    latest_crawl_time: str = ""
    first_seen_time: str = ""
    personal_seller_summary: str | None = None

    # 时间戳
    tracking_created_at: str = ""
    tracking_updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为 API 响应格式。"""
        return {
            "seller_key": self.seller_key,
            "seller_nickname": self.seller_nickname,
            "status": self.status.value,
            "notes": self.notes,
            "tags": self.tags,
            "item_count": self.item_count,
            "recommended_count": self.recommended_count,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "latest_crawl_time": self.latest_crawl_time,
            "first_seen_time": self.first_seen_time,
            "personal_seller_summary": self.personal_seller_summary,
            "tracking_created_at": self.tracking_created_at,
            "tracking_updated_at": self.tracking_updated_at,
        }
