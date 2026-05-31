"""
卖家跟进模块单元测试

测试覆盖：
- SellerStatus 枚举
- SellerTracking 领域模型
- seller_tracking_repository 仓储层
"""

import sqlite3
import tempfile
import os
from datetime import datetime, timezone

from src.domain.models.seller import SellerStatus, SellerTracking
from src.domain.repositories.seller_tracking_repository import (
    get_tracking,
    upsert_tracking,
    delete_tracking,
    list_trackings,
)


# ============ Domain Model Tests ============

def test_seller_status_enum_values():
    """测试 SellerStatus 枚举值"""
    assert SellerStatus.NORMAL.value == "normal"
    assert SellerStatus.FAVORITE.value == "favorite"
    assert SellerStatus.IGNORED.value == "ignored"
    assert SellerStatus.BLACKLISTED.value == "blacklisted"


def test_seller_tracking_to_dict():
    """测试 SellerTracking.to_dict() 序列化"""
    now = datetime.now(timezone.utc).isoformat()
    tracking = SellerTracking(
        seller_key="test_seller_123",
        status=SellerStatus.FAVORITE,
        notes="优质卖家，价格合理",
        tags=["优质", "快递快"],
        created_at=now,
        updated_at=now,
    )
    
    d = tracking.to_dict()
    
    assert d["seller_key"] == "test_seller_123"
    assert d["status"] == "favorite"
    assert d["notes"] == "优质卖家，价格合理"
    assert d["tags"] == ["优质", "快递快"]
    assert d["created_at"] == now
    assert d["updated_at"] == now


def test_seller_tracking_from_dict():
    """测试 SellerTracking.from_dict() 反序列化"""
    now_str = datetime.now(timezone.utc).isoformat()
    data = {
        "seller_key": "seller_abc",
        "status": "blacklisted",
        "notes": "骗子卖家",
        "tags": ["骗子", "差评"],
        "created_at": now_str,
        "updated_at": now_str,
    }
    
    tracking = SellerTracking.from_dict(data)
    
    assert tracking.seller_key == "seller_abc"
    assert tracking.status == SellerStatus.BLACKLISTED
    assert tracking.notes == "骗子卖家"
    assert tracking.tags == ["骗子", "差评"]


def test_seller_tracking_from_dict_with_defaults():
    """测试 from_dict 处理缺失字段"""
    data = {
        "seller_key": "minimal_seller",
    }
    
    tracking = SellerTracking.from_dict(data)
    
    assert tracking.seller_key == "minimal_seller"
    assert tracking.status == SellerStatus.NORMAL
    assert tracking.notes == ""
    assert tracking.tags == []


# ============ Repository Tests ============

