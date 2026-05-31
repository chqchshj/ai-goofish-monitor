"""
卖家跟进工作台 API 路由。

提供卖家详情聚合、跟进状态管理、商品历史查询等接口。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.domain.models.seller import SellerStatus, SellerTracking
from src.domain.repositories import seller_tracking_repository as repo
from src.infrastructure.persistence.sqlite_connection import sqlite_connection
from src.services.seller_aggregation_service import aggregate_sellers
from src.services.result_storage_service import query_result_records


router = APIRouter(prefix="/api/sellers", tags=["sellers"])


# ============================================================
# Pydantic 请求/响应模型
# ============================================================


class SellerTrackingUpdate(BaseModel):
    """卖家跟进状态更新请求。"""

    status: str | None = Field(None, description="跟进状态: normal/favorite/ignored/blacklisted")
    notes: str | None = Field(None, description="备注")
    tags: list[str] | None = Field(None, description="标签列表")


class SellerTrackingResponse(BaseModel):
    """卖家跟进记录响应。"""

    seller_key: str
    status: str
    notes: str
    tags: list[str]
    created_at: str
    updated_at: str


class SellerDetailResponse(BaseModel):
    """卖家详情聚合响应。"""

    seller_key: str
    seller_nickname: str
    status: str
    notes: str
    tags: list[str]
    item_count: int
    recommended_count: int
    min_price: float | None
    max_price: float | None
    latest_crawl_time: str
    personal_seller_summary: str | None
    tracking_created_at: str
    tracking_updated_at: str


class SellerListResponse(BaseModel):
    """卖家列表响应。"""

    sellers: list[SellerDetailResponse]
    total: int
    page: int
    limit: int


class StatusCountResponse(BaseModel):
    """状态统计响应。"""

    counts: dict[str, int]
    total: int


# ============================================================
# 辅助函数
# ============================================================


async def _fetch_all_items(result_filename: str, seller: str | None = None) -> list[dict[str, Any]]:
    """获取结果文件中的所有商品记录（用于聚合）。"""
    total, items = await query_result_records(
        result_filename,
        ai_recommended_only=False,
        keyword_recommended_only=False,
        sort_by="crawl_time",
        sort_order="desc",
        page=1,
        limit=10000,  # 获取所有记录用于聚合
        include_hidden=False,
        seller=seller,
    )
    return items


def _build_seller_detail(
    summary: dict[str, Any],
    tracking: SellerTracking | None,
) -> SellerDetailResponse:
    """从聚合摘要和跟进记录构建卖家详情响应。"""
    return SellerDetailResponse(
        seller_key=summary["seller_nickname"],
        seller_nickname=summary["seller_nickname"],
        status=tracking.status.value if tracking else SellerStatus.NORMAL.value,
        notes=tracking.notes if tracking else "",
        tags=tracking.tags if tracking else [],
        item_count=summary["item_count"],
        recommended_count=summary["recommended_count"],
        min_price=summary["min_price"],
        max_price=summary["max_price"],
        latest_crawl_time=summary["latest_crawl_time"] or "",
        personal_seller_summary=summary.get("personal_seller_summary"),
        tracking_created_at=tracking.created_at if tracking else "",
        tracking_updated_at=tracking.updated_at if tracking else "",
    )


# ============================================================
# API 端点
# ============================================================


@router.get("/workbench", response_model=SellerListResponse)
async def get_seller_workbench(
    result_filename: str = Query(..., description="结果文件名"),
    status: str | None = Query(None, description="按状态过滤: normal/favorite/ignored/blacklisted"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    获取卖家跟进工作台列表。

    聚合指定结果文件中的卖家，并关联跟进状态。
    """
    # 1. 从结果文件聚合卖家
    items = await _fetch_all_items(result_filename)
    seller_summaries = aggregate_sellers(items)

    # 2. 获取跟进状态
    with sqlite_connection() as conn:
        seller_keys = [s["seller_nickname"] for s in seller_summaries]
        trackings: dict[str, SellerTracking] = {}
        for key in seller_keys:
            tracking = repo.get_tracking(conn, key)
            if tracking:
                trackings[key] = tracking

    # 3. 组装详情列表
    details: list[SellerDetailResponse] = []
    for summary in seller_summaries:
        tracking = trackings.get(summary["seller_nickname"])
        detail = _build_seller_detail(summary, tracking)
        details.append(detail)

    # 4. 按状态过滤
    if status:
        try:
            filter_status = SellerStatus(status)
            details = [d for d in details if d.status == filter_status.value]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态值: {status}")

    # 5. 分页
    total = len(details)
    start = (page - 1) * limit
    end = start + limit
    paged_details = details[start:end]

    return SellerListResponse(
        sellers=paged_details,
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{seller_key}", response_model=SellerDetailResponse)
async def get_seller_detail(
    seller_key: str,
    result_filename: str = Query(..., description="结果文件名"),
):
    """
    获取单个卖家的详情。

    聚合该卖家在指定结果文件中的商品统计，并关联跟进状态。
    """
    # 1. 获取该卖家的商品记录
    items = await _fetch_all_items(result_filename, seller=seller_key)
    if not items:
        raise HTTPException(status_code=404, detail=f"未找到卖家: {seller_key}")

    # 2. 聚合统计
    summaries = aggregate_sellers(items)
    if not summaries:
        raise HTTPException(status_code=404, detail=f"未找到卖家: {seller_key}")
    summary = summaries[0]

    # 3. 获取跟进状态
    with sqlite_connection() as conn:
        tracking = repo.get_tracking(conn, seller_key)

    return _build_seller_detail(summary, tracking)


@router.patch("/{seller_key}", response_model=SellerTrackingResponse)
async def update_seller_tracking(
    seller_key: str,
    update: SellerTrackingUpdate,
):
    """
    更新卖家跟进状态。

    支持部分更新：只更新传入的非空字段。
    """
    # 解析状态
    status = None
    if update.status:
        try:
            status = SellerStatus(update.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态值: {update.status}")

    with sqlite_connection() as conn:
        tracking = repo.upsert_tracking(
            conn,
            seller_key,
            status=status,
            notes=update.notes,
            tags=update.tags,
        )

    return SellerTrackingResponse(
        seller_key=tracking.seller_key,
        status=tracking.status.value,
        notes=tracking.notes,
        tags=tracking.tags,
        created_at=tracking.created_at,
        updated_at=tracking.updated_at,
    )


@router.delete("/{seller_key}/tracking")
async def delete_seller_tracking(seller_key: str):
    """
    删除卖家跟进记录。

    删除后卖家恢复为默认状态（normal）。
    """
    with sqlite_connection() as conn:
        deleted = repo.delete_tracking(conn, seller_key)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"未找到卖家跟进记录: {seller_key}")

    return {"message": f"已删除卖家 {seller_key} 的跟进记录"}


@router.get("/{seller_key}/items")
async def get_seller_items(
    seller_key: str,
    result_filename: str = Query(..., description="结果文件名"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    获取卖家的商品历史列表。

    返回该卖家在指定结果文件中的所有商品记录。
    """
    total, items = await query_result_records(
        result_filename,
        ai_recommended_only=False,
        keyword_recommended_only=False,
        sort_by="crawl_time",
        sort_order="desc",
        page=page,
        limit=limit,
        include_hidden=False,
        seller=seller_key,
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/stats/by-status", response_model=StatusCountResponse)
async def get_tracking_stats():
    """
    获取跟进状态统计。

    返回各状态的卖家数量。
    """
    with sqlite_connection() as conn:
        counts = repo.count_by_status(conn)

    total = sum(counts.values())
    return StatusCountResponse(counts=counts, total=total)


@router.get("/tracking/list")
async def list_tracked_sellers(
    status: str | None = Query(None, description="按状态过滤"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """
    列出所有有跟进记录的卖家。

    不依赖结果文件，直接从 seller_tracking 表查询。
    """
    filter_status = None
    if status:
        try:
            filter_status = SellerStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态值: {status}")

    offset = (page - 1) * limit

    with sqlite_connection() as conn:
        trackings = repo.list_trackings(conn, status=filter_status, limit=limit, offset=offset)

    return {
        "trackings": [
            SellerTrackingResponse(
                seller_key=t.seller_key,
                status=t.status.value,
                notes=t.notes,
                tags=t.tags,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in trackings
        ],
        "page": page,
        "limit": limit,
    }
