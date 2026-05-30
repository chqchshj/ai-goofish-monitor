
"""
Q7 QA audit: edge-case tests for result management batch operations.
Tests boundary conditions not covered by existing integration tests.
"""
import csv
import json
from io import StringIO

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import results


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _csv_rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(StringIO(text)))


def _make_record(item_id, title="Item", price="¥100", recommended=True, source="ai"):
    return {
        "爬取时间": f"2026-01-01T0{item_id[-1]}:00:00",
        "搜索关键字": "test",
        "任务名称": "Test Task",
        "商品信息": {
            "商品ID": item_id,
            "商品标题": title,
            "商品链接": f"https://www.goofish.com/item?id={item_id}",
            "当前售价": price,
            "发布时间": "2026-01-01 10:00",
        },
        "卖家信息": {"卖家昵称": "Seller"},
        "ai_analysis": {
            "analysis_source": source,
            "is_recommended": recommended,
            "reason": "test",
        },
    }


def test_batch_duplicate_item_ids(tmp_path, monkeypatch):
    """Duplicate item_ids in batch request should be deduplicated — updated_count reflects unique items."""
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir()
    _write_jsonl(jsonl_dir / "dup_test_full_data.jsonl", [_make_record("5001"), _make_record("5002")])

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    # Send duplicate item_ids
    resp = client.patch(
        "/api/results/dup_test_full_data.jsonl/items/batch",
        json={"item_ids": ["5001", "5001", "5001", "5002", "5002"], "is_processed": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Should report unique count, not duplicated count
    assert data["requested_count"] == 2  # dict.fromkeys deduplicates
    assert data["updated_count"] == 2


def test_batch_whitespace_only_item_ids(tmp_path, monkeypatch):
    """Whitespace-only item_ids should be stripped and treated as empty."""
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir()
    _write_jsonl(jsonl_dir / "ws_test_full_data.jsonl", [_make_record("6001")])

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    # All whitespace item_ids → effectively empty → 400
    resp = client.patch(
        "/api/results/ws_test_full_data.jsonl/items/batch",
        json={"item_ids": ["  ", "\t", ""], "is_processed": True},
    )
    assert resp.status_code == 400


def test_batch_cross_file_item_id(tmp_path, monkeypatch):
    """Item IDs from a different file should not be updated — returns 404."""
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir()
    _write_jsonl(jsonl_dir / "file_a_full_data.jsonl", [_make_record("7001")])
    _write_jsonl(jsonl_dir / "file_b_full_data.jsonl", [_make_record("7002")])

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    # Try to update item from file_a using file_b endpoint
    resp = client.patch(
        "/api/results/file_b_full_data.jsonl/items/batch",
        json={"item_ids": ["7001"], "is_processed": True},
    )
    # 7001 belongs to file_a, not file_b → 0 updated → 404
    assert resp.status_code == 404


def test_batch_hide_then_processed_combination(tmp_path, monkeypatch):
    """Hidden + processed combination: item can be both hidden and processed."""
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir()
    _write_jsonl(jsonl_dir / "combo_test_full_data.jsonl", [
        _make_record("8001"),
        _make_record("8002"),
    ])

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    # Hide + mark processed in one batch call
    resp = client.patch(
        "/api/results/combo_test_full_data.jsonl/items/batch",
        json={"item_ids": ["8001"], "status": "hidden", "is_processed": True},
    )
    assert resp.status_code == 200
    assert resp.json()["updated_count"] == 1

    # Verify: item is hidden (not in default view)
    get_resp = client.get("/api/results/combo_test_full_data.jsonl")
    items = get_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["商品信息"]["商品ID"] == "8002"

    # With include_hidden: item shows both hidden and processed
    get_resp = client.get("/api/results/combo_test_full_data.jsonl", params={"include_hidden": True})
    items = get_resp.json()["items"]
    item_8001 = next(i for i in items if i["商品信息"]["商品ID"] == "8001")
    assert item_8001["_status"] == "hidden"
    assert item_8001["_is_processed"] is True
    assert item_8001["_hidden_reason"] == "manual"

    # Restore to active — processed flag should persist
    resp = client.patch(
        "/api/results/combo_test_full_data.jsonl/items/batch",
        json={"item_ids": ["8001"], "status": "active"},
    )
    assert resp.status_code == 200

    get_resp = client.get("/api/results/combo_test_full_data.jsonl")
    items = get_resp.json()["items"]
    item_8001 = next(i for i in items if i["商品信息"]["商品ID"] == "8001")
    assert item_8001["_is_processed"] is True  # flag persists after un-hide


def test_export_respects_all_active_filters(tmp_path, monkeypatch):
    """Export endpoint must respect all filter params including processed/contacted/hidden."""
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir()
    _write_jsonl(jsonl_dir / "export_filter_full_data.jsonl", [
        _make_record("9001", title="Processed Item"),
        _make_record("9002", title="Contacted Item"),
        _make_record("9003", title="Plain Item"),
    ])

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    # Mark 9001 as processed, 9002 as contacted
    client.patch("/api/results/export_filter_full_data.jsonl/items/9001/flags", json={"is_processed": True})
    client.patch("/api/results/export_filter_full_data.jsonl/items/9002/flags", json={"is_contacted": True})

    # Export with processed_only → only 9001
    export_resp = client.get("/api/results/export_filter_full_data.jsonl/export", params={"processed_only": True})
    assert export_resp.status_code == 200
    assert "Processed Item" in export_resp.text
    assert "Contacted Item" not in export_resp.text
    assert "Plain Item" not in export_resp.text

    # Export with contacted_only → only 9002
    export_resp = client.get("/api/results/export_filter_full_data.jsonl/export", params={"contacted_only": True})
    assert export_resp.status_code == 200
    assert "Contacted Item" in export_resp.text
    assert "Processed Item" not in export_resp.text

    # Export with hide_processed → 9002 and 9003
    export_resp = client.get("/api/results/export_filter_full_data.jsonl/export", params={"hide_processed": True})
    assert export_resp.status_code == 200
    assert "Contacted Item" in export_resp.text
    assert "Plain Item" in export_resp.text
    assert "Processed Item" not in export_resp.text


def test_selection_state_pruned_after_filter_change_scenario(tmp_path, monkeypatch):
    """
    Simulates the frontend behavior: after fetchResults, selectedItemIds is pruned
    to only include items visible in the current page.
    This tests the backend side — that filtered results correctly exclude items.
    """
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir()
    _write_jsonl(jsonl_dir / "selection_full_data.jsonl", [
        _make_record("A001", title="AI Recommended", recommended=True, source="ai"),
        _make_record("A002", title="Keyword Hit", recommended=True, source="keyword"),
        _make_record("A003", title="Not Recommended", recommended=False, source="ai"),
    ])

    app = FastAPI()
    app.include_router(results.router)
    client = TestClient(app)

    # No filter: all 3 visible
    resp = client.get("/api/results/selection_full_data.jsonl")
    assert resp.json()["total_items"] == 3

    # AI recommended filter: only A001
    resp = client.get("/api/results/selection_full_data.jsonl", params={"ai_recommended_only": True})
    assert resp.json()["total_items"] == 1
    assert resp.json()["items"][0]["商品信息"]["商品ID"] == "A001"

    # Keyword recommended filter: only A002
    resp = client.get("/api/results/selection_full_data.jsonl", params={"keyword_recommended_only": True})
    assert resp.json()["total_items"] == 1
    assert resp.json()["items"][0]["商品信息"]["商品ID"] == "A002"

    # Frontend would prune selectedItemIds to only visible items after each fetch.
    # If user had A001+A002 selected, then switched to ai_recommended_only,
    # only A001 would remain in the visible set.
