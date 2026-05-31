# P3-5 Seller-Level Next-Step Design

> 2026-05-30 · 基于 P3-4 seller aggregation 的后续功能评估

## 当前基线

P3-4 已提供 `/api/results/{filename}/sellers` 聚合端点，返回以下 seller 维度的聚合数据：

| 字段 | 来源 | 说明 |
|------|------|------|
| `seller_nickname` | `卖家信息.卖家昵称` → `商品信息.卖家昵称` | 缺失归入"未知卖家" |
| `item_count` | 聚合计数 | 该卖家在当前筛选结果中的商品数 |
| `min_price` / `max_price` | `商品信息.当前售价` | parse_price_value 解析 |
| `latest_crawl_time` | 每条记录的 crawl_time | 最近一次爬取时间 |
| `recommended_count` | `ai_analysis.is_recommended` | AI 推荐的商品数 |
| `personal_seller_summary` | `criteria_analysis.seller_type.persona` | 去重后最多 3 个 persona |

前端 SellersPanel 以静态卡片网格展示所有 seller。

## 每条 result_item 中已有的 seller 相关字段

当前 JSONL 结果记录中，每条 item 包含：

```json
{
  "卖家信息": {
    "卖家昵称": "...",
    "卖家信用等级": "...",
    "卖家好评率": "...",
    "卖家在售商品数": ...,
    "卖家ID": "..."
  },
  "商品信息": {
    "商品ID": "...",
    "商品链接": "...",
    "当前售价": "..."
  },
  "criteria_analysis": {
    "seller_type": {
      "status": "PASS|WARN|FAIL|UNKNOWN",
      "persona": "发烧友, 学生党",
      "analysis_details": {...}
    }
  },
  "id": "item_xxx",
  "status": "active|hidden|expired",
  "is_processed": false,
  "is_contacted": false
}
```

**结论：** 对于读操作（详情页、按卖家筛选结果列表），**不需要 DB schema 变更**——当前 JSONL result records + API 聚合已包含卖家昵称、信用等级、好评率、在售商品数、persona 等核心字段。

## 四个后续方向的评估

### 1. 卖家详情页

**需要什么：** 点击卖家昵称 → 展示该卖家的完整商品列表 + 卖家画像信息。

**能否复用现有字段：** 可以。
- 商品列表：对当前 result items 按 `卖家昵称` 筛选即可（前端或后端添加 query param）
- 卖家画像：聚合多个 item 的 `卖家信息` 字段，取最新/最完整的记录
- 价格历史：可从 `price_history/` 结合该卖家商品 ID 查询

**DB schema：不需要。** 纯读操作，数据来自 JSONL + price_history。

**最小实现（1 个 PR）：**
- 后端：新增 `GET /api/results/{filename}/sellers/{nickname}` 或查询参数 `?seller=昵称` 筛选 items
- 前端：SellersPanel 卖家卡片可点击，展示该卖家商品列表

**复杂度：低。** 主要是路由和筛选逻辑。

### 2. 卖家级隐藏/标记

**需要什么：**
- 批量隐藏某卖家所有商品
- 关注卖家（有新商品时通知）
- 卖家备注（"靠谱卖家"、"二手贩子" 等标签）

**能否复用现有字段：**
- 批量隐藏：可以——批量修改当前结果中该卖家所有 item 的 `status='hidden'`（复用现有 batch update API）
- 关注/备注：**需要新增持久化存储**——这些是跨任务 run 的偏好，不能只存在 JSONL 里

**DB schema：部分需要。**
- 批量隐藏：不需要新 schema（复用 batch update）
- 卖家关注/标记/备注：需要新表（如 `seller_tags`、`seller_watchlist`）或配置文件

**最小实现（1-2 个 PR）：**
- PR1：SellersPanel 增加"批量隐藏该卖家所有商品"按钮（复用 batch PATCH API）
- PR2（如需）：seller watch/备注 → 需要 schema 设计 + 配置存储

**复杂度：中。** PR1 低风险，PR2 需要 schema 决策。

### 3. 卖家对比

**需要什么：** 选择多个卖家并排对比商品数、价格带、推荐率、画像。

**能否复用现有字段：可以。** 聚合 API 已返回每个卖家的 item_count、min/max price、recommended_count、persona。

**DB schema：不需要。** 纯前端展示，数据来自已有聚合 API。

**最小实现（1 个 PR）：**
- SellersPanel 添加多选 checkbox
- 选中 2+ 卖家后显示对比面板（并排展示聚合数据）

**复杂度：低。** 主要是前端 UI 工作，无需后端改动。

### 4. 按卖家筛选

**需要什么：** 在结果列表按卖家昵称筛选。

**能否复用现有字段：可以。** 每条 result item 已有 `卖家信息.卖家昵称`。

**DB schema：不需要。** 可在 query param 添加 `?seller=昵称` 做服务端筛选，或前端本地筛选。

**最小实现（1 个 PR）：**
- 后端：`GET /api/results/{filename}` 添加 `seller` 查询参数
- 前端：SellersPanel 点击卖家 → 过滤结果列表

**复杂度：低。**

## 推荐的最小下一步

按优先级排列：

### PR1（本次实现）：SellersPanel 无 schema 交互改进

**改动范围：** 前端 only，无 schema。

- SellersPanel 添加 top-N 控制：默认展示 6 个卖家，多余可展开/折叠
- 为后续卖家详情/筛选预留交互入口（点击卖家名称可 emit 事件，暂不接后端路由）
- i18n 补齐 showAll / showLess 键

**验证：** `web-ui npm run build`

### PR2（推荐下一步）：卖家详情/筛选轻量路由

**改动范围：** 后端 + 前端，无 schema。

- 后端：`GET /api/results/{filename}?seller=昵称` 查询参数
- 前端：SellersPanel 点击卖家 → ResultsView 自动设置 seller 筛选
- 卖家详情面板：展示信用等级、好评率、在售商品数、persona 等

### PR3（如需）：卖家关注/标记

**改动范围：** 后端 + schema。

- 新增 `seller_tags` 表（或配置文件）存储卖家偏好
- 关注卖家有新商品时通知

## 数据流总结

```
JSONL result items ──→ seller aggregation API ──→ SellersPanel
                              │
                              ├── PR1: top-N 控制 (本次, 无 schema)
                              ├── PR2: seller 筛选 + 详情 (无 schema)
                              └── PR3: 卖家关注/标记 (需 schema)
```

所有读操作（详情、筛选、对比）均可复用现有 result items 字段，**不需要 DB schema**。
只有写操作（关注、备注、持久化规则）需要新增存储。
