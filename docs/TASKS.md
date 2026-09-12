# 量化系统任务交接表

> 供新会话接续：当前基线 = P0/P1/P3 全部落地并推送（`71e5b8f` 之后）。
> 规范：所有量化相关改动必须遵循 `.claude/skills/quant-product-engineer/SKILL.md`。

## 当前系统基线（已完成，勿重做）

| 模块 | 状态 | 关键文件 |
|---|---|---|
| 回测引擎（成本/涨跌停/停牌/T+1/整手） | ✅ 已上线 | data-service/backtest/engine.py |
| 因子检验（IC/分层/衰减/牛熊/行业中性/多维评级） | ✅ 已上线 | data-service/factorlab.py |
| 预测校准层（历史胜率替代 sigmoid 伪概率） | ✅ 已上线 | data-service/predict_calibration.py |
| 模拟盘（每日 17:50 自动调仓+净值跟踪） | ✅ 已上线，2026-09-11 已建仓 | data-service/jobs/paper_trade.py |
| 通知通道（企业微信/钉钉/飞书/raw webhook） | ✅ 已实测 | data-service/notifier.py（env: ALERT_WEBHOOK_URL） |
| 前端因子实验室（双评分/五态/体检/排序切换） | ✅ 已上线 | frontend/src/components/screener/FactorLabPanel.vue |
| 模拟盘面板（净值/持仓/调仓/重置） | ✅ 已上线 | frontend/src/components/screener/PaperPanel.vue |
| 3.5 年历史回补（1015 只 × 659,887 行，2023-03~今） | ✅ 已完成 | 数据库 stock_kline_daily |
| 数据时钟修复（ann_date point-in-time、指数日历） | ✅ 已上线 | data-service/migrations.py |
| 29 策略月度体检（已被周度重跑推翻，见下） | ✅ 已完成 | — |

## 关键结论（新会话勿被旧数字误导）

- **月度 12 期体检的候选名单已被周度 117+ 期重跑推翻**：北向资金追踪（月 ICIR 0.52 → 周 0.068）、缩量企稳（月 -0.52 反向候选 → 周 0.05）。周度低 IC 已排除数据接缝伪影（验证干净）。
- 目前**没有任何策略达到 🟢 有效**（|t|≥2 + 经济≥B + n≥12 + |ICIR|≥0.3）。全部策略需以周度大样本重新出名单。
- 预测概率已改为历史校准胜率（9,400 观测回放），未校准时明确标注"模型评分"。

## 待办任务表

| # | 优先级 | 任务 | 要点/验收标准 | 涉及文件 |
|---|---|---|---|---|
| 0 | 🔴 高 | **P2 性能面板化（原路线图遗留，未开工）** | `_load_ctx`（api/strategies_v2.py）每股 7 次 SQL，全市场评分 3-5 分钟。方案：批量面板加载器 `_bulk_load_panels(codes)` — MySQL 8 窗口函数 `ROW_NUMBER() OVER (PARTITION BY code ORDER BY trade_date DESC)` 取每股前 260 根 K 线、基本面前 12 条、北向/龙虎榜/资金流 60 日窗、stock_info 一把；jobs/strategy_score.py 改为一次加载全内存后循环 `_score_all(ctx)`。目标 <60s。验收：抽 20 只股新旧路径评分一致 + 全市场计时 | api/strategies_v2.py, jobs/strategy_score.py |
| 0 | 🔴 高 | **P4 实盘半自动（原路线图遗留，未开工）** | 里程碑 1（零外部依赖）：委托单生成器 — api/paper.py 加 `GET /api/paper/orders`（最近一个调仓日的 paper_trades → 委托清单：代码/名称/方向/股数/参考价/原因，附目标持仓），前端 PaperPanel 加「生成委托单」卡（表格 + CSV 导出 + 已执行标记 localStorage）。里程碑 2（需券商客户端环境）：`BrokerAdapter` 抽象接口 + EasytraderAdapter（Windows 同花顺 GUI 自动化）与 QMT/PTrade(xtquant)，检测到已安装且显式开启才启用。**安全红线：默认绝不自动下单，半自动 = 生成委托单→人工执行→回填成交；状态流转 待执行→已执行→已回填** | api/paper.py, frontend PaperPanel.vue, 新 broker_adapter.py |

