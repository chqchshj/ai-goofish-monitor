"""
购买动作模块单元测试。

测试覆盖：
- 领域模型枚举（PurchaseActionMode/CandidateStatus/ActionType/SkipReason）
- PolicyConfig / PolicyDecision / ItemContext 数据契约
- evaluate_purchase_action Policy 纯函数（所有 skip 原因 + allow 路径）
- purchase_action_repository 仓储层（候选 CRUD + 审计日志 + 状态转换 + 日消费）
"""

from __future__ import annotations

import os
import tempfile
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.domain.models.purchase_action import (
    ActionType,
    CandidateStatus,
    ItemContext,
    PolicyConfig,
    PolicyDecision,
    PurchaseActionAuditLog,
    PurchaseActionCandidate,
    PurchaseActionMode,
    SkipReason,
)
from src.domain.repositories import purchase_action_repository as repo
from src.infrastructure.persistence.sqlite_connection import init_schema, sqlite_connection
from src.services.purchase_action_policy import (
    evaluate_purchase_action,
    load_policy_config_from_env,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def db_conn():
    """临时 SQLite 数据库连接（每个测试一个独立 db）。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with sqlite_connection(path) as conn:
            init_schema(conn)
            yield conn
    finally:
        os.unlink(path)


@pytest.fixture
def sample_item():
    """通过所有策略检查的样本商品。"""
    return ItemContext(
        item_id="item_001",
        price=500.0,
        seller_id="seller_001",
        is_recommended=True,
        is_sold_out=False,
    )


@pytest.fixture
def manual_confirm_config():
    """启用 manual_confirm 模式的策略配置。"""
    return PolicyConfig(
        global_enabled=True,
        mode=PurchaseActionMode.MANUAL_CONFIRM,
        max_price=1000.0,
        daily_budget=5000.0,
        cooldown_seconds=300,
        require_seller_allowlist=False,
    )


# ============================================================
# 1. 领域模型枚举与数据契约
# ============================================================


def test_purchase_action_mode_enum_values():
    assert PurchaseActionMode.NOTIFY_ONLY.value == "notify_only"
    assert PurchaseActionMode.MANUAL_CONFIRM.value == "manual_confirm"
    assert PurchaseActionMode.DRAFT_ORDER_DRY_RUN.value == "draft_order_dry_run"
    assert PurchaseActionMode.AUTO_CLICK.value == "auto_click"


def test_candidate_status_enum_values():
    assert CandidateStatus.PENDING.value == "pending"
    assert CandidateStatus.CONFIRMED.value == "confirmed"
    assert CandidateStatus.CANCELLED.value == "cancelled"
    assert CandidateStatus.EXPIRED.value == "expired"
    assert CandidateStatus.EXECUTED.value == "executed"


def test_action_type_safe_actions_only_in_m11():
    """M11 阶段仅允许安全动作类型。"""
    safe_types = {"open_item_page", "copy_link", "dry_run_order"}
    declared = {a.value for a in ActionType}
    assert declared == safe_types, "M11 阶段不应声明 auto_submit_order 等高风险动作"


def test_skip_reason_covers_all_policy_branches():
    """SkipReason 必须覆盖 evaluate_purchase_action 所有跳过分支。"""
    expected = {
        "global_disabled",
        "mode_notify_only",
        "price_exceeds_limit",
        "daily_budget_exhausted",
        "cooldown_active",
        "seller_not_in_allowlist",
        "not_recommended",
        "item_sold_out",
    }
    declared = {s.value for s in SkipReason}
    assert declared == expected


def test_policy_config_default_is_inert():
    """PolicyConfig 默认值是 inert：global_enabled=False, mode=notify_only。"""
    cfg = PolicyConfig()
    assert cfg.global_enabled is False
    assert cfg.mode == PurchaseActionMode.NOTIFY_ONLY
    assert cfg.max_price is None
    assert cfg.allow_auto_click is False


def test_policy_decision_to_dict_serialization():
    decision = PolicyDecision(
        allow=False,
        reason="测试原因",
        skip_reason=SkipReason.PRICE_EXCEEDS_LIMIT,
    )
    d = decision.to_dict()
    assert d["allow"] is False
    assert d["reason"] == "测试原因"
    assert d["skip_reason"] == "price_exceeds_limit"
    assert d["suggested_action"] is None


def test_load_policy_config_from_env_defaults_inert(monkeypatch):
    """env 未配置时返回 inert 默认值。"""
    for key in [
        "PURCHASE_ACTION_GLOBAL_ENABLED",
        "PURCHASE_ACTION_MODE",
        "PURCHASE_ACTION_MAX_PRICE",
        "PURCHASE_ACTION_DAILY_BUDGET",
        "PURCHASE_ACTION_COOLDOWN_SECONDS",
        "PURCHASE_ACTION_REQUIRE_SELLER_ALLOWLIST",
        "PURCHASE_ACTION_ALLOW_AUTO_CLICK",
    ]:
        monkeypatch.delenv(key, raising=False)

    cfg = load_policy_config_from_env()
    assert cfg.global_enabled is False
    assert cfg.mode == PurchaseActionMode.NOTIFY_ONLY
    assert cfg.max_price is None
    assert cfg.cooldown_seconds == 300
    assert cfg.allow_auto_click is False


# ============================================================
# 2. evaluate_purchase_action — 所有 skip 原因
# ============================================================


def test_policy_skip_global_disabled(sample_item):
    """全局开关关闭时跳过（默认 inert 行为）。"""
    cfg = PolicyConfig()  # global_enabled=False
    decision = evaluate_purchase_action(sample_item, cfg)
    assert decision.allow is False
    assert decision.skip_reason == SkipReason.GLOBAL_DISABLED


def test_policy_skip_mode_notify_only(sample_item):
    """全局启用但 mode=notify_only 时跳过。"""
    cfg = PolicyConfig(global_enabled=True, mode=PurchaseActionMode.NOTIFY_ONLY)
    decision = evaluate_purchase_action(sample_item, cfg)
    assert decision.allow is False
    assert decision.skip_reason == SkipReason.MODE_NOTIFY_ONLY


def test_policy_skip_not_recommended(manual_confirm_config):
    """AI 未推荐时跳过。"""
    item = ItemContext(item_id="x", price=100.0, seller_id="s", is_recommended=False)
    decision = evaluate_purchase_action(item, manual_confirm_config)
    assert decision.allow is False
    assert decision.skip_reason == SkipReason.NOT_RECOMMENDED


def test_policy_skip_item_sold_out(manual_confirm_config):
    """商品已售出时跳过。"""
    item = ItemContext(
        item_id="x",
        price=100.0,
        seller_id="s",
        is_recommended=True,
        is_sold_out=True,
    )
    decision = evaluate_purchase_action(item, manual_confirm_config)
    assert decision.allow is False
    assert decision.skip_reason == SkipReason.ITEM_SOLD_OUT


def test_policy_skip_when_max_price_unset(sample_item):
    """安全硬规则：未设价格上限时即使全局启用也禁止。"""
    cfg = PolicyConfig(
        global_enabled=True,
        mode=PurchaseActionMode.MANUAL_CONFIRM,
        max_price=None,  # 故意不设
    )
    decision = evaluate_purchase_action(sample_item, cfg)
    assert decision.allow is False
    assert decision.skip_reason == SkipReason.PRICE_EXCEEDS_LIMIT


def test_policy_skip_price_exceeds_limit(manual_confirm_config):
    """商品价格超过上限时跳过。"""
    expensive = ItemContext(
        item_id="x",
        price=2000.0,
        seller_id="s",
        is_recommended=True,
    )
    decision = evaluate_purchase_action(expensive, manual_confirm_config)  # max_price=1000
    assert decision.allow is False
    assert decision.skip_reason == SkipReason.PRICE_EXCEEDS_LIMIT


def test_policy_skip_daily_budget_exhausted(sample_item, manual_confirm_config):
    """日预算耗尽时跳过。"""
    decision = evaluate_purchase_action(
        sample_item,  # price=500
        manual_confirm_config,  # daily_budget=5000
        daily_spend=4800.0,  # 4800 + 500 > 5000
    )
    assert decision.allow is False
    assert decision.skip_reason == SkipReason.DAILY_BUDGET_EXHAUSTED


def test_policy_skip_cooldown_active(sample_item, manual_confirm_config):
    """商品在冷却期内时跳过。"""
    last = datetime.now(timezone.utc) - timedelta(seconds=60)  # 60 秒前
    decision = evaluate_purchase_action(
        sample_item,
        manual_confirm_config,  # cooldown_seconds=300
        last_candidate_time=last,
    )
    assert decision.allow is False
    assert decision.skip_reason == SkipReason.COOLDOWN_ACTIVE


def test_policy_skip_cooldown_expired_passes(sample_item, manual_confirm_config):
    """冷却期已过则不应被冷却 skip。"""
    last = datetime.now(timezone.utc) - timedelta(seconds=600)  # 10 分钟前
    decision = evaluate_purchase_action(
        sample_item,
        manual_confirm_config,
        last_candidate_time=last,
    )
    assert decision.allow is True


def test_policy_skip_seller_allowlist_empty(sample_item):
    """要求白名单但未传入或为空时跳过。"""
    cfg = PolicyConfig(
        global_enabled=True,
        mode=PurchaseActionMode.MANUAL_CONFIRM,
        max_price=1000.0,
        require_seller_allowlist=True,
    )
    decision = evaluate_purchase_action(sample_item, cfg, seller_allowlist=None)
    assert decision.allow is False
    assert decision.skip_reason == SkipReason.SELLER_NOT_IN_ALLOWLIST


def test_policy_skip_seller_not_in_allowlist(sample_item):
    """卖家不在白名单时跳过。"""
    cfg = PolicyConfig(
        global_enabled=True,
        mode=PurchaseActionMode.MANUAL_CONFIRM,
        max_price=1000.0,
        require_seller_allowlist=True,
    )
    decision = evaluate_purchase_action(
        sample_item,  # seller_id=seller_001
        cfg,
        seller_allowlist={"seller_002", "seller_003"},
    )
    assert decision.allow is False
    assert decision.skip_reason == SkipReason.SELLER_NOT_IN_ALLOWLIST


# ============================================================
# 3. evaluate_purchase_action — allow 路径
# ============================================================


def test_policy_allow_in_manual_confirm_suggests_open_item_page(sample_item, manual_confirm_config):
    """manual_confirm 模式下通过所有检查时建议 OPEN_ITEM_PAGE。"""
    decision = evaluate_purchase_action(sample_item, manual_confirm_config)
    assert decision.allow is True
    assert decision.skip_reason is None
    assert decision.suggested_action == ActionType.OPEN_ITEM_PAGE


def test_policy_allow_in_dry_run_mode_suggests_dry_run_order(sample_item):
    """draft_order_dry_run 模式下建议 DRY_RUN_ORDER。"""
    cfg = PolicyConfig(
        global_enabled=True,
        mode=PurchaseActionMode.DRAFT_ORDER_DRY_RUN,
        max_price=1000.0,
        require_seller_allowlist=False,
    )
    decision = evaluate_purchase_action(sample_item, cfg)
    assert decision.allow is True
    assert decision.suggested_action == ActionType.DRY_RUN_ORDER


def test_policy_allow_with_allowlist_match(sample_item):
    """卖家在白名单中应通过。"""
    cfg = PolicyConfig(
        global_enabled=True,
        mode=PurchaseActionMode.MANUAL_CONFIRM,
        max_price=1000.0,
        require_seller_allowlist=True,
    )
    decision = evaluate_purchase_action(
        sample_item,
        cfg,
        seller_allowlist={"seller_001"},
    )
    assert decision.allow is True


# ============================================================
# 4. Repository CRUD
# ============================================================


def _create_sample_candidate(conn) -> PurchaseActionCandidate:
    return repo.create_candidate(
        conn,
        item_id="item_x",
        task_id=1,
        action_type=ActionType.OPEN_ITEM_PAGE,
        price=500.0,
        seller_id="seller_x",
        seller_name="测试卖家",
        item_title="测试商品",
        item_url="https://example.com/x",
        ai_reason="价格合适",
        policy_reason="通过所有检查",
    )


def test_repo_create_and_get_candidate(db_conn):
    """创建候选后能查回来，状态为 pending。"""
    c = _create_sample_candidate(db_conn)
    assert c.status == CandidateStatus.PENDING
    assert c.id  # uuid
    assert c.item_id == "item_x"

    fetched = repo.get_candidate_by_id(db_conn, c.id)
    assert fetched is not None
    assert fetched.id == c.id
    assert fetched.status == CandidateStatus.PENDING
    assert fetched.price == 500.0


def test_repo_get_candidate_not_found(db_conn):
    assert repo.get_candidate_by_id(db_conn, "no-such-id") is None


def test_repo_update_candidate_status_pending_to_confirmed(db_conn):
    c = _create_sample_candidate(db_conn)
    now = datetime.now(timezone.utc).isoformat()
    ok = repo.update_candidate_status(
        db_conn, c.id, CandidateStatus.CONFIRMED, confirmed_at=now
    )
    assert ok is True

    refreshed = repo.get_candidate_by_id(db_conn, c.id)
    assert refreshed is not None
    assert refreshed.status == CandidateStatus.CONFIRMED
    assert refreshed.confirmed_at == now


def test_repo_list_and_count_candidates_by_status(db_conn):
    a = _create_sample_candidate(db_conn)
    b = _create_sample_candidate(db_conn)
    repo.update_candidate_status(db_conn, b.id, CandidateStatus.CANCELLED)

    all_pending = repo.list_candidates(db_conn, status=CandidateStatus.PENDING)
    all_cancelled = repo.list_candidates(db_conn, status=CandidateStatus.CANCELLED)

    assert len(all_pending) == 1
    assert all_pending[0].id == a.id
    assert len(all_cancelled) == 1
    assert all_cancelled[0].id == b.id

    assert repo.count_candidates(db_conn, status=CandidateStatus.PENDING) == 1
    assert repo.count_candidates(db_conn, status=CandidateStatus.CANCELLED) == 1
    assert repo.count_candidates(db_conn) == 2  # no filter


def test_repo_get_candidate_by_item_id_returns_latest(db_conn):
    c1 = _create_sample_candidate(db_conn)
    c2 = _create_sample_candidate(db_conn)  # same item_id, later
    latest = repo.get_candidate_by_item_id(db_conn, "item_x")
    assert latest is not None
    assert latest.id == c2.id  # 最近的一条


def test_repo_audit_log_create_and_list(db_conn):
    c = _create_sample_candidate(db_conn)
    log1 = repo.create_audit_log(
        db_conn,
        candidate_id=c.id,
        action="confirm",
        actor="user",
        details={"foo": "bar", "中文": "支持"},
    )
    log2 = repo.create_audit_log(
        db_conn,
        candidate_id=c.id,
        action="execute",
        actor="user",
        details={},
    )

    assert log1.id != log2.id
    logs = repo.list_audit_logs(db_conn, c.id)
    assert len(logs) == 2
    # ORDER BY created_at DESC
    assert logs[0].action in ("confirm", "execute")
    # details 中文正确序列化
    confirm_logs = [l for l in logs if l.action == "confirm"]
    assert confirm_logs[0].details["中文"] == "支持"


def test_repo_get_daily_spend_only_counts_confirmed_and_executed(db_conn):
    """日消费只统计 confirmed/executed，pending/cancelled 不计入。"""
    c1 = _create_sample_candidate(db_conn)  # pending, 500
    c2 = _create_sample_candidate(db_conn)  # 将变 confirmed
    c3 = _create_sample_candidate(db_conn)  # 将变 executed
    c4 = _create_sample_candidate(db_conn)  # 将变 cancelled

    repo.update_candidate_status(db_conn, c2.id, CandidateStatus.CONFIRMED)
    repo.update_candidate_status(db_conn, c3.id, CandidateStatus.EXECUTED)
    repo.update_candidate_status(db_conn, c4.id, CandidateStatus.CANCELLED)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    spend = repo.get_daily_spend(db_conn, today)
    # c2 (500) + c3 (500) = 1000；c1 (pending) 和 c4 (cancelled) 不计
    assert spend == 1000.0


def test_repo_create_candidate_extra_data_persisted(db_conn):
    """extra_data 字典字段正确序列化和反序列化。"""
    c = repo.create_candidate(
        db_conn,
        item_id="item_extra",
        task_id=None,
        action_type=ActionType.COPY_LINK,
        price=100.0,
        seller_id=None,
        seller_name=None,
        item_title="t",
        item_url="https://x",
        ai_reason="",
        policy_reason="",
        extra_data={"score": 0.92, "tags": ["good"]},
    )
    fetched = repo.get_candidate_by_id(db_conn, c.id)
    assert fetched is not None
    assert fetched.extra_data == {"score": 0.92, "tags": ["good"]}
