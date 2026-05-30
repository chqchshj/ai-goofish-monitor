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
            await self._notifier(
                record.get("商品信息", {}) or {},
                analysis_result.get("reason", "无"),
                notification_targets,
            )
        except Exception as exc:
            print(f"   [通知] 发送推荐通知失败: {exc}")
            return False
        return True
