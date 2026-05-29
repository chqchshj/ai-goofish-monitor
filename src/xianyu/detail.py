from src.utils import format_registration_days, safe_get


async def enrich_item_from_detail(item_data: dict, detail_json: dict) -> dict:
    item_do = await safe_get(detail_json, "data", "itemDO", default={})
    seller_do = await safe_get(detail_json, "data", "sellerDO", default={})

    reg_days_raw = await safe_get(seller_do, "userRegDay", default=0)
    registration_duration_text = format_registration_days(reg_days_raw)
    zhima_credit_text = await safe_get(seller_do, "zhimaLevelInfo", "levelName")

    image_infos = await safe_get(item_do, "imageInfos", default=[])
    if image_infos:
        all_image_urls = [img.get("url") for img in image_infos if img.get("url")]
        if all_image_urls:
            item_data["商品图片列表"] = all_image_urls
            item_data["商品主图链接"] = all_image_urls[0]

    item_data["“想要”人数"] = await safe_get(
        item_do,
        "wantCnt",
        default=item_data.get("“想要”人数", "NaN"),
    )
    item_data["浏览量"] = await safe_get(item_do, "browseCnt", default="-")
    user_id = await safe_get(seller_do, "sellerId")

    return {
        "item_data": item_data,
        "seller_do": seller_do,
        "user_id": user_id,
        "zhima_credit_text": zhima_credit_text,
        "registration_duration_text": registration_duration_text,
    }
