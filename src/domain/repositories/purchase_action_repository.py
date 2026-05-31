"""
购买动作候选仓储。

提供 purchase_action_candidates 和 purchase_action_audit_logs 表的 CRUD 操作。
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.domain.models.purchase_action import (
    ActionType,
    CandidateStatus,
    PurchaseActionAuditLog,
    PurchaseActionCandidate,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _generate_id() -> str:
    """生成 UUID。"""
    return str(uuid.uuid4())


# =============================================================================
# Candidate CRUD
# =============================================================================


def create_candidate(
    conn: sqlite3.Connection,
    *,
    item_id: str,
    task_id: int | None,
    action_type: ActionType,
    price: float,
    seller_id: str | None,
    seller_name: str | None,
    item_title: str,
    item_url: str,
    ai_reason: str,
    policy_reason: str,
    expires_at: str | None = None,
    extra_data: dict | None = None,
) -> PurchaseActionCandidate:
    """创建候选记录。"""
    now = _now_iso()
    candidate_id = _generate_id()
    extra_json = json.dumps(extra_data or {}, ensure_ascii=False)

    conn.execute(
        """
        INSERT INTO purchase_action_candidates (
            id, item_id, task_id, status, action_type, price,
            seller_id, seller_name, item_title, item_url,
            ai_reason, policy_reason, created_at, updated_at,
            expires_at, extra_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            item_id,
            task_id,
            CandidateStatus.PENDING.value,
            action_type.value,
            price,
            seller_id,
            seller_name,
            item_title,
            item_url,
            ai_reason,
            policy_reason,
            now,
            now,
            expires_at,
            extra_json,
        ),
    )
    conn.commit()

    return PurchaseActionCandidate(
        id=candidate_id,
        item_id=item_id,
        task_id=task_id,
        status=CandidateStatus.PENDING,
        action_type=action_type,
        price=price,
        seller_id=seller_id,
        seller_name=seller_name,
        item_title=item_title,
        item_url=item_url,
        ai_reason=ai_reason,
        policy_reason=policy_reason,
        created_at=now,
        updated_at=now,
        expires_at=expires_at,
        extra_data=extra_data or {},
    )


