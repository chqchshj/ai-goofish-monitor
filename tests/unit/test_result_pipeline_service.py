import asyncio

from src.services.notification_filter import (
    InMemoryDedupStore,
    LEVEL_HIGH,
    NotificationPolicy,
)
from src.services.result_pipeline_service import (
    ResultPipelineService,
    _policy_from_env,
)


def test_result_pipeline_service_saves_record_and_notifies_recommended_item():
    saved_calls = []
    notified_calls = []
    record = {
        "商品信息": {"商品ID": "item-1", "商品标题": "Sony A7M4"},
        "ai_analysis": {"is_recommended": True, "reason": "价格合适"},
    }
    targets = [{"channel": "wecom-app", "agent_id": "1000001"}]

    async def saver(saved_record: dict, keyword: str):
        saved_calls.append((saved_record, keyword))
        return True

    async def notifier(item_data: dict, reason: str, notification_targets=None):
        notified_calls.append((item_data, reason, notification_targets))

    async def run():
        service = ResultPipelineService(saver=saver, notifier=notifier)
        return await service.persist_and_notify(
            record,
            "相机",
            notification_targets=targets,
        )

    outcome = asyncio.run(run())

    assert saved_calls == [(record, "相机")]
    assert notified_calls == [(record["商品信息"], "价格合适", targets)]
    assert outcome.saved is True
    assert outcome.notified is True
    assert outcome.save_count_increment == 1


def test_result_pipeline_service_skips_notification_for_non_recommended_item():
    notified_calls = []
    record = {
        "商品信息": {"商品ID": "item-2"},
        "ai_analysis": {"is_recommended": False, "reason": "不符合"},
    }

    async def saver(saved_record: dict, keyword: str):
        return False

    async def notifier(item_data: dict, reason: str, notification_targets=None):
        notified_calls.append((item_data, reason, notification_targets))

    async def run():
        service = ResultPipelineService(saver=saver, notifier=notifier)
        return await service.persist_and_notify(record, "相机")

    outcome = asyncio.run(run())

    assert notified_calls == []
    assert outcome.saved is False
    assert outcome.notified is False
    assert outcome.save_count_increment == 0


def test_result_pipeline_service_swallows_notification_errors_after_save(capsys):
    record = {
        "商品信息": {"商品ID": "item-3"},
        "ai_analysis": {"is_recommended": True},
    }

    async def saver(saved_record: dict, keyword: str):
        return True

    async def notifier(item_data: dict, reason: str, notification_targets=None):
        raise RuntimeError("notification backend down")

    async def run():
        service = ResultPipelineService(saver=saver, notifier=notifier)
        return await service.persist_and_notify(record, "相机")

    outcome = asyncio.run(run())

    assert outcome.saved is True
    assert outcome.notified is False
    assert outcome.save_count_increment == 1
    assert "发送推荐通知失败" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# P4-1 通知降噪 seam 集成测试
# ---------------------------------------------------------------------------


def _record(item_id: str, *, is_recommended: bool = True, statuses: list[str] | None = None) -> dict:
    criteria = {}
    if statuses:
        for i, status in enumerate(statuses):
            criteria[f"f{i}"] = {"status": status}
    return {
        "商品信息": {"商品ID": item_id},
        "ai_analysis": {
            "is_recommended": is_recommended,
            "reason": "test",
            "criteria_analysis": criteria,
        },
    }


def test_result_pipeline_with_min_score_filters_low_score():
    notified_calls = []

    async def saver(record, keyword):
        return True

    async def notifier(item_data, reason, notification_targets=None):
        notified_calls.append((item_data, reason))

    record = _record("low", statuses=["FAIL", "FAIL"])  # score = 0
    policy = NotificationPolicy(min_score=50.0)

    async def run():
        service = ResultPipelineService(saver=saver, notifier=notifier, policy=policy)
        return await service.persist_and_notify(record, "kw")

    outcome = asyncio.run(run())
    assert outcome.saved is True
    assert outcome.notified is False
    assert notified_calls == []
    assert outcome.skip_reason is not None and "阈值" in outcome.skip_reason
    assert outcome.decision is not None


