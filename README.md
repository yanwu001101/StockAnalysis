# AlphaForge — AI 驱动的 A 股量化终端

多智能体（LangGraph）负责定性推理，回测引擎负责定量计算；两者严格分离——
**所有数字都是确定性的，大模型只负责把数字讲成人话**。

前端是**专业量化终端（Bloomberg / TradingView 式工作区）**，不是后台管理系统：
图标导航条 + 全局顶栏 + Ctrl/⌘+K 命令面板 + 四个多面板工作区，路由切换不重绘框架。

```
┌────────────────────────────────────────────────────────────────────────┐
│ Vue 3 终端（暗黑金融风 #0A0E14 / #0E1116 / #1E242C）                     │
│  IconRail ─ TopBar(全局搜索·AI信息流·系统状态) ─ 命令面板(Ctrl/⌘+K)       │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐              │
│  │ /command-   │ /analysis/  │ /backtest   │ /watchlist  │              │
│  │ center 驾驶舱│ :symbol 工作台│ 回测实验室  │ 雷达监控    │              │
│  └─────────────┴─────────────┴─────────────┴─────────────┘              │
└──────────┬─────────────────────────────────────┬───────────────────────┘
           │ REST (CQRS)                         │ WebSocket 进度流
           ▼                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ FastAPI（六边形架构：api → services → domain ← infrastructure）           │
│   POST /api/v1/analyze ──► AnalysisCommandService ──► asyncio 任务       │
│   GET  /api/v1/result/{id} ──► AnalysisQueryService                      │
│   GET  /api/v1/stats · /api/v1/market/overview ──► 驾驶舱                 │
│   WS   /ws/v1/progress/{id} ──► ConnectionManager + Redis 总线            │
│                                                                         │
│   LangGraph StateGraph（9 节点，多空辩论 1-3 轮）                         │
│     data_ingestion → fundamental → sentiment_analyst                     │
│       → technical_analyst → bull ⇄ bear(×N) → risk_manager               │
│       → decision(确定性回测) → translation(人话翻译)                       │
│                                                                         │
│   回测引擎（纯函数，无未来函数）：                                         │
│     佣金万三(最低¥5) / 印花税0.1%(卖出) / 过户费0.002%(沪市)               │
│     整手100股 / T+1 / 滑点0.1% / 涨跌停约束 / 前复权(qfq)                  │
└──────────┬──────────────────────┬─────────────────────┬───────────────┘
           ▼                      ▼                     ▼
      AkShare(行情/基本面/新闻)   Redis(缓存+WS总线)   MongoDB(任务持久化)
```

## 快速开始

```bash
cp .env.example .env          # 占位配置；无需任何密钥即可运行
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端终端 | http://localhost:8080 |
| 后端 API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health · /ready |

默认 `LLM_PROVIDER=heuristic`（确定性规则引擎，离线可复现）；配置
`LLM_PROVIDER=openai` + `LLM_API_KEY` 后，定性文本改由 OpenAI 兼容端点生成，
**数值永远不走 LLM**。

### 本地开发（不用 Docker）

```bash
# 后端（Python 3.11）
cd backend
pip install -r requirements.txt
DATA_PROVIDER=synthetic PERSISTENCE=memory CACHE_BACKEND=memory \
  uvicorn app.main:app --reload

