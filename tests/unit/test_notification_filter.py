"""单测: src.services.notification_filter — P4-1 通知降噪 seam."""
from __future__ import annotations

from src.services.notification_filter import (
    InMemoryDedupStore,
    LEVEL_HIGH,
    LEVEL_LOW,
    LEVEL_MEDIUM,
    NotificationPolicy,
    dedup_key_for,
    derive_recommendation_level,
    derive_recommendation_score,
    evaluate_notification,
)


# ---------------------------------------------------------------------------
# 评分 / 等级
# ---------------------------------------------------------------------------


def test_score_returns_zero_when_not_recommended():
    record = {"ai_analysis": {"is_recommended": False}}
    assert derive_recommendation_score(record) == 0.0


def test_score_returns_full_when_no_signal_and_recommended():
    record = {"ai_analysis": {"is_recommended": True}}
    assert derive_recommendation_score(record) == 100.0


def test_score_averages_status_weights_and_penalizes_risk_tags():
    record = {
        "ai_analysis": {
            "is_recommended": True,
            "criteria_analysis": {
                "model_chip": {"status": "PASS"},
                "battery_health": {"status": "PASS"},
                "condition": {"status": "WARN"},
                "history": {"status": "FAIL"},
            },
            "risk_tags": ["未提供电池健康度"],
        }
    }
    score = derive_recommendation_score(record)
    # 平均 (1 + 1 + 0.5 + 0) / 4 = 0.625 -> 62.5; 减 8 = 54.5
    assert 54.0 < score < 55.0


def test_score_clamped_to_zero_with_many_risk_tags():
    record = {
        "ai_analysis": {
            "is_recommended": True,
            "criteria_analysis": {"model_chip": {"status": "PASS"}},
            "risk_tags": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m"],
        }
    }
    assert derive_recommendation_score(record) == 0.0


def test_score_handles_unknown_status_gracefully():
    record = {
        "ai_analysis": {
            "is_recommended": True,
            "criteria_analysis": {
                "model_chip": {"status": "UNKNOWN"},
                "battery_health": {"status": "weird"},
                "condition": {"status": "PASS"},
            },
        }
    }
    score = derive_recommendation_score(record)
    # UNKNOWN=0.4, weird 不计入, PASS=1.0; 平均 (0.4+1.0)/2 = 0.7 -> 70
    assert score == 70.0


def test_level_mapping_boundaries():
    assert derive_recommendation_level(80.0) == LEVEL_HIGH
    assert derive_recommendation_level(79.99) == LEVEL_MEDIUM
    assert derive_recommendation_level(50.0) == LEVEL_MEDIUM
    assert derive_recommendation_level(49.99) == LEVEL_LOW
    assert derive_recommendation_level(0.0) == LEVEL_LOW


# ---------------------------------------------------------------------------
# 去重 key
# ---------------------------------------------------------------------------


def test_dedup_key_prefers_item_id():
    record = {"商品信息": {"商品ID": "12345", "商品链接": "https://www.goofish.com/item?id=12345&ref=xxx"}}
    assert dedup_key_for(record) == "item:12345"


def test_dedup_key_falls_back_to_normalized_url():
    record = {"商品信息": {"商品链接": "https://www.goofish.com/item.htm?id=999&utm=foo#frag"}}
    assert dedup_key_for(record) == "url:https://www.goofish.com/item.htm"


def test_dedup_key_returns_none_without_signal():
    assert dedup_key_for({}) is None
    assert dedup_key_for({"商品信息": {}}) is None
    assert dedup_key_for({"商品信息": {"商品ID": "N/A", "商品链接": ""}}) is None