def test_result_pipeline_with_min_level_filters_below_high():
    notified_calls = []

    async def saver(record, keyword):
        return True

    async def notifier(item_data, reason, notification_targets=None):
        notified_calls.append((item_data, reason))

    # WARN/WARN -> 50 -> medium
    record = _record("mid", statuses=["WARN", "WARN"])
    policy = NotificationPolicy(min_level=LEVEL_HIGH)

    async def run():
        service = ResultPipelineService(saver=saver, notifier=notifier, policy=policy)
        return await service.persist_and_notify(record, "kw")

    outcome = asyncio.run(run())
    assert outcome.saved is True
    assert outcome.notified is False
    assert notified_calls == []


def test_result_pipeline_dedup_window_blocks_repeated_item():
    notified_calls = []

    async def saver(record, keyword):
        return True

    async def notifier(item_data, reason, notification_targets=None):
        notified_calls.append((item_data, reason))

    policy = NotificationPolicy(dedup_window_seconds=600)
    store = InMemoryDedupStore()
    record = _record("same", statuses=["PASS"])

    async def run():
        service = ResultPipelineService(
            saver=saver, notifier=notifier, policy=policy, dedup_store=store
        )
        first = await service.persist_and_notify(record, "kw")
        second = await service.persist_and_notify(record, "kw")
        return first, second

    first, second = asyncio.run(run())
    assert first.notified is True
    assert second.notified is False
    assert second.skip_reason is not None and "窗口" in second.skip_reason
    assert len(notified_calls) == 1


def test_result_pipeline_default_no_policy_keeps_legacy_behavior():
    """没有 policy 时仍然以 is_recommended 为唯一判据 (向后兼容)。"""
    notified_calls = []

    async def saver(record, keyword):
        return True

    async def notifier(item_data, reason, notification_targets=None):
        notified_calls.append((item_data, reason))

    # 即使 score 很低 (FAIL/FAIL = 0), 没有 policy 时仍应通知。
    record = _record("legacy", statuses=["FAIL", "FAIL"])

    async def run():
        service = ResultPipelineService(saver=saver, notifier=notifier)
        return await service.persist_and_notify(record, "kw")

    outcome = asyncio.run(run())
    assert outcome.notified is True
    assert outcome.skip_reason is None
    assert outcome.decision is None
    assert len(notified_calls) == 1


def test_policy_from_env_returns_none_when_settings_inert():
    class Inert:
        notification_min_score = None
        notification_min_level = None
        notification_dedup_window_seconds = 0
        notification_seller_throttle_window_seconds = 0

    policy, store, seller_store = _policy_from_env(Inert())
    assert policy is None
    assert store is None
    assert seller_store is None


def test_policy_from_env_builds_full_policy():
    class Settings:
        notification_min_score = 60.0
        notification_min_level = "MEDIUM"
        notification_dedup_window_seconds = 300
        notification_seller_throttle_window_seconds = 0

    policy, store, seller_store = _policy_from_env(Settings())
    assert policy is not None
    assert policy.min_score == 60.0
    assert policy.min_level == "medium"
    assert policy.dedup_window_seconds == 300
    assert policy.seller_throttle_window_seconds == 0
    assert store is not None
    assert seller_store is None


def test_policy_from_env_ignores_invalid_level():
    class Settings:
        notification_min_score = None
        notification_min_level = "ULTRA"
        notification_dedup_window_seconds = 0
        notification_seller_throttle_window_seconds = 0

    policy, store, seller_store = _policy_from_env(Settings())
    # 无效等级且无其他字段 → 视作 inert
    assert policy is None
    assert store is None
    assert seller_store is None


def test_from_settings_falls_back_to_inert_without_settings():
    async def saver(record, keyword):
        return True

    async def notifier(item_data, reason, notification_targets=None):
        pass

    # notification_settings=None 且 load_notification_settings 不 raise 时也应能构造
    class FakeSettings:
        notification_min_score = None
        notification_min_level = None
        notification_dedup_window_seconds = 0
        notification_seller_throttle_window_seconds = 0

    service = ResultPipelineService.from_settings(
        saver=saver, notifier=notifier, notification_settings=FakeSettings()
    )
    # 内部 policy 应为 None — 行为完全等价于不带 policy 的实例
    assert service._policy is None
    assert service._dedup_store is None
    assert service._seller_throttle_store is None
