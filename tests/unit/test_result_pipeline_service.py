import asyncio

from src.services.result_pipeline_service import ResultPipelineService


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
