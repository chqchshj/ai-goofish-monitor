"""
卖家跟进记录仓储。

提供 seller_tracking 表的 CRUD 操作。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.domain.models.seller import SellerStatus, SellerTracking

if TYPE_CHECKING:
    from collections.abc import Sequence


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _row_to_tracking(row: sqlite3.Row) -> SellerTracking:
    """将数据库行转换为 SellerTracking 对象。"""
    tags = json.loads(row["tags_json"]) if row["tags_json"] else []
    return SellerTracking(
        seller_key=row["seller_key"],
        status=SellerStatus(row["status"]),
        notes=row["notes"],
        tags=tags,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_tracking(conn: sqlite3.Connection, seller_key: str) -> SellerTracking | None:
    """
    获取单个卖家的跟进记录。

    Args:
        conn: 数据库连接
        seller_key: 卖家唯一标识

    Returns:
        跟进记录，不存在则返回 None
    """
    cursor = conn.execute(
        "SELECT * FROM seller_tracking WHERE seller_key = ?",
        (seller_key,),
    )
    row = cursor.fetchone()
    return _row_to_tracking(row) if row else None


def list_trackings(
    conn: sqlite3.Connection,
    *,
    status: SellerStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[SellerTracking]:
    """
    列出卖家跟进记录。

    Args:
        conn: 数据库连接
        status: 可选状态过滤
        limit: 返回数量上限
        offset: 分页偏移

    Returns:
        跟进记录列表
    """
    if status:
        cursor = conn.execute(
            """
            SELECT * FROM seller_tracking
            WHERE status = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (status.value, limit, offset),
        )
    else:
        cursor = conn.execute(
            """
            SELECT * FROM seller_tracking
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
    return [_row_to_tracking(row) for row in cursor.fetchall()]


def upsert_tracking(
    conn: sqlite3.Connection,
    seller_key: str,
    *,
    status: SellerStatus | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
) -> SellerTracking:
    """
    创建或更新卖家跟进记录。

    使用 UPSERT 语义：存在则更新，不存在则创建。
    只更新传入的非 None 字段。

    Args:
        conn: 数据库连接
        seller_key: 卖家唯一标识
        status: 跟进状态
        notes: 备注
        tags: 标签列表

    Returns:
        更新后的跟进记录
    """
    now = _now_iso()
    existing = get_tracking(conn, seller_key)

    if existing:
        # 更新现有记录
        new_status = status if status is not None else existing.status
        new_notes = notes if notes is not None else existing.notes
        new_tags = tags if tags is not None else existing.tags

        conn.execute(
            """
            UPDATE seller_tracking
            SET status = ?, notes = ?, tags_json = ?, updated_at = ?
            WHERE seller_key = ?
            """,
            (new_status.value, new_notes, json.dumps(new_tags), now, seller_key),
        )
        conn.commit()

        return SellerTracking(
            seller_key=seller_key,
            status=new_status,
            notes=new_notes,
            tags=new_tags,
            created_at=existing.created_at,
            updated_at=now,
        )
    else:
        # 创建新记录
        new_status = status if status is not None else SellerStatus.NORMAL
        new_notes = notes if notes is not None else ""
        new_tags = tags if tags is not None else []

        conn.execute(
            """
            INSERT INTO seller_tracking (seller_key, status, notes, tags_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (seller_key, new_status.value, new_notes, json.dumps(new_tags), now, now),
        )
        conn.commit()

        return SellerTracking(
            seller_key=seller_key,
            status=new_status,
            notes=new_notes,
            tags=new_tags,
            created_at=now,
            updated_at=now,
        )


def delete_tracking(conn: sqlite3.Connection, seller_key: str) -> bool:
    """
    删除卖家跟进记录。

    Args:
        conn: 数据库连接
        seller_key: 卖家唯一标识

    Returns:
        是否删除成功（记录存在）
    """
    cursor = conn.execute(
        "DELETE FROM seller_tracking WHERE seller_key = ?",
        (seller_key,),
    )
    conn.commit()
    return cursor.rowcount > 0


def count_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    """
    按状态统计卖家跟进记录数量。

    Returns:
        状态 -> 数量的映射
    """
    cursor = conn.execute(
        """
        SELECT status, COUNT(*) as count
        FROM seller_tracking
        GROUP BY status
        """
    )
    return {row["status"]: row["count"] for row in cursor.fetchall()}
