"""
卖家聚合 API 测试。

覆盖：
- 聚合 key（卖家昵称）
- 计数、价格范围、最近发现时间
- 推荐商品计数
- 个人卖家画像摘要提取
- 缺失卖家字段降级（未知卖家）
- 与现有筛选参数兼容
"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import results


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_seller_aggregation_basic_grouping_and_stats(tmp_path, monkeypatch):
    """测试基本的卖家聚合：按昵称分组、商品数、价格范围、最近发现时间。"""
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    target_file = jsonl_dir / "seller_agg_full_data.jsonl"

    records = [
        {
            "爬取时间": "2026-01-01T10:00:00",
            "商品信息": {"商品ID": "1001", "当前售价": "¥1000"},
            "卖家信息": {"卖家昵称": "卖家A"},
            "ai_analysis": {"is_recommended": True, "analysis_source": "ai"},
        },
        {
            "爬取时间": "2026-01-01T12:00:00",
            "商品信息": {"商品ID": "1002", "当前售价": "¥2000"},
            "卖家信息": {"卖家昵称": "卖家A"},
            "ai_analysis": {"is_recommended": False, "analysis_source": "ai"},
        },
        {
            "爬取时间": "2026-01-01T11:00:00",
            "商品信息": {"商品ID": "1003", "当前售价": "¥1500"},
            "卖家信息": {"卖家昵称": "卖家B"},
            "ai_analysis": {"is_recommended": True, "analysis_source": "ai"},
        },
    ]
    _write_jsonl(target_file, records)

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    resp = client.get("/api/results/seller_agg_full_data.jsonl/sellers")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_sellers"] == 2
    assert data["total_items"] == 3

    sellers = {s["seller_nickname"]: s for s in data["sellers"]}

    # 卖家A: 2 items, price 1000-2000, latest 12:00
    assert sellers["卖家A"]["item_count"] == 2
    assert sellers["卖家A"]["min_price"] == 1000.0
    assert sellers["卖家A"]["max_price"] == 2000.0
    assert sellers["卖家A"]["latest_crawl_time"] == "2026-01-01T12:00:00"
    assert sellers["卖家A"]["recommended_count"] == 1

    # 卖家B: 1 item, price 1500, latest 11:00
    assert sellers["卖家B"]["item_count"] == 1
    assert sellers["卖家B"]["min_price"] == 1500.0
    assert sellers["卖家B"]["max_price"] == 1500.0
    assert sellers["卖家B"]["latest_crawl_time"] == "2026-01-01T11:00:00"
    assert sellers["卖家B"]["recommended_count"] == 1


def test_seller_aggregation_missing_seller_fallback(tmp_path, monkeypatch):
    """测试缺失卖家昵称时降级为"未知卖家"。"""
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    target_file = jsonl_dir / "missing_seller_full_data.jsonl"

    records = [
        {
            "爬取时间": "2026-01-01T10:00:00",
            "商品信息": {"商品ID": "2001", "当前售价": "¥500"},
            "ai_analysis": {"is_recommended": False, "analysis_source": "keyword"},
        },
        {
            "爬取时间": "2026-01-01T11:00:00",
            "商品信息": {"商品ID": "2002", "当前售价": "¥600", "卖家昵称": ""},
            "卖家信息": {},
            "ai_analysis": {"is_recommended": False, "analysis_source": "keyword"},
        },
        {
            "爬取时间": "2026-01-01T12:00:00",
            "商品信息": {"商品ID": "2003", "当前售价": "¥700"},
            "卖家信息": {"卖家昵称": "有名卖家"},
            "ai_analysis": {"is_recommended": True, "analysis_source": "ai"},
        },
    ]
    _write_jsonl(target_file, records)

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    resp = client.get("/api/results/missing_seller_full_data.jsonl/sellers")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_sellers"] == 2
    sellers = {s["seller_nickname"]: s for s in data["sellers"]}

    # 未知卖家: 2 items (no nickname)
    assert "未知卖家" in sellers
    assert sellers["未知卖家"]["item_count"] == 2
    assert sellers["未知卖家"]["min_price"] == 500.0
    assert sellers["未知卖家"]["max_price"] == 600.0

    # 有名卖家: 1 item
    assert sellers["有名卖家"]["item_count"] == 1


def test_seller_aggregation_personal_seller_persona_extraction(tmp_path, monkeypatch):
    """测试从 AI 分析中提取个人卖家画像摘要。"""
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    target_file = jsonl_dir / "persona_full_data.jsonl"

    records = [
        {
            "爬取时间": "2026-01-01T10:00:00",
            "商品信息": {"商品ID": "3001", "当前售价": "¥1000"},
            "卖家信息": {"卖家昵称": "个人玩家"},
            "ai_analysis": {
                "is_recommended": True,
                "analysis_source": "ai",
                "criteria_analysis": {
                    "seller_type": {"status": "通过", "persona": "发烧友", "comment": "自用升级换代"}
                },
            },
        },
        {
            "爬取时间": "2026-01-01T11:00:00",
            "商品信息": {"商品ID": "3002", "当前售价": "¥1200"},
            "卖家信息": {"卖家昵称": "个人玩家"},
            "ai_analysis": {
                "is_recommended": True,
                "analysis_source": "ai",
                "criteria_analysis": {
                    "seller_type": {"status": "通过", "persona": "学生党", "comment": "毕业出闲置"}
                },
            },
        },
        {
            "爬取时间": "2026-01-01T12:00:00",
            "商品信息": {"商品ID": "3003", "当前售价": "¥800"},
            "卖家信息": {"卖家昵称": "商家"},
            "ai_analysis": {
                "is_recommended": False,
                "analysis_source": "ai",
                "criteria_analysis": {
                    "seller_type": {"status": "不通过", "persona": "二手贩子"}
                },
            },
        },
        {
            "爬取时间": "2026-01-01T13:00:00",
            "商品信息": {"商品ID": "3004", "当前售价": "¥900"},
            "卖家信息": {"卖家昵称": "关键词卖家"},
            "ai_analysis": {
                "is_recommended": True,
                "analysis_source": "keyword",
                "keyword_hit_count": 3,
            },
        },
    ]
    _write_jsonl(target_file, records)

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    resp = client.get("/api/results/persona_full_data.jsonl/sellers")
    assert resp.status_code == 200
    data = resp.json()

    sellers = {s["seller_nickname"]: s for s in data["sellers"]}

    # 个人玩家: 2 items, 2 different personas
    assert sellers["个人玩家"]["item_count"] == 2
    summary = sellers["个人玩家"]["personal_seller_summary"]
    assert summary is not None
    assert "发烧友" in summary
    assert "学生党" in summary

    # 商家: 1 item, has persona
    assert sellers["商家"]["personal_seller_summary"] == "二手贩子"

    # 关键词卖家: keyword source, no persona
    assert sellers["关键词卖家"]["personal_seller_summary"] is None


def test_seller_aggregation_with_filters(tmp_path, monkeypatch):
    """测试卖家聚合与现有筛选参数兼容。"""
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    target_file = jsonl_dir / "filter_full_data.jsonl"

    records = [
        {
            "爬取时间": "2026-01-01T10:00:00",
            "商品信息": {"商品ID": "4001", "当前售价": "¥1000", "标签": ["验货宝"]},
            "卖家信息": {"卖家昵称": "卖家X"},
            "ai_analysis": {"is_recommended": True, "analysis_source": "ai"},
        },
        {
            "爬取时间": "2026-01-01T11:00:00",
            "商品信息": {"商品ID": "4002", "当前售价": "¥2000"},
            "卖家信息": {"卖家昵称": "卖家X"},
            "ai_analysis": {"is_recommended": False, "analysis_source": "ai"},
        },
        {
            "爬取时间": "2026-01-01T12:00:00",
            "商品信息": {"商品ID": "4003", "当前售价": "¥1500", "标签": ["验货宝"]},
            "卖家信息": {"卖家昵称": "卖家Y"},
            "ai_analysis": {"is_recommended": True, "analysis_source": "ai"},
        },
    ]
    _write_jsonl(target_file, records)

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    # 无筛选: 2 sellers, 3 items
    resp = client.get("/api/results/filter_full_data.jsonl/sellers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sellers"] == 2
    assert data["total_items"] == 3

    # AI 推荐筛选: 2 sellers, 2 items
    resp = client.get("/api/results/filter_full_data.jsonl/sellers", params={"ai_recommended_only": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 2
    sellers = {s["seller_nickname"]: s for s in data["sellers"]}
    assert sellers["卖家X"]["item_count"] == 1
    assert sellers["卖家Y"]["item_count"] == 1

    # 验货宝筛选: 2 sellers, 2 items
    resp = client.get("/api/results/filter_full_data.jsonl/sellers", params={"yhb_only": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 2

    # 组合筛选: AI 推荐 + 验货宝
    resp = client.get(
        "/api/results/filter_full_data.jsonl/sellers",
        params={"ai_recommended_only": True, "yhb_only": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 2


def test_seller_aggregation_sorted_by_item_count(tmp_path, monkeypatch):
    """测试卖家聚合结果按商品数量降序排列。"""
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    target_file = jsonl_dir / "sort_full_data.jsonl"

    records = [
        {"爬取时间": "2026-01-01T10:00:00", "商品信息": {"商品ID": "5001", "当前售价": "¥100"}, "卖家信息": {"卖家昵称": "少量卖家"}, "ai_analysis": {"is_recommended": False}},
        {"爬取时间": "2026-01-01T11:00:00", "商品信息": {"商品ID": "5002", "当前售价": "¥200"}, "卖家信息": {"卖家昵称": "大量卖家"}, "ai_analysis": {"is_recommended": False}},
        {"爬取时间": "2026-01-01T12:00:00", "商品信息": {"商品ID": "5003", "当前售价": "¥300"}, "卖家信息": {"卖家昵称": "大量卖家"}, "ai_analysis": {"is_recommended": False}},
        {"爬取时间": "2026-01-01T13:00:00", "商品信息": {"商品ID": "5004", "当前售价": "¥400"}, "卖家信息": {"卖家昵称": "大量卖家"}, "ai_analysis": {"is_recommended": False}},
        {"爬取时间": "2026-01-01T14:00:00", "商品信息": {"商品ID": "5005", "当前售价": "¥500"}, "卖家信息": {"卖家昵称": "中量卖家"}, "ai_analysis": {"is_recommended": False}},
        {"爬取时间": "2026-01-01T15:00:00", "商品信息": {"商品ID": "5006", "当前售价": "¥600"}, "卖家信息": {"卖家昵称": "中量卖家"}, "ai_analysis": {"is_recommended": False}},
    ]
    _write_jsonl(target_file, records)

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    resp = client.get("/api/results/sort_full_data.jsonl/sellers")
    assert resp.status_code == 200
    data = resp.json()

    # 按商品数量降序: 大量(3) > 中量(2) > 少量(1)
    assert data["sellers"][0]["seller_nickname"] == "大量卖家"
    assert data["sellers"][0]["item_count"] == 3
    assert data["sellers"][1]["seller_nickname"] == "中量卖家"
    assert data["sellers"][1]["item_count"] == 2
    assert data["sellers"][2]["seller_nickname"] == "少量卖家"
    assert data["sellers"][2]["item_count"] == 1


def test_seller_aggregation_file_not_found(tmp_path, monkeypatch):
    """测试文件不存在时返回 404。"""
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    resp = client.get("/api/results/nonexistent_full_data.jsonl/sellers")
    assert resp.status_code == 404