def get_candidate_by_id(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> PurchaseActionCandidate | None:
    """根据 ID 获取候选记录。"""
    cursor = conn.execute(
        "SELECT * FROM purchase_action_candidates WHERE id = ?",
        (candidate_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return _row_to_candidate(row)


def list_candidates(
    conn: sqlite3.Connection,
    *,
    status: CandidateStatus | None = None,
    task_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[PurchaseActionCandidate]:
    """列出候选记录。"""
    conditions = []
    params: list = []

    if status is not None:
        conditions.append("status = ?")
        params.append(status.value)
    if task_id is not None:
        conditions.append("task_id = ?")
        params.append(task_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    params.extend([limit, offset])

    cursor = conn.execute(
        f"""
        SELECT * FROM purchase_action_candidates
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        params,
    )
    return [_row_to_candidate(row) for row in cursor.fetchall()]


def count_candidates(
    conn: sqlite3.Connection,
    *,
    status: CandidateStatus | None = None,
    task_id: int | None = None,
) -> int:
    """统计候选记录数量。"""
    conditions = []
    params: list = []

    if status is not None:
        conditions.append("status = ?")
        params.append(status.value)
    if task_id is not None:
        conditions.append("task_id = ?")
        params.append(task_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    cursor = conn.execute(
        f"SELECT COUNT(*) FROM purchase_action_candidates WHERE {where_clause}",
        params,
    )
    return cursor.fetchone()[0]


def update_candidate_status(
    conn: sqlite3.Connection,
    candidate_id: str,
    new_status: CandidateStatus,
    *,
    confirmed_at: str | None = None,
    executed_at: str | None = None,
) -> bool:
    """更新候选状态。"""
    now = _now_iso()
    updates = ["status = ?", "updated_at = ?"]
    params: list = [new_status.value, now]

    if confirmed_at:
        updates.append("confirmed_at = ?")
        params.append(confirmed_at)
    if executed_at:
        updates.append("executed_at = ?")
        params.append(executed_at)

    params.append(candidate_id)
    set_clause = ", ".join(updates)

    cursor = conn.execute(
        f"UPDATE purchase_action_candidates SET {set_clause} WHERE id = ?",
        params,
    )
    conn.commit()
    return cursor.rowcount > 0


def get_candidate_by_item_id(
    conn: sqlite3.Connection,
    item_id: str,
    *,
    since: str | None = None,
) -> PurchaseActionCandidate | None:
    """根据商品 ID 获取最近的候选记录（用于冷却检查）。"""
    if since:
        cursor = conn.execute(
            """
            SELECT * FROM purchase_action_candidates
            WHERE item_id = ? AND created_at >= ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (item_id, since),
        )
    else:
        cursor = conn.execute(
            """
            SELECT * FROM purchase_action_candidates
            WHERE item_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (item_id,),
        )
    row = cursor.fetchone()
    return _row_to_candidate(row) if row else None


def get_daily_spend(
    conn: sqlite3.Connection,
    date_str: str,
) -> float:
    """获取指定日期的已确认/已执行候选总价格（用于预算检查）。"""
    cursor = conn.execute(
        """
        SELECT COALESCE(SUM(price), 0) FROM purchase_action_candidates
        WHERE DATE(created_at) = ?
        AND status IN (?, ?)
        """,
        (date_str, CandidateStatus.CONFIRMED.value, CandidateStatus.EXECUTED.value),
    )
    return cursor.fetchone()[0]


def _row_to_candidate(row: sqlite3.Row) -> PurchaseActionCandidate:
    """将数据库行转换为候选对象。"""
    extra_data = json.loads(row["extra_data"]) if row["extra_data"] else {}
    return PurchaseActionCandidate(
        id=row["id"],
        item_id=row["item_id"],
        task_id=row["task_id"],
        status=CandidateStatus(row["status"]),
        action_type=ActionType(row["action_type"]),
        price=row["price"],
        seller_id=row["seller_id"],
        seller_name=row["seller_name"],
        item_title=row["item_title"],
        item_url=row["item_url"],
        ai_reason=row["ai_reason"],
        policy_reason=row["policy_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
        confirmed_at=row["confirmed_at"],
        executed_at=row["executed_at"],
        extra_data=extra_data,
    )


# =============================================================================
# Audit Log CRUD
# =============================================================================


def create_audit_log(
    conn: sqlite3.Connection,
    *,
    candidate_id: str,
    action: str,
    actor: str,
    details: dict | None = None,
) -> PurchaseActionAuditLog:
    """创建审计日志。"""
    now = _now_iso()
    log_id = _generate_id()
    details_json = json.dumps(details or {}, ensure_ascii=False)

    conn.execute(
        """
        INSERT INTO purchase_action_audit_logs (
            id, candidate_id, action, actor, details, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (log_id, candidate_id, action, actor, details_json, now),
    )
    conn.commit()

    return PurchaseActionAuditLog(
        id=log_id,
        candidate_id=candidate_id,
        action=action,
        actor=actor,
        details=details or {},
        created_at=now,
    )


def list_audit_logs(
    conn: sqlite3.Connection,
    candidate_id: str,
    *,
    limit: int = 50,
) -> Sequence[PurchaseActionAuditLog]:
    """列出候选的审计日志。"""
    cursor = conn.execute(
        """
        SELECT * FROM purchase_action_audit_logs
        WHERE candidate_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (candidate_id, limit),
    )
    return [_row_to_audit_log(row) for row in cursor.fetchall()]


def _row_to_audit_log(row: sqlite3.Row) -> PurchaseActionAuditLog:
    """将数据库行转换为审计日志对象。"""
    details = json.loads(row["details"]) if row["details"] else {}
    return PurchaseActionAuditLog(
        id=row["id"],
        candidate_id=row["candidate_id"],
        action=row["action"],
        actor=row["actor"],
        details=details,
        created_at=row["created_at"],
    )
