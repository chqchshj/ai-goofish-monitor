from src.utils import get_link_unique_key


def should_stop_for_debug_limit(debug_limit: int, processed_item_count: int) -> bool:
    return debug_limit > 0 and processed_item_count >= debug_limit


def is_processed_item(item_data: dict, processed_links: set[str]) -> bool:
    return get_link_unique_key(item_data["商品链接"]) in processed_links


def build_item_progress_message(index, total, title, *, skipped=False) -> str:
    if skipped:
        return f"[页内进度 {index}/{total}] 商品 '{title[:20]}...' 已存在，跳过。"
    return f"[页内进度 {index}/{total}] 发现新商品，获取详情: {title[:30]}..."