def _create_test_db() -> tuple[str, sqlite3.Connection]:
    """创建测试用的临时数据库，返回 (路径, 连接)"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seller_tracking (
            seller_key TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'normal',
            notes TEXT DEFAULT '',
            tags_json TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_seller_tracking_status ON seller_tracking(status)")
    conn.commit()
    
    return path, conn


def test_upsert_and_get_tracking():
    """测试插入和查询跟进记录"""
    path, conn = _create_test_db()
    
    try:
        # 插入
        result = upsert_tracking(
            conn,
            "seller_001",
            status=SellerStatus.FAVORITE,
            notes="测试备注",
            tags=["测试"],
        )
        
        assert result.seller_key == "seller_001"
        assert result.status == SellerStatus.FAVORITE
        
        # 查询
        fetched = get_tracking(conn, "seller_001")
        
        assert fetched is not None
        assert fetched.seller_key == "seller_001"
        assert fetched.status == SellerStatus.FAVORITE
        assert fetched.notes == "测试备注"
        assert fetched.tags == ["测试"]
    finally:
        conn.close()
        os.unlink(path)


def test_upsert_updates_existing():
    """测试 upsert 更新已存在的记录"""
    path, conn = _create_test_db()
    
    try:
        # 首次插入
        upsert_tracking(
            conn,
            "seller_002",
            status=SellerStatus.NORMAL,
            notes="初始备注",
        )
        
        # 更新
        upsert_tracking(
            conn,
            "seller_002",
            status=SellerStatus.IGNORED,
            notes="已联系，等待回复",
            tags=["已联系"],
        )
        
        # 验证
        result = get_tracking(conn, "seller_002")
        
        assert result is not None
        assert result.status == SellerStatus.IGNORED
        assert result.notes == "已联系，等待回复"
        assert result.tags == ["已联系"]
    finally:
        conn.close()
        os.unlink(path)


def test_upsert_partial_update():
    """测试 upsert 只更新传入的字段"""
    path, conn = _create_test_db()
    
    try:
        # 首次插入
        upsert_tracking(
            conn,
            "seller_003",
            status=SellerStatus.FAVORITE,
            notes="初始备注",
            tags=["tag1"],
        )
        
        # 只更新 notes
        upsert_tracking(
            conn,
            "seller_003",
            notes="更新后的备注",
        )
        
        # 验证其他字段未变
        result = get_tracking(conn, "seller_003")
        
        assert result is not None
        assert result.status == SellerStatus.FAVORITE  # 未变
        assert result.notes == "更新后的备注"  # 已更新
        assert result.tags == ["tag1"]  # 未变
    finally:
        conn.close()
        os.unlink(path)


def test_get_tracking_not_found():
    """测试查询不存在的记录返回 None"""
    path, conn = _create_test_db()
    
    try:
        result = get_tracking(conn, "nonexistent_seller")
        assert result is None
    finally:
        conn.close()
        os.unlink(path)


def test_delete_tracking():
    """测试删除跟进记录"""
    path, conn = _create_test_db()
    
    try:
        # 插入
        upsert_tracking(
            conn,
            "seller_to_delete",
            status=SellerStatus.BLACKLISTED,
        )
        
        # 确认存在
        assert get_tracking(conn, "seller_to_delete") is not None
        
        # 删除
        deleted = delete_tracking(conn, "seller_to_delete")
        assert deleted is True
        
        # 确认已删除
        assert get_tracking(conn, "seller_to_delete") is None
    finally:
        conn.close()
        os.unlink(path)


def test_delete_tracking_not_found():
    """测试删除不存在的记录返回 False"""
    path, conn = _create_test_db()
    
    try:
        deleted = delete_tracking(conn, "nonexistent")
        assert deleted is False
    finally:
        conn.close()
        os.unlink(path)


def test_list_trackings():
    """测试列出所有跟进记录"""
    path, conn = _create_test_db()
    
    try:
        # 插入多条记录
        for i in range(3):
            upsert_tracking(
                conn,
                f"seller_{i}",
                status=SellerStatus.FAVORITE if i % 2 == 0 else SellerStatus.IGNORED,
            )
        
        # 列出全部
        results = list_trackings(conn)
        assert len(results) == 3
        
        # 按状态筛选
        favorites = list_trackings(conn, status=SellerStatus.FAVORITE)
        assert len(favorites) == 2
        
        ignored = list_trackings(conn, status=SellerStatus.IGNORED)
        assert len(ignored) == 1
    finally:
        conn.close()
        os.unlink(path)


def test_list_trackings_with_limit_offset():
    """测试分页查询"""
    path, conn = _create_test_db()
    
    try:
        # 插入 5 条记录
        for i in range(5):
            upsert_tracking(
                conn,
                f"seller_{i:02d}",
                status=SellerStatus.NORMAL,
            )
        
        # 分页
        page1 = list_trackings(conn, limit=2, offset=0)
        assert len(page1) == 2
        
        page2 = list_trackings(conn, limit=2, offset=2)
        assert len(page2) == 2
        
        page3 = list_trackings(conn, limit=2, offset=4)
        assert len(page3) == 1
    finally:
        conn.close()
        os.unlink(path)
