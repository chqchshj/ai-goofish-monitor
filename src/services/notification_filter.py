"""
通知降噪策略 (P4-1 seam)

提供两个相互独立但可组合使用的降噪能力:

1. 推荐评分 / 等级阈值
   - 基于 AI 输出的 ``criteria_analysis.<field>.status`` 与 ``risk_tags``
     推导一个 0..100 的归一化推荐分和 low/medium/high 等级。
   - 通过 ``NotificationPolicy.min_score`` / ``min_level`` 设定最低阈值, 低于
     阈值的推荐 *只保存不通知*。

2. 短窗口去重
   - 通过 ``DedupStore`` 协议 (默认 ``InMemoryDedupStore``) 在指定时间窗口内
     按 ``item_id`` / 规范化 URL 抑制重复通知。

设计目标:
- 纯函数 + 协议接口, 易于单元测试 (clock 可注入)。
- 默认行为完全向后兼容: 没有提供 policy 或所有阈值为空时, 决策与现状一致。
- 不写生产 DB 或文件: 默认存储是进程内 ``OrderedDict``。
- 未来 AI 输出原生 ``recommendation_score`` 字段时, 只需替换 ``score_from_record``
  的实现 (通过 ``NotificationPolicy.scorer`` 注入), 无需改动 seam 调用方。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol
from urllib.parse import urlparse, urlunparse

# ---------------------------------------------------------------------------
# 卖家限流
# ---------------------------------------------------------------------------

_SELLER_THROTTLE_KEY_PREFIX = "seller:"


def seller_throttle_key_for(record: dict) -> Optional[str]:
    """从 record 推导 seller throttle key。

    优先级: sellerId -> 卖家昵称 -> 卖家主页。
    任一字段有效 (非空字符串) 即返回 ``seller:<value>``。
    全部缺失返回 None, 表示不启用 seller throttle。

    数据来源: record 根层级 ``seller_id``, 或 ``卖家信息`` 子字段。
    与 ``dedup_key_for`` 完全独立 —— item dedup 不受 seller throttle 影响。
    """
    if not isinstance(record, dict):
        return None

    seller_id = record.get("seller_id")
    if seller_id is not None and str(seller_id).strip():
        return f"{_SELLER_THROTTLE_KEY_PREFIX}{str(seller_id).strip()}"

    info = record.get("卖家信息") if isinstance(record, dict) else None
    if isinstance(info, dict):
        sid = info.get("卖家ID")
        if sid is not None and str(sid).strip():
            return f"{_SELLER_THROTTLE_KEY_PREFIX}{str(sid).strip()}"

        nickname = info.get("卖家昵称")
        if isinstance(nickname, str) and nickname.strip():
            return f"{_SELLER_THROTTLE_KEY_PREFIX}{nickname.strip()}"

        homepage = info.get("卖家主页") or info.get("主页")
        if isinstance(homepage, str) and homepage.strip():
            return f"{_SELLER_THROTTLE_KEY_PREFIX}{homepage.strip()}"

    return None

# ---------------------------------------------------------------------------
# 评分 / 等级
# ---------------------------------------------------------------------------

# 推荐等级
LEVEL_LOW = "low"
LEVEL_MEDIUM = "medium"
LEVEL_HIGH = "high"
_LEVEL_RANK = {LEVEL_LOW: 0, LEVEL_MEDIUM: 1, LEVEL_HIGH: 2}

# criteria_analysis 中各字段 status 的归一化打分。
# 与 prompts/base_prompt.txt 中 EagleEye-V6.4 的输出契约对齐:
# 常见 status 值有 PASS / WARN / FAIL / UNKNOWN, 大小写不敏感。
_STATUS_WEIGHT = {
    "pass": 1.0,
    "ok": 1.0,
    "good": 1.0,
    "warn": 0.5,
    "warning": 0.5,
    "neutral": 0.5,
    "unknown": 0.4,
    "n/a": 0.4,
    "fail": 0.0,
    "bad": 0.0,
}

# 命中风险标签每条扣多少分(0..100 量纲)。
_RISK_TAG_PENALTY = 8


def _normalize_status(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def derive_recommendation_score(record: dict) -> float:
    """从 record 中推导 0..100 的推荐分。

    评分启发式 (P4-1 阶段, 等待 AI 原生字段时的 fallback):
    - ``ai_analysis.is_recommended`` 为 False 时直接 0 分。
    - 否则取 ``criteria_analysis`` 中所有子项 ``status`` 的平均归一权重 *100,
      再按 ``risk_tags`` 数量线性扣分。
    - 没有任何可用信号时返回 100 分 (即不在评分维度上过滤),
      把"过滤与否"完全交给阈值是否设置。
    """
    analysis = record.get("ai_analysis") if isinstance(record, dict) else None
    if not isinstance(analysis, dict):
        return 100.0
    if analysis.get("is_recommended") is False:
        return 0.0

    criteria = analysis.get("criteria_analysis")
    weights: list[float] = []
    if isinstance(criteria, dict):
        for value in criteria.values():
            if not isinstance(value, dict):
                continue
            status = _normalize_status(value.get("status"))
            if not status:
                continue
            if status in _STATUS_WEIGHT:
                weights.append(_STATUS_WEIGHT[status])

    if weights:
        base = (sum(weights) / len(weights)) * 100.0
    else:
        base = 100.0

    risk_tags = analysis.get("risk_tags")
    if isinstance(risk_tags, list):
        base -= _RISK_TAG_PENALTY * len(risk_tags)

    if base < 0.0:
        return 0.0
    if base > 100.0:
        return 100.0
    return base


def derive_recommendation_level(score: float) -> str:
    """0..100 推荐分映射到 low / medium / high。

    边界设计偏保守 (favor 高质量): 80+ 高, 50..79 中, <50 低。
    """
    if score >= 80.0:
        return LEVEL_HIGH
    if score >= 50.0:
        return LEVEL_MEDIUM
    return LEVEL_LOW


def _level_at_least(actual: str, minimum: str) -> bool:
    actual_rank = _LEVEL_RANK.get(actual, 0)
    minimum_rank = _LEVEL_RANK.get(minimum, 0)
    return actual_rank >= minimum_rank


# ---------------------------------------------------------------------------
# 去重 key
# ---------------------------------------------------------------------------


def _normalize_url(url: object) -> str:
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return url.strip()
    # 丢弃 query / fragment / 端口的常见噪音, 保留 scheme+host+path
    cleaned = parsed._replace(query="", fragment="", params="")
    return urlunparse(cleaned).rstrip("/")


def dedup_key_for(record: dict) -> Optional[str]:
    """从 record 推导去重 key。

    优先级: 商品ID -> 规范化商品链接。两者都缺失返回 None (不去重)。
    """
    if not isinstance(record, dict):
        return None
    raw_info = record.get("商品信息")
    info: dict = raw_info if isinstance(raw_info, dict) else {}
    item_id = info.get("商品ID") or record.get("item_id")
    if isinstance(item_id, (str, int)) and str(item_id).strip() and str(item_id).strip().upper() != "N/A":
        return f"item:{str(item_id).strip()}"
    link = info.get("商品链接") or record.get("url")
    normalized = _normalize_url(link)
    if normalized:
        return f"url:{normalized}"
    return None


# ---------------------------------------------------------------------------
# 去重存储
# ---------------------------------------------------------------------------


class DedupStore(Protocol):
    """通知去重的最小存储协议。

    实现需保证以下语义:
    - ``seen_within(key, window_seconds, now)``: 若 key 在 [now-window, now]
      内出现过返回 True, 否则返回 False。
    - ``mark(key, now)``: 记录 key 最近一次发送时间为 now。

    实现可自由选择: 内存 OrderedDict / Redis / SQLite WAL 等。P4-1 仅提供
    内存实现以保证"非生产写入、可回滚、可测试"。
    """

    def seen_within(self, key: str, window_seconds: int, now: float) -> bool: ...

    def mark(self, key: str, now: float) -> None: ...


class InMemoryDedupStore:
    """进程内 TTL 去重。

    - 容量上限 ``max_entries`` 默认 4096; 超过时按写入顺序淘汰最旧条目。
    - 不持久化, 进程重启即清空 (符合 P4-1 "不写生产 DB" 边界)。
    """

    def __init__(self, max_entries: int = 4096) -> None:
        self._max_entries = max(1, int(max_entries))
        # 简单字典 + 插入顺序; 不引入 OrderedDict 也能利用 dict 的有序性。
        self._records: dict[str, float] = {}

    def seen_within(self, key: str, window_seconds: int, now: float) -> bool:
        if window_seconds <= 0 or not key:
            return False
        last = self._records.get(key)
        if last is None:
            return False
        if (now - last) <= window_seconds:
            return True
        # 过窗即视为未见过, 顺手清理。
        self._records.pop(key, None)
        return False

    def mark(self, key: str, now: float) -> None:
        if not key:
            return
        # 更新 = 删后再插, 维持插入顺序代表 LRU 末位。
        if key in self._records:
            self._records.pop(key)
        self._records[key] = now
        while len(self._records) > self._max_entries:
            oldest_key = next(iter(self._records))
            self._records.pop(oldest_key, None)


# ---------------------------------------------------------------------------
# 策略 + 决策
# ---------------------------------------------------------------------------


Scorer = Callable[[dict], float]


@dataclass(frozen=True)
class NotificationPolicy:
    """通知降噪策略。

    所有字段都可选; 全部为空 / 0 时, ``evaluate_notification`` 等价于直接放行
    (与升级前完全一致), 这是默认兼容性的依据。
    """

    min_score: Optional[float] = None
    min_level: Optional[str] = None
    dedup_window_seconds: int = 0
    seller_throttle_window_seconds: int = 0
    scorer: Optional[Scorer] = field(default=None, repr=False)

    def is_inert(self) -> bool:
        """没有任何过滤/去重作用时返回 True。"""
        return (
            self.min_score is None
            and self.min_level is None
            and self.dedup_window_seconds <= 0
            and self.seller_throttle_window_seconds <= 0
        )

    def score(self, record: dict) -> float:
        scorer = self.scorer or derive_recommendation_score
        return scorer(record)


@dataclass(frozen=True)
class NotificationDecision:
    """通知决策结果。

    属性:
        should_notify: 是否应发送通知。
        score: 推导出的推荐分 (0..100)。
        level: low/medium/high。
        skip_reason: should_notify=False 时的可读跳过原因; 否则为 None。
        dedup_key: 用于幂等的 key, 可能为 None。
        seller_throttle_key: seller throttle key, 可能为 None。
    """

    should_notify: bool
    score: float
    level: str
    skip_reason: Optional[str] = None
    dedup_key: Optional[str] = None
    seller_throttle_key: Optional[str] = None


def evaluate_notification(
    record: dict,
    policy: Optional[NotificationPolicy] = None,
    dedup_store: Optional[DedupStore] = None,
    seller_throttle_store: Optional[DedupStore] = None,
    now: Optional[float] = None,
) -> NotificationDecision:
    """对一条 result record 做通知降噪决策。

    调用方契约 (与 ResultPipelineService 当前行为对齐):
    - 调用方在调用本函数*之前*已经判定 ``ai_analysis.is_recommended`` 为真。
    - 因此返回 ``should_notify=False`` 表示"曾经被推荐, 但被降噪策略过滤"。

    side-effect: 若返回 ``should_notify=True`` 且 dedup_store 与 dedup_key 同时
    存在, 会调用 ``dedup_store.mark`` 记录本次发送, 后续同 key 命中窗口将被
    抑制。同理, seller_throttle_store 会记录 seller throttle key。
    """
    if policy is None:
        policy = NotificationPolicy()
    if now is None:
        # 延迟导入避免顶层依赖 time 在某些精简环境中报错。
        import time

        now = time.monotonic()

    score = policy.score(record)
    level = derive_recommendation_level(score)
    dedup_key = dedup_key_for(record)
    seller_key = seller_throttle_key_for(record)

    if policy.is_inert():
        if dedup_store is not None and dedup_key:
            # inert 策略下不主动做窗口拦截, 但仍记录最近发送时间, 方便外层
            # 在切换策略时不出现"刚启用就把所有历史 key 全发一遍"的尴尬。
            dedup_store.mark(dedup_key, now)
        if seller_throttle_store is not None and seller_key:
            seller_throttle_store.mark(seller_key, now)
        return NotificationDecision(
            should_notify=True,
            score=score,
            level=level,
            skip_reason=None,
            dedup_key=dedup_key,
            seller_throttle_key=seller_key,
        )

    if policy.min_score is not None and score < policy.min_score:
        return NotificationDecision(
            should_notify=False,
            score=score,
            level=level,
            skip_reason=f"score {score:.1f} 低于阈值 {policy.min_score:.1f}",
            dedup_key=dedup_key,
            seller_throttle_key=seller_key,
        )

    if policy.min_level is not None and not _level_at_least(level, policy.min_level):
        return NotificationDecision(
            should_notify=False,
            score=score,
            level=level,
            skip_reason=f"等级 {level} 低于 {policy.min_level}",
            dedup_key=dedup_key,
            seller_throttle_key=seller_key,
        )

    if (
        dedup_store is not None
        and dedup_key
        and policy.dedup_window_seconds > 0
        and dedup_store.seen_within(dedup_key, policy.dedup_window_seconds, now)
    ):
        return NotificationDecision(
            should_notify=False,
            score=score,
            level=level,
            skip_reason=(
                f"{policy.dedup_window_seconds}s 窗口内已通知过 {dedup_key}"
            ),
            dedup_key=dedup_key,
            seller_throttle_key=seller_key,
        )

    if (
        seller_throttle_store is not None
        and seller_key
        and policy.seller_throttle_window_seconds > 0
        and seller_throttle_store.seen_within(
            seller_key, policy.seller_throttle_window_seconds, now
        )
    ):
        return NotificationDecision(
            should_notify=False,
            score=score,
            level=level,
            skip_reason=(
                f"卖家 {seller_key} 在 {policy.seller_throttle_window_seconds}s "
                f"窗口内已通知过"
            ),
            dedup_key=dedup_key,
            seller_throttle_key=seller_key,
        )

    if dedup_store is not None and dedup_key and policy.dedup_window_seconds > 0:
        dedup_store.mark(dedup_key, now)
    if seller_throttle_store is not None and seller_key and policy.seller_throttle_window_seconds > 0:
        seller_throttle_store.mark(seller_key, now)

    return NotificationDecision(
        should_notify=True,
        score=score,
        level=level,
        skip_reason=None,
        dedup_key=dedup_key,
        seller_throttle_key=seller_key,
    )


__all__ = [
    "DedupStore",
    "InMemoryDedupStore",
    "LEVEL_HIGH",
    "LEVEL_LOW",
    "LEVEL_MEDIUM",
    "NotificationDecision",
    "NotificationPolicy",
    "Scorer",
    "dedup_key_for",
    "derive_recommendation_level",
    "derive_recommendation_score",
    "evaluate_notification",
    "seller_throttle_key_for",
]
