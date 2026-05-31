"""
购买动作候选 API 路由。

提供候选列表、详情、确认、取消等接口。
M11 阶段只实现只读和安全动作（打开页面、复制链接），不实现真实下单。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.domain.models.purchase_action import (
    ActionType,
    CandidateStatus,
    PurchaseActionAuditLog,
    PurchaseActionCandidate,
)
from src.domain.repositories import purchase_action_repository as repo
from src.infrastructure.persistence.sqlite_connection import sqlite_connection
from src.services.purchase_action_policy import load_policy_config_from_env


router = APIRouter(prefix="/api/purchase-actions", tags=["purchase-actions"])


# ============================================================
# Pydantic 请求/响应模型
# ============================================================


class CandidateResponse(BaseModel):
    """候选记录响应。"""

    id: str
    item_id: str
    task_id: int | None
    status: str
    action_type: str
    price: float
    seller_id: str | None
    seller_name: str | None
    item_title: str
    item_url: str
    ai_reason: str
    policy_reason: str
    created_at: str
    updated_at: str
    expires_at: str | None
    confirmed_at: str | None
    executed_at: str | None


class CandidateListResponse(BaseModel):
    """候选列表响应。"""

    candidates: list[CandidateResponse]
    total: int
    page: int
    limit: int


class AuditLogResponse(BaseModel):
    """审计日志响应。"""

    id: str
    candidate_id: str
    action: str
    actor: str
    details: dict[str, Any]
    created_at: str


class PolicyConfigResponse(BaseModel):
    """策略配置响应。"""

    global_enabled: bool
    mode: str
    max_price: float | None
    daily_budget: float | None
    cooldown_seconds: int
    require_seller_allowlist: bool
    allow_auto_click: bool


class ConfirmRequest(BaseModel):
    """确认请求。"""

    action_type: str | None = Field(None, description="覆盖动作类型")


class DailyStatsResponse(BaseModel):
    """日统计响应。"""

    date: str
    total_spend: float
    candidate_count: int
    confirmed_count: int
    executed_count: int


# ============================================================
# 路由
# ============================================================


@router.get("/config", response_model=PolicyConfigResponse)
def get_policy_config() -> PolicyConfigResponse:
    """获取当前策略配置。"""
    config = load_policy_config_from_env()
    return PolicyConfigResponse(
        global_enabled=config.global_enabled,
        mode=config.mode.value,
        max_price=config.max_price,
        daily_budget=config.daily_budget,
        cooldown_seconds=config.cooldown_seconds,
        require_seller_allowlist=config.require_seller_allowlist,
        allow_auto_click=config.allow_auto_click,
    )


@router.get("/candidates", response_model=CandidateListResponse)
def list_candidates(
    status: str | None = Query(None, description="按状态筛选"),
    task_id: int | None = Query(None, description="按任务 ID 筛选"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
) -> CandidateListResponse:
    """列出候选记录。"""
    with sqlite_connection() as conn:
        status_enum = CandidateStatus(status) if status else None
        offset = (page - 1) * limit

        candidates = repo.list_candidates(
            conn,
            status=status_enum,
            task_id=task_id,
            limit=limit,
            offset=offset,
        )
        total = repo.count_candidates(conn, status=status_enum, task_id=task_id)

    return CandidateListResponse(
        candidates=[_candidate_to_response(c) for c in candidates],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/candidates/{candidate_id}", response_model=CandidateResponse)
def get_candidate(candidate_id: str) -> CandidateResponse:
    """获取候选详情。"""
    with sqlite_connection() as conn:
        candidate = repo.get_candidate_by_id(conn, candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="候选记录不存在")
    return _candidate_to_response(candidate)


@router.get("/candidates/{candidate_id}/audit-logs", response_model=list[AuditLogResponse])
def list_candidate_audit_logs(
    candidate_id: str,
    limit: int = Query(50, ge=1, le=200, description="最大数量"),
) -> list[AuditLogResponse]:
    """获取候选的审计日志。"""
    with sqlite_connection() as conn:
        candidate = repo.get_candidate_by_id(conn, candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="候选记录不存在")

        logs = repo.list_audit_logs(conn, candidate_id, limit=limit)

    return [_audit_log_to_response(log) for log in logs]


@router.post("/candidates/{candidate_id}/confirm", response_model=CandidateResponse)
def confirm_candidate(
    candidate_id: str,
    request: ConfirmRequest | None = None,
) -> CandidateResponse:
    """
    确认候选（用户手动确认）。

    确认后状态变为 confirmed，等待执行。
    """
    from datetime import datetime, timezone

    with sqlite_connection() as conn:
        candidate = repo.get_candidate_by_id(conn, candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="候选记录不存在")

        if candidate.status != CandidateStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"候选状态为 {candidate.status.value}，无法确认",
            )

        now = datetime.now(timezone.utc).isoformat()
        repo.update_candidate_status(
            conn,
            candidate_id,
            CandidateStatus.CONFIRMED,
            confirmed_at=now,
        )

        # 记录审计日志
        repo.create_audit_log(
            conn,
            candidate_id=candidate_id,
            action="confirm",
            actor="user",
            details={
                "action_type": request.action_type if request else None,
                "previous_status": candidate.status.value,
            },
        )

        # 重新获取更新后的记录
        candidate = repo.get_candidate_by_id(conn, candidate_id)

    return _candidate_to_response(candidate)  # type: ignore


@router.post("/candidates/{candidate_id}/cancel", response_model=CandidateResponse)
def cancel_candidate(candidate_id: str) -> CandidateResponse:
    """
    取消候选。

    取消后状态变为 cancelled。
    """
    with sqlite_connection() as conn:
        candidate = repo.get_candidate_by_id(conn, candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="候选记录不存在")

        if candidate.status not in (CandidateStatus.PENDING, CandidateStatus.CONFIRMED):
            raise HTTPException(
                status_code=400,
                detail=f"候选状态为 {candidate.status.value}，无法取消",
            )

        repo.update_candidate_status(conn, candidate_id, CandidateStatus.CANCELLED)

        # 记录审计日志
        repo.create_audit_log(
            conn,
            candidate_id=candidate_id,
            action="cancel",
            actor="user",
            details={"previous_status": candidate.status.value},
        )

        candidate = repo.get_candidate_by_id(conn, candidate_id)

    return _candidate_to_response(candidate)  # type: ignore


@router.post("/candidates/{candidate_id}/execute", response_model=CandidateResponse)
def execute_candidate(candidate_id: str) -> CandidateResponse:
    """
    执行候选动作。

    M11 阶段只支持 OPEN_ITEM_PAGE 和 COPY_LINK，返回执行结果。
    实际打开页面由前端处理，后端只记录状态。
    """
    from datetime import datetime, timezone

    with sqlite_connection() as conn:
        candidate = repo.get_candidate_by_id(conn, candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="候选记录不存在")

        if candidate.status != CandidateStatus.CONFIRMED:
            raise HTTPException(
                status_code=400,
                detail=f"候选状态为 {candidate.status.value}，需先确认才能执行",
            )

        # M11 只支持安全动作
        if candidate.action_type not in (ActionType.OPEN_ITEM_PAGE, ActionType.COPY_LINK):
            raise HTTPException(
                status_code=400,
                detail=f"M11 阶段不支持动作类型 {candidate.action_type.value}",
            )

        now = datetime.now(timezone.utc).isoformat()
        repo.update_candidate_status(
            conn,
            candidate_id,
            CandidateStatus.EXECUTED,
            executed_at=now,
        )

        # 记录审计日志
        repo.create_audit_log(
            conn,
            candidate_id=candidate_id,
            action="execute",
            actor="user",
            details={
                "action_type": candidate.action_type.value,
                "item_url": candidate.item_url,
            },
        )

        candidate = repo.get_candidate_by_id(conn, candidate_id)

    return _candidate_to_response(candidate)  # type: ignore


@router.get("/stats/daily", response_model=DailyStatsResponse)
def get_daily_stats(
    date: str | None = Query(None, description="日期 (YYYY-MM-DD)，默认今天"),
) -> DailyStatsResponse:
    """获取日统计。"""
    from datetime import datetime, timezone

    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with sqlite_connection() as conn:
        total_spend = repo.get_daily_spend(conn, date)

        # 统计各状态数量
        all_candidates = repo.list_candidates(conn, limit=10000)
        day_candidates = [
            c for c in all_candidates if c.created_at.startswith(date)
        ]

        confirmed_count = sum(
            1 for c in day_candidates
            if c.status in (CandidateStatus.CONFIRMED, CandidateStatus.EXECUTED)
        )
        executed_count = sum(
            1 for c in day_candidates if c.status == CandidateStatus.EXECUTED
        )

    return DailyStatsResponse(
        date=date,
        total_spend=total_spend,
        candidate_count=len(day_candidates),
        confirmed_count=confirmed_count,
        executed_count=executed_count,
    )


# ============================================================
# 辅助函数
# ============================================================


def _candidate_to_response(candidate: PurchaseActionCandidate) -> CandidateResponse:
    """转换候选为响应模型。"""
    return CandidateResponse(
        id=candidate.id,
        item_id=candidate.item_id,
        task_id=candidate.task_id,
        status=candidate.status.value,
        action_type=candidate.action_type.value,
        price=candidate.price,
        seller_id=candidate.seller_id,
        seller_name=candidate.seller_name,
        item_title=candidate.item_title,
        item_url=candidate.item_url,
        ai_reason=candidate.ai_reason,
        policy_reason=candidate.policy_reason,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
        expires_at=candidate.expires_at,
        confirmed_at=candidate.confirmed_at,
        executed_at=candidate.executed_at,
    )


def _audit_log_to_response(log: PurchaseActionAuditLog) -> AuditLogResponse:
    """转换审计日志为响应模型。"""
    return AuditLogResponse(
        id=log.id,
        candidate_id=log.candidate_id,
        action=log.action,
        actor=log.actor,
        details=log.details,
        created_at=log.created_at,
    )
