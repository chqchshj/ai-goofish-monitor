"""
卖家维度聚合服务。

从已筛选的结果记录中按卖家昵称聚合，返回商品数、价格范围、
最近发现时间、个人卖家画像摘要等统计信息。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.services.price_history_service import parse_price_value


# 未知卖家的占位符
UNKNOWN_SELLER_KEY = "__unknown__"
UNKNOWN_SELLER_DISPLAY = "未知卖家"


@dataclass
class SellerSummary:
    """单个卖家的聚合摘要。"""

    seller_nickname: str
    item_count: int = 0
    min_price: float | None = None
    max_price: float | None = None
    latest_crawl_time: str = ""
    recommended_count: int = 0
    personal_seller_personas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为 API 响应格式。"""
        # 去重并取前 3 个画像摘要
        unique_personas = []
        seen = set()
        for p in self.personal_seller_personas:
            if p and p not in seen:
                seen.add(p)
                unique_personas.append(p)
                if len(unique_personas) >= 3:
                    break

        return {
            "seller_nickname": self.seller_nickname,
            "item_count": self.item_count,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "latest_crawl_time": self.latest_crawl_time,
            "recommended_count": self.recommended_count,
            "personal_seller_summary": ", ".join(unique_personas) if unique_personas else None,
        }


def _extract_seller_nickname(record: dict) -> str:
    """从记录中提取卖家昵称，优先使用卖家信息字段。"""
    seller_info = record.get("卖家信息", {}) or {}
    nickname = seller_info.get("卖家昵称")
    if nickname:
        return str(nickname).strip()

    item_info = record.get("商品信息", {}) or {}
    nickname = item_info.get("卖家昵称")
    if nickname:
        return str(nickname).strip()

    return ""


def _extract_price(record: dict) -> float | None:
    """从记录中提取价格数值。"""
    item_info = record.get("商品信息", {}) or {}
    price_display = item_info.get("当前售价")
    if price_display:
        return parse_price_value(price_display)
    return None


def _extract_crawl_time(record: dict) -> str:
    """从记录中提取爬取时间。"""
    return str(record.get("爬取时间", "") or "")


def _extract_is_recommended(record: dict) -> bool:
    """从记录中提取是否推荐。"""
    analysis = record.get("ai_analysis", {}) or {}
    return bool(analysis.get("is_recommended"))


def _extract_seller_persona(record: dict) -> str | None:
    """
    从 AI 分析中提取卖家画像摘要。

    优先使用 criteria_analysis.seller_type 中的 persona 字段，
    其次使用 status 或 comment。
    """
    analysis = record.get("ai_analysis", {}) or {}
    if analysis.get("analysis_source") != "ai":
        return None

    criteria = analysis.get("criteria_analysis", {}) or {}
    seller_type = criteria.get("seller_type")
    if not isinstance(seller_type, dict):
        return None

    # 优先取 persona
    persona = seller_type.get("persona")
    if persona and isinstance(persona, str):
        return persona.strip()

    # 其次取 status
    status = seller_type.get("status")
    if status and isinstance(status, str):
        return status.strip()

    # 最后尝试从 analysis_details 中提取
    details = seller_type.get("analysis_details", {})
    if isinstance(details, dict):
        for key in ("story", "persona", "type"):
            nested = details.get(key, {})
            if isinstance(nested, dict):
                comment = nested.get("comment")
                if comment and isinstance(comment, str):
                    # 截取前 20 个字符作为摘要
                    return comment[:20].strip()

    return None


def aggregate_sellers(records: list[dict]) -> list[dict[str, Any]]:
    """
    按卖家昵称聚合记录列表。

    Args:
        records: 已筛选的结果记录列表

    Returns:
        按商品数量降序排列的卖家聚合摘要列表
    """
    aggregation: dict[str, SellerSummary] = {}

    for record in records:
        nickname = _extract_seller_nickname(record)
        key = nickname if nickname else UNKNOWN_SELLER_KEY
        display_name = nickname if nickname else UNKNOWN_SELLER_DISPLAY

        if key not in aggregation:
            aggregation[key] = SellerSummary(seller_nickname=display_name)

        summary = aggregation[key]
        summary.item_count += 1

        # 更新价格范围
        price = _extract_price(record)
        if price is not None:
            if summary.min_price is None or price < summary.min_price:
                summary.min_price = price
            if summary.max_price is None or price > summary.max_price:
                summary.max_price = price

        # 更新最近发现时间
        crawl_time = _extract_crawl_time(record)
        if crawl_time and crawl_time > summary.latest_crawl_time:
            summary.latest_crawl_time = crawl_time

        # 更新推荐计数
        if _extract_is_recommended(record):
            summary.recommended_count += 1

        # 收集卖家画像
        persona = _extract_seller_persona(record)
        if persona:
            summary.personal_seller_personas.append(persona)

    # 按商品数量降序排列
    sorted_summaries = sorted(
        aggregation.values(),
        key=lambda s: (s.item_count, s.latest_crawl_time),
        reverse=True,
    )

    return [s.to_dict() for s in sorted_summaries]
