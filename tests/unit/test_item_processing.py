from src.pipeline.item_processing import (
    build_item_progress_message,
    is_processed_item,
    should_stop_for_debug_limit,
)
from src.utils import get_link_unique_key


def test_should_stop_for_debug_limit_only_when_positive_limit_reached() -> None:
    assert should_stop_for_debug_limit(0, 10) is False
    assert should_stop_for_debug_limit(3, 2) is False
    assert should_stop_for_debug_limit(3, 3) is True
    assert should_stop_for_debug_limit(3, 4) is True


def test_is_processed_item_uses_link_unique_key() -> None:
    item_data = {"商品链接": "https://www.goofish.com/item?id=123&spm=a"}
    processed_links = {get_link_unique_key(item_data["商品链接"])}

    assert is_processed_item(item_data, processed_links) is True
    assert is_processed_item({"商品链接": "https://www.goofish.com/item?id=456"}, processed_links) is False


def test_build_item_progress_message_preserves_existing_formats() -> None:
    title = "这是一个很长很长的商品标题用于测试截断逻辑"

    assert build_item_progress_message(1, 5, title, skipped=True) == (
        "[页内进度 1/5] 商品 '这是一个很长很长的商品标题用于测试截断逻...' 已存在，跳过。"
    )
    assert build_item_progress_message(2, 5, title) == (
        "[页内进度 2/5] 发现新商品，获取详情: 这是一个很长很长的商品标题用于测试截断逻辑..."
    )
