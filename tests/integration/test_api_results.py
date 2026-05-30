import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import results
from src.services.price_history_service import record_market_snapshots


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_results_filter_and_sort_for_keyword_recommendations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    target_file = jsonl_dir / "demo_full_data.jsonl"

    records = [
        {
            "爬取时间": "2026-01-01T01:00:00",
            "商品信息": {"当前售价": "¥1000", "发布时间": "2026-01-01 10:00"},
            "ai_analysis": {
                "analysis_source": "keyword",
                "is_recommended": True,
                "keyword_hit_count": 3,
                "reason": "命中 3 个关键词",
            },
        },
        {
            "爬取时间": "2026-01-01T02:00:00",
            "商品信息": {"当前售价": "¥2000", "发布时间": "2026-01-01 11:00"},
            "ai_analysis": {
                "analysis_source": "keyword",
                "is_recommended": True,
                "keyword_hit_count": 1,
                "reason": "命中 1 个关键词",
            },
        },
        {
            "爬取时间": "2026-01-01T03:00:00",
            "商品信息": {"当前售价": "¥3000", "发布时间": "2026-01-01 12:00"},
            "ai_analysis": {
                "analysis_source": "ai",
                "is_recommended": True,
                "reason": "AI推荐",
            },
        },
    ]
    _write_jsonl(target_file, records)

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    resp = client.get(
        "/api/results/demo_full_data.jsonl",
        params={"keyword_recommended_only": True, "sort_by": "keyword_hit_count", "sort_order": "desc"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 2
    assert data["items"][0]["ai_analysis"]["keyword_hit_count"] == 3
    assert data["items"][1]["ai_analysis"]["keyword_hit_count"] == 1

    resp = client.get(
        "/api/results/demo_full_data.jsonl",
        params={"ai_recommended_only": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 1
    assert data["items"][0]["ai_analysis"]["analysis_source"] == "ai"

    resp = client.get(
        "/api/results/demo_full_data.jsonl",
        params={"ai_recommended_only": True, "keyword_recommended_only": True},
    )
    assert resp.status_code == 400


def test_results_attribute_filters_for_yhb_and_free_shipping_list_and_export(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    target_file = jsonl_dir / "demo_full_data.jsonl"

    records = [
        {
            "爬取时间": "2026-01-01T01:00:00",
            "商品信息": {
                "商品ID": "1001",
                "商品标题": "YHB Free Shipping",
                "当前售价": "¥1000",
                "发布时间": "2026-01-01 10:00",
                "标签": ["验货宝", "包邮"],
            },
            "ai_analysis": {"analysis_source": "ai", "is_recommended": True},
        },
        {
            "爬取时间": "2026-01-01T02:00:00",
            "商品信息": {
                "商品ID": "1002",
                "商品标题": "YHB Only",
                "当前售价": "¥2000",
                "发布时间": "2026-01-01 11:00",
                "标签": [{"text": "验货宝"}],
            },
            "ai_analysis": {"analysis_source": "keyword", "is_recommended": True, "keyword_hit_count": 2},
        },
        {
            "爬取时间": "2026-01-01T03:00:00",
            "商品信息": {
                "商品ID": "1003",
                "商品标题": "Free Shipping Only",
                "当前售价": "¥3000",
                "发布时间": "2026-01-01 12:00",
                "标签": [{"name": "包邮"}],
            },
            "ai_analysis": {"analysis_source": "keyword", "is_recommended": False, "keyword_hit_count": 0},
        },
        {
            "爬取时间": "2026-01-01T04:00:00",
            "商品信息": {
                "商品ID": "1004",
                "商品标题": "标题写着验货宝和包邮但没有平台标签",
                "当前售价": "¥4000",
                "发布时间": "2026-01-01 13:00",
            },
            "ai_analysis": {"analysis_source": "ai", "is_recommended": False},
        },
    ]
    _write_jsonl(target_file, records)

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    yhb_resp = client.get("/api/results/demo_full_data.jsonl", params={"yhb_only": True})
    assert yhb_resp.status_code == 200
    yhb_payload = yhb_resp.json()
    assert yhb_payload["total_items"] == 2
    assert [item["商品信息"]["商品ID"] for item in yhb_payload["items"]] == ["1002", "1001"]

    free_shipping_resp = client.get(
        "/api/results/demo_full_data.jsonl",
        params={"free_shipping_only": True, "sort_by": "price", "sort_order": "asc"},
    )
    assert free_shipping_resp.status_code == 200
    free_shipping_payload = free_shipping_resp.json()
    assert free_shipping_payload["total_items"] == 2
    assert [item["商品信息"]["商品ID"] for item in free_shipping_payload["items"]] == ["1001", "1003"]

    combined_resp = client.get(
        "/api/results/demo_full_data.jsonl",
        params={"yhb_only": True, "free_shipping_only": True, "ai_recommended_only": True},
    )
    assert combined_resp.status_code == 200
    combined_payload = combined_resp.json()
    assert combined_payload["total_items"] == 1
    assert combined_payload["items"][0]["商品信息"]["商品ID"] == "1001"

    export_resp = client.get(
        "/api/results/demo_full_data.jsonl/export",
        params={"yhb_only": True, "free_shipping_only": True, "sort_by": "price", "sort_order": "asc"},
    )
    assert export_resp.status_code == 200
    assert "YHB Free Shipping" in export_resp.text
    assert "标题写着验货宝和包邮但没有平台标签" not in export_resp.text
    assert "YHB Only" not in export_resp.text
    assert "Free Shipping Only" not in export_resp.text


def test_results_personal_seller_filter_uses_ai_persona_analysis(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    target_file = jsonl_dir / "seller_persona_full_data.jsonl"

    records = [
        {"爬取时间": "2026-01-01T01:00:00", "商品信息": {"商品ID": "2001", "商品标题": "Personal Story", "当前售价": "¥1000", "标签": ["包邮"]}, "ai_analysis": {"analysis_source": "ai", "is_recommended": True, "criteria_analysis": {"seller_type": {"status": "通过", "persona": "个人玩家", "comment": "自用设备升级换代，可信的个人故事。"}}}},
        {"爬取时间": "2026-01-01T02:00:00", "商品信息": {"商品ID": "2002", "商品标题": "Nested Enthusiast", "当前售价": "¥2000"}, "ai_analysis": {"analysis_source": "ai", "is_recommended": True, "criteria_analysis": {"seller_type": {"status": "通过", "analysis_details": {"story": {"comment": "发烧友正常升级换代，描述像消费者自用转让。", "evidence": ["购入和使用时间线完整"]}}}}}},
        {"爬取时间": "2026-01-01T03:00:00", "商品信息": {"商品ID": "2003", "商品标题": "Merchant Story", "当前售价": "¥3000", "标签": ["包邮"]}, "ai_analysis": {"analysis_source": "ai", "is_recommended": True, "criteria_analysis": {"seller_type": {"persona": "个人卖家", "comment": "疑似商家/贩子批量出货，个人故事逻辑断裂。"}}}},
        {"爬取时间": "2026-01-01T04:00:00", "商品信息": {"商品ID": "2004", "商品标题": "Keyword Only", "当前售价": "¥4000"}, "ai_analysis": {"analysis_source": "keyword", "is_recommended": True, "keyword_hit_count": 2}},
        {"爬取时间": "2026-01-01T05:00:00", "商品信息": {"商品ID": "2005", "商品标题": "Old AI Shape", "当前售价": "¥5000"}, "ai_analysis": {"analysis_source": "ai", "is_recommended": True, "criteria_analysis": {}}},
    ]
    _write_jsonl(target_file, records)

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    resp = client.get("/api/results/seller_persona_full_data.jsonl", params={"personal_seller_only": True})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_items"] == 2
    assert [item["商品信息"]["商品ID"] for item in payload["items"]] == ["2002", "2001"]

    combined_resp = client.get("/api/results/seller_persona_full_data.jsonl", params={"personal_seller_only": True, "free_shipping_only": True})
    assert combined_resp.status_code == 200
    combined_payload = combined_resp.json()
    assert combined_payload["total_items"] == 1
    assert combined_payload["items"][0]["商品信息"]["商品ID"] == "2001"

    export_resp = client.get("/api/results/seller_persona_full_data.jsonl/export", params={"personal_seller_only": True})
    assert export_resp.status_code == 200
    assert "Personal Story" in export_resp.text
    assert "Nested Enthusiast" in export_resp.text
    assert "Merchant Story" not in export_resp.text
    assert "Keyword Only" not in export_resp.text
    assert "Old AI Shape" not in export_resp.text


def test_results_insights_and_export_csv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    target_file = jsonl_dir / "demo_full_data.jsonl"

    records = [
        {
            "爬取时间": "2026-01-02T09:00:00",
            "搜索关键字": "demo",
            "任务名称": "Demo 任务",
            "商品信息": {
                "商品ID": "1001",
                "商品标题": "Demo One",
                "商品链接": "https://www.goofish.com/item?id=1001",
                "当前售价": "¥950",
                "发布时间": "2026-01-02 08:30",
            },
            "卖家信息": {"卖家昵称": "卖家A"},
            "ai_analysis": {
                "analysis_source": "ai",
                "is_recommended": True,
                "reason": "价格低于近期均价",
            },
        },
        {
            "爬取时间": "2026-01-02T09:05:00",
            "搜索关键字": "demo",
            "任务名称": "Demo 任务",
            "商品信息": {
                "商品ID": "1002",
                "商品标题": "Demo Two",
                "商品链接": "https://www.goofish.com/item?id=1002",
                "当前售价": "¥1200",
                "发布时间": "2026-01-02 08:45",
            },
            "卖家信息": {"卖家昵称": "卖家B"},
            "ai_analysis": {
                "analysis_source": "keyword",
                "is_recommended": False,
                "reason": "未命中",
                "keyword_hit_count": 0,
            },
        },
    ]
    _write_jsonl(target_file, records)

    record_market_snapshots(
        keyword="demo",
        task_name="Demo 任务",
        items=[
            {
                "商品ID": "1001",
                "商品标题": "Demo One",
                "当前售价": "¥1000",
                "商品链接": "https://www.goofish.com/item?id=1001",
            },
            {
                "商品ID": "1002",
                "商品标题": "Demo Two",
                "当前售价": "¥1200",
                "商品链接": "https://www.goofish.com/item?id=1002",
            },
        ],
        run_id="run-1",
        snapshot_time="2026-01-01T10:00:00",
        seen_item_ids=set(),
    )
    record_market_snapshots(
        keyword="demo",
        task_name="Demo 任务",
        items=[
            {
                "商品ID": "1001",
                "商品标题": "Demo One",
                "当前售价": "¥950",
                "商品链接": "https://www.goofish.com/item?id=1001",
            },
            {
                "商品ID": "1002",
                "商品标题": "Demo Two",
                "当前售价": "¥1180",
                "商品链接": "https://www.goofish.com/item?id=1002",
            },
        ],
        run_id="run-2",
        snapshot_time="2026-01-02T10:00:00",
        seen_item_ids=set(),
    )

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    insights_resp = client.get("/api/results/demo_full_data.jsonl/insights")
    assert insights_resp.status_code == 200
    insights = insights_resp.json()
    assert insights["market_summary"]["sample_count"] == 2
    assert len(insights["daily_trend"]) == 2

    list_resp = client.get("/api/results/demo_full_data.jsonl")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert items[0]["price_insight"]["observation_count"] >= 1

    export_resp = client.get(
        "/api/results/demo_full_data.jsonl/export",
        params={"sort_by": "price", "sort_order": "asc"},
    )
    assert export_resp.status_code == 200
    assert "text/csv" in export_resp.headers["content-type"]
    text = export_resp.text
    assert "任务名称,搜索关键字,商品ID,商品标题" in text
    assert "Demo One" in text


def test_results_export_csv_supports_unicode_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    target_file = jsonl_dir / "演示_full_data.jsonl"

    records = [
        {
            "爬取时间": "2026-01-02T09:00:00",
            "搜索关键字": "演示",
            "任务名称": "演示任务",
            "商品信息": {
                "商品ID": "1001",
                "商品标题": "演示商品",
                "商品链接": "https://www.goofish.com/item?id=1001",
                "当前售价": "¥950",
                "发布时间": "2026-01-02 08:30",
            },
            "卖家信息": {"卖家昵称": "卖家A"},
            "ai_analysis": {
                "analysis_source": "ai",
                "is_recommended": True,
                "reason": "价格合理",
            },
        }
    ]
    _write_jsonl(target_file, records)

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    export_resp = client.get("/api/results/演示_full_data.jsonl/export")
    assert export_resp.status_code == 200
    assert "text/csv" in export_resp.headers["content-type"]
    disposition = export_resp.headers["content-disposition"]
    assert 'filename="export.csv"' in disposition
    assert "filename*=UTF-8''%E6%BC%94%E7%A4%BA_full_data.csv" in disposition


def test_results_blacklist_rules_hide_items_from_view_and_insights(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    target_file = jsonl_dir / "macbook_air_m1_full_data.jsonl"

    records = [
        {
            "爬取时间": "2026-01-03T09:00:00",
            "搜索关键字": "MacBook Air M1",
            "任务名称": "MacBook Air M1 监控",
            "商品信息": {
                "商品ID": "2001",
                "商品标题": "MacBook Air M1 8+256",
                "商品链接": "https://www.goofish.com/item?id=2001",
                "当前售价": "¥4200",
                "发布时间": "2026-01-03 08:30",
            },
            "卖家信息": {"卖家昵称": "卖家A"},
            "ai_analysis": {
                "analysis_source": "ai",
                "is_recommended": True,
                "reason": "符合目标机型",
            },
        },
        {
            "爬取时间": "2026-01-03T09:05:00",
            "搜索关键字": "MacBook Air M1",
            "任务名称": "MacBook Air M1 监控",
            "商品信息": {
                "商品ID": "2002",
                "商品标题": "MacBook Air Intel i5 8+256",
                "商品链接": "https://www.goofish.com/item?id=2002",
                "当前售价": "¥3100",
                "发布时间": "2026-01-03 08:35",
            },
            "卖家信息": {"卖家昵称": "卖家B"},
            "ai_analysis": {
                "analysis_source": "ai",
                "is_recommended": False,
                "reason": "不是目标机型",
            },
        },
        {
            "爬取时间": "2026-01-03T09:10:00",
            "搜索关键字": "MacBook Air M1",
            "任务名称": "MacBook Air M1 监控",
            "商品信息": {
                "商品ID": "2003",
                "商品标题": "MacBook Pro Intel 13寸",
                "商品链接": "https://www.goofish.com/item?id=2003",
                "当前售价": "¥3600",
                "发布时间": "2026-01-03 08:40",
            },
            "卖家信息": {"卖家昵称": "卖家C"},
            "ai_analysis": {
                "analysis_source": "ai",
                "is_recommended": False,
                "reason": "不是 Air M1",
            },
        },
    ]
    _write_jsonl(target_file, records)

    record_market_snapshots(
        keyword="MacBook Air M1",
        task_name="MacBook Air M1 监控",
        items=[
            {
                "商品ID": "2001",
                "商品标题": "MacBook Air M1 8+256",
                "当前售价": "¥4300",
                "商品链接": "https://www.goofish.com/item?id=2001",
            },
            {
                "商品ID": "2002",
                "商品标题": "MacBook Air Intel i5 8+256",
                "当前售价": "¥3200",
                "商品链接": "https://www.goofish.com/item?id=2002",
            },
            {
                "商品ID": "2003",
                "商品标题": "MacBook Pro Intel 13寸",
                "当前售价": "¥3700",
                "商品链接": "https://www.goofish.com/item?id=2003",
            },
        ],
        run_id="run-1",
        snapshot_time="2026-01-02T10:00:00",
        seen_item_ids=set(),
    )
    record_market_snapshots(
        keyword="MacBook Air M1",
        task_name="MacBook Air M1 监控",
        items=[
            {
                "商品ID": "2001",
                "商品标题": "MacBook Air M1 8+256",
                "当前售价": "¥4200",
                "商品链接": "https://www.goofish.com/item?id=2001",
            },
            {
                "商品ID": "2002",
                "商品标题": "MacBook Air Intel i5 8+256",
                "当前售价": "¥3100",
                "商品链接": "https://www.goofish.com/item?id=2002",
            },
            {
                "商品ID": "2003",
                "商品标题": "MacBook Pro Intel 13寸",
                "当前售价": "¥3600",
                "商品链接": "https://www.goofish.com/item?id=2003",
            },
        ],
        run_id="run-2",
        snapshot_time="2026-01-03T10:00:00",
        seen_item_ids=set(),
    )

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    update_rules_resp = client.put(
        "/api/results/macbook_air_m1_full_data.jsonl/blacklist-rules",
        json={"keywords": ["intel"]},
    )
    assert update_rules_resp.status_code == 200
    assert update_rules_resp.json()["keywords"] == ["intel"]

    rules_resp = client.get("/api/results/macbook_air_m1_full_data.jsonl/blacklist-rules")
    assert rules_resp.status_code == 200
    assert rules_resp.json()["keywords"] == ["intel"]

    filtered_resp = client.get("/api/results/macbook_air_m1_full_data.jsonl")
    assert filtered_resp.status_code == 200
    filtered_payload = filtered_resp.json()
    assert filtered_payload["total_items"] == 1
    assert [item["商品信息"]["商品ID"] for item in filtered_payload["items"]] == ["2001"]

    include_hidden_resp = client.get(
        "/api/results/macbook_air_m1_full_data.jsonl",
        params={"include_hidden": True},
    )
    assert include_hidden_resp.status_code == 200
    include_hidden_payload = include_hidden_resp.json()
    assert include_hidden_payload["total_items"] == 3
    hidden_item = next(
        item for item in include_hidden_payload["items"]
        if item["商品信息"]["商品ID"] == "2002"
    )
    assert hidden_item["_hidden_reason"] == "rule"
    assert hidden_item["_matched_blacklist_keywords"] == ["intel"]

    insights_resp = client.get("/api/results/macbook_air_m1_full_data.jsonl/insights")
    assert insights_resp.status_code == 200
    insights = insights_resp.json()
    assert insights["market_summary"]["sample_count"] == 1
    assert insights["market_summary"]["avg_price"] == 4200.0
    assert all(point["sample_count"] == 1 for point in insights["daily_trend"])

    list_resp = client.get("/api/results/macbook_air_m1_full_data.jsonl")
    assert list_resp.status_code == 200
    visible_item = list_resp.json()["items"][0]
    assert visible_item["price_insight"]["market_avg_price"] == 4200.0

    export_resp = client.get("/api/results/macbook_air_m1_full_data.jsonl/export")
    assert export_resp.status_code == 200
    assert "MacBook Air M1 8+256" in export_resp.text
    assert "MacBook Air Intel i5 8+256" not in export_resp.text
    assert "MacBook Pro Intel 13寸" not in export_resp.text

    download_resp = client.get("/api/results/files/macbook_air_m1_full_data.jsonl")
    assert download_resp.status_code == 200
    assert "MacBook Air Intel i5 8+256" in download_resp.text
    assert "MacBook Pro Intel 13寸" in download_resp.text