def test_dedup_key_handles_non_dict_record():
    assert dedup_key_for(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# InMemoryDedupStore
# ---------------------------------------------------------------------------


def test_dedup_store_seen_within_window():
    store = InMemoryDedupStore()
    store.mark("k", now=1000.0)
    assert store.seen_within("k", window_seconds=60, now=1030.0) is True
    assert store.seen_within("k", window_seconds=60, now=1061.0) is False


def test_dedup_store_zero_window_never_dedups():
    store = InMemoryDedupStore()
    store.mark("k", now=1000.0)
    assert store.seen_within("k", window_seconds=0, now=1000.0) is False


def test_dedup_store_lru_eviction():
    store = InMemoryDedupStore(max_entries=2)
    store.mark("a", now=1.0)
    store.mark("b", now=2.0)
    store.mark("c", now=3.0)  # 应淘汰 a
    assert store.seen_within("a", window_seconds=999, now=4.0) is False
    assert store.seen_within("b", window_seconds=999, now=4.0) is True
    assert store.seen_within("c", window_seconds=999, now=4.0) is True


# ---------------------------------------------------------------------------
# evaluate_notification
# ---------------------------------------------------------------------------


def _good_record(item_id: str = "1") -> dict:
    return {
        "商品信息": {"商品ID": item_id},
        "ai_analysis": {
            "is_recommended": True,
            "criteria_analysis": {
                "model_chip": {"status": "PASS"},
                "battery_health": {"status": "PASS"},
            },
        },
    }


def test_evaluate_default_policy_always_passes():
    decision = evaluate_notification(_good_record(), policy=NotificationPolicy(), now=0.0)
    assert decision.should_notify is True
    assert decision.skip_reason is None
    assert decision.score == 100.0
    assert decision.level == LEVEL_HIGH


def test_evaluate_blocks_below_min_score():
    record = {
        "ai_analysis": {
            "is_recommended": True,
            "criteria_analysis": {"history": {"status": "FAIL"}},
        }
    }
    decision = evaluate_notification(
        record,
        policy=NotificationPolicy(min_score=50.0),
        now=0.0,
    )
    assert decision.should_notify is False
    assert decision.skip_reason is not None
    assert "阈值" in decision.skip_reason


def test_evaluate_blocks_below_min_level():
    record = {
        "ai_analysis": {
            "is_recommended": True,
            "criteria_analysis": {
                "model_chip": {"status": "WARN"},
                "battery_health": {"status": "WARN"},
            },
        }
    }
    # WARN/WARN -> 50 -> medium; min_level=high 应阻断
    decision = evaluate_notification(
        record,
        policy=NotificationPolicy(min_level=LEVEL_HIGH),
        now=0.0,
    )
    assert decision.should_notify is False
    assert decision.level == LEVEL_MEDIUM
    assert decision.skip_reason is not None and "等级" in decision.skip_reason


def test_evaluate_dedup_window_blocks_repeat_within_window():
    store = InMemoryDedupStore()
    policy = NotificationPolicy(dedup_window_seconds=600)

    first = evaluate_notification(_good_record("1"), policy=policy, dedup_store=store, now=0.0)
    assert first.should_notify is True

    second = evaluate_notification(_good_record("1"), policy=policy, dedup_store=store, now=300.0)
    assert second.should_notify is False
    assert second.skip_reason is not None and "窗口" in second.skip_reason

    third = evaluate_notification(_good_record("1"), policy=policy, dedup_store=store, now=601.0)
    assert third.should_notify is True


def test_evaluate_dedup_does_not_affect_distinct_keys():
    store = InMemoryDedupStore()
    policy = NotificationPolicy(dedup_window_seconds=600)
    a = evaluate_notification(_good_record("a"), policy=policy, dedup_store=store, now=0.0)
    b = evaluate_notification(_good_record("b"), policy=policy, dedup_store=store, now=10.0)
    assert a.should_notify is True
    assert b.should_notify is True


def test_evaluate_inert_policy_still_marks_dedup_store():
    """inert 策略 (无阈值/无窗口) 不能触发去重, 但要记录历史以便切换平滑。"""
    store = InMemoryDedupStore()
    policy = NotificationPolicy()  # inert
    decision = evaluate_notification(
        _good_record("x"),
        policy=policy,
        dedup_store=store,
        now=42.0,
    )
    assert decision.should_notify is True
    # 切换到带窗口的策略, 现在应能命中
    later = evaluate_notification(
        _good_record("x"),
        policy=NotificationPolicy(dedup_window_seconds=60),
        dedup_store=store,
        now=80.0,
    )
    assert later.should_notify is False


def test_evaluate_passes_when_dedup_store_missing_even_with_window():
    policy = NotificationPolicy(dedup_window_seconds=600)
    decision = evaluate_notification(_good_record(), policy=policy, dedup_store=None, now=0.0)
    assert decision.should_notify is True


def test_custom_scorer_overrides_default():
    record = {"ai_analysis": {"is_recommended": True}}
    policy = NotificationPolicy(min_score=99.9, scorer=lambda _r: 12.5)
    decision = evaluate_notification(record, policy=policy, now=0.0)
    assert decision.should_notify is False
    assert decision.score == 12.5