| 1 | 🔴 高 | **收取后台周度体检结果** | 上一窗口的后台进程（host python PID 45556）可能仍在跑，结果落 `data-service/_weekly_sweep.json`（进程结束才写出）；文件不存在则用 UI 体检重跑：调仓频率=周度、窗口 2024-03 起。按五态+评级出终版名单：🟢加权 / 🟡低权观察 / 🟠暂不加权 / ⚪待面板化 / 🔴修复 | — |
| 2 | 🔴 高 | **前端 :80 容器重建** | `docker compose build frontend && docker compose up -d frontend`——当前 :80 还是旧版 UI | frontend/ |
| 3 | 🟡 中 | **复权基准统一（防接缝复发）** | 现状：历史段=腾讯源、每日增量=东财源，基准差异已被整段覆盖掩盖，但每日东财 upsert 只刷前 250 根，约 1 年后 250/800 接缝会重现。根治：改存 hfq 因子或每日对变动股全量重刷 | data-service/jobs/postmarket.py, pipelines/kline.py |
| 4 | 🟡 中 | **夜间评分任务提速** | strategy_score 逐股 5-6 次 SQL（3-5 分钟）→ 批量加载进内存 + 多进程（目标 <60s）；这是全策略体检高频重跑的前置 | data-service/jobs/strategy_score.py, api/strategies_v2.py `_load_ctx` |
| 5 | 🟡 中 | **市值中性化** | stock_info 表有 market_cap（当前快照）；按市值十分位去均值后重算 IC，区分"小票效应"与真选股能力。注意：无历史股本，用当前市值为近似并注明 | data-service/factorlab.py |
| 6 | 🟡 中 | **样本外 + 滚动窗口** | 因子检验加：滚动 60 期 ICIR 曲线、样本外段（前 70% 拟合/后 30% 验证）——补齐稳健性评分的"样本外"分量（当前 robustness 只含牛熊+行业中性） | factorlab.py `_rate` |
| 7 | 🟡 中 | **p 值展示** | 由 t 值算双侧 p（scipy.stats.t.sf），加入 ic_summary 与前端 | factorlab.py, 前端面板 |
| 8 | 🟡 中 | **预测四层拆分**（Skill §5） | 个股预测页重组为 趋势/买点/风险/历史验证 四层；后端 calibration 已就绪，前端 PredictionPanel.vue 重组；相似信号历史表现可复用 predict_calibration 分桶 | frontend/.../PredictionPanel.vue, predictor.py |
| 9 | 🟡 中 | **权重云同步** | 用户自定义策略权重存前端 localStorage → 上服务端；模拟盘与综合评分即可用真实用户权重（当前用注册表默认权重，面板已注明） | frontend/src/stores/strategy.ts, backend 权重接口, jobs/paper_trade.py `_strategy_weights` |
| 10 | 🟢 低 | **指标相关性去重**（Skill §6） | 8 个预测维度相关性矩阵 → 高相关组内降权；产品内说明"综合评分≠独立证据" | predictor.py |
| 11 | 🟢 低 | **部署提醒** | `:80` 前端与 `data-service/backend` 每次改码后需 rebuild；生产推送需配置 `ALERT_WEBHOOK_URL` 环境变量 | docker-compose |

## 验证命令速查

```bash
# 前端构建
cd frontend && npm run build
# Java 编译（本机无 mvn，用 docker）
MSYS_NO_PATHCONV=1 docker run --rm -v "D:/StockAnalysis/backend":/app -w //app maven:3.9-eclipse-temurin-17 mvn -q compile -DskipTests
# 数据服务部署
docker compose build data-service backend && docker compose up -d data-service backend
# 因子检验冒烟（host，需 DB env）
DB_HOST=127.0.0.1 DB_PORT=23307 DB_USER=root DB_PASSWORD=$(docker exec stock-data-service printenv DB_PASSWORD) DB_NAME=stock_screener python - <<EOF
from factorlab import analyze
import datetime as dt
print(analyze("quality_factor", dt.date(2025,9,1), dt.date(2026,9,11))["rating"])
EOF
```

## 已知问题/坑

- 容器内跑 python 脚本用 `docker exec -i`（stdin 要传）；host 直连东财被 TLS 指纹拦截，数据抓取一律在容器内跑
- 文件行尾混用 LF/CRLF——python 补丁脚本用「按行分割 + nl 探测」，锚点断言失败先查行尾
- 后台周度体检结果文件：`data-service/_weekly_sweep.json`（host 进程 cwd = data-service）
- 测试账号 uidemo2026 / Ui#Demo2026!
