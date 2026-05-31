# Repository Guidelines

## 项目结构与模块组织
- 后端位于 `src/`，入口 `src/app.py`，API 路由在 `src/api/routes/`，服务层在 `src/services/`，领域模型在 `src/domain/`，基础设施在 `src/infrastructure/`。
- 前端在 `web-ui/`（Vue 3 + Vite），视图放于 `web-ui/src/views/`，组件在 `web-ui/src/components/`，构建产物会复制到根目录 `dist/`。
- 测试位于 `tests/`，命名遵循 `test_*.py` 或 `tests/*/test_*.py`。
- 运行数据与资源：`prompts/`、`jsonl/`、`logs/`、`images/`、`static/`、`state/`，配置文件 `config.json` 与 `.env` 位于仓库根目录。

## 构建、测试与本地开发
- 后端开发：`python -m src.app` 或 `uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload`。
- 爬虫任务：`python spider_v2.py --task-name "MacBook Air M1" --debug-limit 3`（可用 `--config` 指定自定义配置）。
- 前端开发：`cd web-ui && npm install && npm run dev`；构建：`cd web-ui && npm run build`（产物复制到根目录 `dist/`）。
- 一键本地启动：`bash start.sh`（自动安装依赖、前端构建并启动后端）。
- Docker：`docker compose up --build -d`，查看日志 `docker compose logs -f app`，停止 `docker compose down`。

## 编码风格与命名约定
- 保持分层：API → services → domain → infrastructure，避免跨层耦合，模块保持精简。
- Python 测试函数命名为 `test_*`，文件与路径遵循上述测试目录规范。
- 使用描述性、任务导向的命名（如爬虫任务名、配置键），与业务含义对应。

## 架构与运行时
- 后端使用 FastAPI 提供 API 与静态资源，爬虫与 AI 推理在独立任务进程中协作，前后端通过 HTTP/Web UI 交互。
- 任务运行会在 `jsonl/` 写入结果、在 `logs/` 留存运行日志、在 `images/` 下载图片，前端监控页面依赖这些数据。
- 默认监听 8000 端口，前端构建后静态文件可由后端或 Docker 镜像直接提供。

## 测试指南
- 测试框架：`pytest`（默认同步测试，无需 `pytest-asyncio`）。
- 运行全部测试：`pytest`；覆盖率：`pytest --cov=src` 或 `coverage run -m pytest`；定向测试：`pytest tests/test_utils.py::test_safe_get`。
- 优先覆盖核心服务、爬虫管道的异常分支与重试逻辑，避免回归。
- PR 前请运行相关测试，新增逻辑补充针对性用例。

## 提交与 PR 规范
- Commit 采用类 Conventional Commits：`feat(...)`、`fix(...)`、`refactor(...)`、`chore(...)`、`docs(...)` 等。
- PR 需说明变更范围与影响模块；UI 变更在 `web-ui/` 提供截图；关联相关 Issue；提及配置或迁移步骤。

## 安全与配置提示
- 复制 `.env.example` 为 `.env`，设置必填项 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL_NAME` 等。
- 不要提交真实凭据或 cookies（如 `state.json`）；Playwright 需本地浏览器，Docker 镜像已预装 Chromium。
- Web 认证默认 `admin/admin123`，生产环境务必修改，推荐启用 HTTPS 并限制访问来源。

## P4-1 通知降噪契约（2026-05 起）

通知策略由 `src/services/notification_filter.py` 与 `src/services/result_pipeline_service.py` 共同维护，作为可演进的 seam：

- 决策入口：`evaluate_notification(record, policy, dedup_store, seller_throttle_store, now)` —— 纯函数，决定一条已被 AI 标记 `is_recommended=True` 的记录是否真的发送通知。
- 评分启发式：从 `criteria_analysis.<field>.status`（PASS/WARN/FAIL/UNKNOWN）求平均权重，再按 `risk_tags` 数量线性扣分，归一到 0..100；映射 low(<50) / medium(50-79) / high(>=80)。等 AI 输出原生 `recommendation_score` 字段时，可通过 `NotificationPolicy.scorer` 注入新打分函数，无需改 seam。
- 去重：`InMemoryDedupStore` 进程内 TTL，按 `商品ID > 规范化商品链接`（去 query/fragment）生成 key；不持久化、重启即清空（P4-1 不写生产 DB）。
- 卖家限流（P4-3）：`InMemoryDedupStore`（独立实例），按 `seller_id > 卖家信息.卖家ID > 卖家昵称 > 卖家主页` 推导 seller key；缺失全部卖家字段时 seller throttle 自动放行（不影响 item dedup）。seller throttle 与 item dedup 完全独立 —— 同卖家不同商品各发一次，同商品同卖家只发一次。
- 配置入口（env-only，刻意不出现在 `/settings/notification`）：
  - `NOTIFICATION_MIN_SCORE`：浮点阈值，留空=不过滤。
  - `NOTIFICATION_MIN_LEVEL`：`low|medium|high`，留空=不过滤。
  - `NOTIFICATION_DEDUP_WINDOW_SECONDS`：>0 时启用去重。
  - `NOTIFICATION_SELLER_THROTTLE_WINDOW_SECONDS`（P4-3）：>0 时启用以 seller 为维度的短窗口限流。
- 默认行为：未配置任何字段时，`ResultPipelineService` 行为与 P3 时期完全一致——`is_recommended=True` 即通知，否则不通知。
- 仅作用范围：影响 AI 推荐链路（`ResultPipelineService._notify_if_recommended`）；任务暂停/失败告警（scraper.py / process_service.py）继续走原通道，不受降噪影响。
- 切换平滑：`evaluate_notification` 在 inert 策略下仍会 `dedup_store.mark` 和 `seller_throttle_store.mark`，避免运维启用窗口的瞬间把历史 key 全部重发。
- 运维启用顺序、风险与回滚步骤见 `docs/runbooks/notification-throttle-ops.md`（不在本契约范围内，文档单独维护）。