# 前端
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 与 /ws 已配置代理
```

`DATA_PROVIDER=synthetic` 使用内置的确定性合成行情，无网络也能跑通全链路
（测试即依赖此模式）。生产环境用默认 `akshare`。

## 终端操作指南

| 操作 | 效果 |
| --- | --- |
| `Ctrl/⌘ + K` | 命令面板：搜股票、跳转工作区、输入 6 位代码直接分析 |
| 顶栏搜索框回车 | 进入分析工作台并立即发起分析 |
| 点击 K 线任意一天 | 左侧「当日检视」与右侧面板联动（OHLC + 当日信号 + AI 快照） |
| 面板右上角 －/＋ | 折叠/展开任意面板，布局不塌陷 |
| 驾驶舱右侧预警 | 点击股票代码直接滑入分析 |

四个工作区：**驾驶舱**（宏观数据卡 · 智能体状态 · AI 预警抽屉）、
**智能分析工作台**（25% Agent 进度 + 75% K线/Tab 结论/辩论回放/专业指标）、
**回测实验室**（策略配置覆盖资金/费率/滑点/日期窗口 → 资金曲线 + 成交流水 + AI 归因）、
**雷达监控**（自选股 AI 评分变动 + 实时异动日志）。

## 测试

```bash
cd backend  && python -m pytest        # 43 个用例：回测规则/无未来函数/指标/翻译/图/API
cd frontend && npx vitest run          # 25 个用例：mapper 阈值/选择器/Store WS 状态机
cd frontend && npm run typecheck       # vue-tsc 全量严格类型检查
```

## 架构决策

| 决策 | 理由 |
| --- | --- |
| 六边形架构（端口在 domain，适配器在 infrastructure/services） | 回测引擎与领域规则不依赖 AkShare/Redis/Mongo，可离线单测 |
| CQRS（命令服务建任务，查询服务读结论） | 写入路径（图执行）与读取路径（轮询/WS）可独立扩展 |
| LangGraph TypedDict 状态 + 依赖注入（GraphDeps） | 节点是纯函数 `state → partial-state`，测试不需要 mock 框架 |
| 节点名与状态键解耦（`sentiment_analyst` ≠ `sentiment`） | LangGraph 禁止节点名与状态通道同名，否则启动即报错 |
| 数值确定性、LLM 只做定性（辩论±15 分封顶） | 换 prompt 不会偷偷改写回测结果 |
| 指标不可计算时以 `metricStatus` 声明，而非伪造 0 | 前端能看到"数据不足"，不会把 0 当成真实收益 |
| 线缆前缀 camelCase（Pydantic `serialization_alias`） | 与 `frontend/src/types/quant.d.ts` 1:1 对齐 |
| 工作区模式（SPA + 图标导航 + 命令面板） | 专业终端交互范式，避免后台式页面跳转 |
| 回测参数经请求覆盖（BacktestOverrides） | 回测实验室与主分析共用同一引擎，不存在第二套计算逻辑 |

## 目录

```
backend/app/
  main.py                 FastAPI 工厂：日志/CORS/错误处理/lifespan
  config.py               全部环境变量集中校验（Pydantic Settings）
  api/                    routes.py（REST）· websocket.py（WS）· deps.py（组合根）
  domain/                 models.py（契约+值对象）· ports.py（端口）· errors.py · results.py
  agents/                 state.py · graph.py（StateGraph）· runner.py · nodes/（9 节点）
  services/               backtest_engine.py · metrics.py · signal_rule.py · indicators.py
                          data_fetcher.py（AkShare 适配器+缓存装饰器+合成源）
                          verdict.py（翻译策略）· ws_manager.py · analysis_service.py
                          llm_factory.py（heuristic / openai 双实现）
  infrastructure/         redis_client.py（缓存+WS 总线）· mongo_client.py（任务仓储）
  tests/                  pytest 套件 + WS 冒烟客户端
frontend/src/
  types/quant.d.ts        与后端 1:1 的线缆契约
  services/quantApi.ts    类型化 fetch 封装（4xx 不重试，5xx 退避重试）
  stores/                 useAnalysisStore（WS 状态机）· useWorkspaceStore（自选/预警/面板）
  utils/                  selectors.ts（日期联动/曲线/流水/命令过滤，纯函数）· mappers/quant-vm.ts
  views/                  GlobalShell · CommandCenterView · AnalysisWorkspace · BacktestLabView · WatchlistView
  components/             IconRail · TopBar · CommandPalette · PanelFrame · AgentProgressPanel
                          QuantVerdict · CandleChart（点击联动）· DayInspector · DebateReplay
                          TradeTable · EquityCurveChart
docker-compose.yml        backend + frontend + redis + mongo
```

## API 约定

- `POST /api/v1/analyze` body `{"symbol":"600519","backtest":{...可选覆盖}}` → `201 {taskId, symbol, status}`
- `GET /api/v1/result/{taskId}` → `QuantVerdictPayload`（未完成时 `409 TASK_NOT_READY`）
- `GET /api/v1/tasks/{taskId}` → 任务状态（调试/轮询用）
- `GET /api/v1/stats` → 智能体舰队统计；`GET /api/v1/market/overview` → 基准指数 + 涨跌家数（不可用时为 null）
- `WS /ws/v1/progress/{taskId}` → `WsEnvelope{type: progress|verdict|heartbeat|error}`

错误统一为 `{"error":{"code","message"}}`；领域错误带自己的 HTTP 状态码，
未预期异常只返回 500 且不泄露堆栈。

## 已知边界

- 情绪面为关键词极性打分（确定性），接入真实 LLM 后仅改写措辞；
- 未建模 ST 5% 涨跌停（免费数据源无可靠 ST 标记）；
- 单 worker 部署时 WS 总线退化为进程内广播（多 worker 需 Redis）；
- 当日检视中的「AI 快照」是本次分析总结论，非当日生成（后端不存历史逐日推理）。
