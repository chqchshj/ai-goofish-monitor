# Seller Aggregation Contract

> 创建于 P3-4 seller aggregation result view seam，与 `/api/results/{filename}/sellers` endpoint 对应。

## 概述

卖家聚合 API 将当前筛选结果按卖家昵称维度聚合，返回每个卖家的商品数、价格范围、最近发现时间、推荐商品数和个人卖家画像摘要。

## Endpoint

```
GET /api/results/{filename}/sellers
```

### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `filename` | string | 结果文件名（需以 `_full_data.jsonl` 结尾） |

### 查询参数

与 `GET /api/results/{filename}` 完全兼容，支持相同的筛选参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ai_recommended_only` | bool | false | 仅看 AI 推荐 |
| `keyword_recommended_only` | bool | false | 仅看关键词推荐 |
| `include_hidden` | bool | false | 包含已屏蔽结果 |
| `yhb_only` | bool | false | 仅看验货宝 |
| `free_shipping_only` | bool | false | 仅看包邮 |
| `personal_seller_only` | bool | false | 仅看个人卖家 |
| `processed_only` | bool | false | 仅看已处理 |
| `contacted_only` | bool | false | 仅看已联系 |
| `hide_processed` | bool | false | 隐藏已处理 |

### 响应格式

```json
{
  "total_sellers": 3,
  "total_items": 12,
  "sellers": [
    {
      "seller_nickname": "卖家A",
      "item_count": 5,
      "min_price": 800.0,
      "max_price": 3500.0,
      "latest_crawl_time": "2026-05-30T12:00:00",
      "recommended_count": 2,
      "personal_seller_summary": "发烧友, 学生党"
    },
    {
      "seller_nickname": "卖家B",
      "item_count": 4,
      "min_price": 1200.0,
      "max_price": 2800.0,
      "latest_crawl_time": "2026-05-30T11:30:00",
      "recommended_count": 1,
      "personal_seller_summary": null
    },
    {
      "seller_nickname": "未知卖家",
      "item_count": 3,
      "min_price": 500.0,
      "max_price": 1500.0,
      "latest_crawl_time": "2026-05-30T10:00:00",
      "recommended_count": 0,
      "personal_seller_summary": null
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `seller_nickname` | string | 卖家昵称，从 `卖家信息.卖家昵称` 或 `商品信息.卖家昵称` 提取；缺失时显示 "未知卖家" |
| `item_count` | int | 该卖家在当前筛选结果中的商品数量 |
| `min_price` | float or null | 最低价（从 `商品信息.当前售价` 解析），无有效价格时为 null |
| `max_price` | float or null | 最高价，无有效价格时为 null |
| `latest_crawl_time` | string | 最近一次爬取时间（ISO 格式），无记录时为空字符串 |
| `recommended_count` | int | AI 推荐的商品数（`ai_analysis.is_recommended` 为 true 的计数） |
| `personal_seller_summary` | string or null | 个人卖家画像摘要，最多取前 3 个去重后的 persona 描述；仅 AI 分析来源的商品才有此项；关键词命中的商品此项为 null |

### 排序

结果按 `item_count` 降序排列，商品数相同时按 `latest_crawl_time` 降序排列。

### 错误状态

| 状态码 | 说明 |
|--------|------|
| 400 | 文件名非法或参数组合冲突（如同时开启 AI 和关键词推荐） |
| 404 | 结果文件不存在 |
| 500 | 读取结果文件时出错 |

## 聚合逻辑

### 卖家昵称提取

1. 优先取 `卖家信息.卖家昵称`
2. 回退到 `商品信息.卖家昵称`
3. 两者都为空时归入 "未知卖家"

### 价格提取

从 `商品信息.当前售价` 字符串解析，依赖 `src/services/price_history_service.parse_price_value()`。无法解析时跳过。

### 卖家画像提取

仅对 `analysis_source == "ai"` 的记录提取：

1. 优先取 `criteria_analysis.seller_type.persona`
2. 回退到 `criteria_analysis.seller_type.status`
3. 最后尝试 `criteria_analysis.seller_type.analysis_details` 的嵌套 comment

聚合时去重，最多保留 3 个，以逗号分隔。

## 安全约束

- 只读操作，不修改任何数据
- 复用 `load_all_result_records` 享受与结果列表相同的筛选和访问控制
- 不新增 schema 迁移，不写入数据库

## 后续 seller-level 操作建议

以下是基于当前聚合视图可以扩展的方向，按优先级排列：

### P3-5: 卖家详情页

- 点击聚合摘要中的卖家昵称，跳转到卖家详情页
- 展示该卖家的所有商品列表（复用现有筛选参数）
- 展示卖家画像详情（信用等级、好评率、在售商品数等）
- 展示该卖家的价格历史趋势

### P3-6: 卖家级操作

- 批量屏蔽卖家所有商品
- 关注卖家（seller watch），有新商品时通知
- 卖家备注（手动标注标签如"靠谱卖家"、"二手贩子"）

### P3-7: 卖家对比视图

- 选择多个卖家进行并排对比
- 对比维度：商品数、价格带、推荐率、画像

### 数据依赖

这些功能需要较完整的卖家画像数据：
- `卖家信息` 字段（信用等级、评价数、在售商品数等）
- AI 分析的 `criteria_analysis.seller_type`
- 价格历史数据（`price_history/`）

当前聚合 API 已提供基础数据，可作为上述功能的查询入口。
