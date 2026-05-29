import asyncio

from src.xianyu.detail import enrich_item_from_detail


def test_enrich_item_from_detail_applies_detail_fields() -> None:
    item = {
        "商品标题": "iPad Pro",
        "商品主图链接": "old",
        "“想要”人数": "3",
    }
    detail_json = {
        "data": {
            "itemDO": {
                "imageInfos": [
                    {"url": "https://example.com/1.jpg"},
                    {"url": ""},
                    {"url": "https://example.com/2.jpg"},
                ],
                "wantCnt": 8,
                "browseCnt": 120,
            },
            "sellerDO": {
                "sellerId": "seller-1",
                "userRegDay": 400,
                "zhimaLevelInfo": {"levelName": "优秀"},
            },
        }
    }

    result = asyncio.run(enrich_item_from_detail(item, detail_json))

    assert result["item_data"] is item
    assert item["商品图片列表"] == [
        "https://example.com/1.jpg",
        "https://example.com/2.jpg",
    ]
    assert item["商品主图链接"] == "https://example.com/1.jpg"
    assert item["“想要”人数"] == 8
    assert item["浏览量"] == 120
    assert result["seller_do"]["sellerId"] == "seller-1"
    assert result["user_id"] == "seller-1"
    assert result["zhima_credit_text"] == "优秀"
    assert result["registration_duration_text"].startswith("来闲鱼1年")


def test_enrich_item_from_detail_preserves_existing_want_default() -> None:
    item = {"“想要”人数": "existing"}

    result = asyncio.run(enrich_item_from_detail(item, {"data": {"itemDO": {}}}))

    assert result["item_data"]["“想要”人数"] == "existing"
    assert result["item_data"]["浏览量"] == "-"
    assert result["seller_do"] == {}
    assert result["user_id"] == "暂无"
    assert result["zhima_credit_text"] == "暂无"
    assert result["registration_duration_text"] == "未知"
