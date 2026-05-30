"""
结果持久化与推荐通知分发。
"""
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional


Notifier = Callable[[dict, str, Optional[list[dict]]], Awaitable[None]]
Saver = Callable[[dict, str], Awaitable[bool]]


@dataclass(frozen=True)
class ResultPipelineOutcome:
    saved: bool
    notified: bool
    save_count_increment: int


class ResultPipelineService:
    """处理分析结果的落盘和推荐通知。"""

    def __init__(self, *, saver: Saver, notifier: Notifier) -> None:
        self._saver = saver
        self._notifier = notifier

    async def persist_and_notify(
        self,
        record: dict,
        keyword: str,
        notification_targets: Optional[list[dict]] = None,
    ) -> ResultPipelineOutcome:
        saved = await self._saver(record, keyword)
        notified = await self._notify_if_recommended(record, notification_targets)
        return ResultPipelineOutcome(
            saved=saved,
            notified=notified,
            save_count_increment=1 if saved else 0,
        )

    async def _notify_if_recommended(
        self,
        record: dict,
        notification_targets: Optional[list[dict]],
    ) -> bool:
        analysis_result = record.get("ai_analysis", {}) or {}
        if not analysis_result.get("is_recommended"):
            return False
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
            return False
        return True
