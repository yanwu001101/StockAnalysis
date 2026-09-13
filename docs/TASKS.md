# 量化系统任务交接表

> 供新会话接续：当前基线 = P0/P1/P3 + P2 性能面板化 + P4 里程碑1（委托单生成器）全部落地（2026-09-13）。
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
| **P2 批量面板加载器**（5913 只全市场 42.4s，旧路径 69s/冷环境 3-5min；20 只股新旧路径评分一致） | ✅ 2026-09-13 | api/strategies_v2.py `_bulk_load_panels`、jobs/strategy_score.py、/api/v2/screen |
| **P4 里程碑1 委托单生成器**（/api/paper/orders 只读清单 + PaperPanel 委托单卡 + Java 透传；GUI 已验证） | ✅ 2026-09-13 | api/paper.py、PaperController.java、DataService.java、PaperPanel.vue |
| **周度全策略体检终版名单**（29 策略 × 周度 131 期，无 🟢） | ✅ 2026-09-13 | docs/weekly_sweep_2026-09.md + .json |
| 3.5 年历史回补（1015 只 × 659,887 行，2023-03~今） | ✅ 已完成 | 数据库 stock_kline_daily |
| 数据时钟修复（ann_date point-in-time、指数日历） | ✅ 已上线 | data-service/migrations.py |

## 关键结论（新会话勿被旧数字误导）

- **周度终版名单已出（2026-09-13，勿再引用月度 12 期数字）**：无任何策略达 🟢（最高 |t|=1.78）。🟡 观察：日频动量反转T（反向）；🟠 暂不加权：MAX 反向、A股短期反转、RSRS（换手 el≈632 成本黑洞）；⚪ 待面板化重测：Magic Formula、行业动量轮动、资金价量背离；其余 22 个无证据。详见 docs/weekly_sweep_2026-09.md。
- 月度体检的候选名单已被周度大样本推翻：北向资金追踪（月 ICIR 0.52 → 周 0.068）、缩量企稳（月 -0.52 → 周 0.05）。
- 预测概率已改为历史校准胜率（9,400 观测回放），未校准时明确标注"模型评分"。

## 待办任务表

| # | 优先级 | 任务 | 要点/验收标准 | 涉及文件 |
|---|---|---|---|---|
| 0 | 🔴 高 | **P4 里程碑2 券商适配（需券商客户端环境，未开工）** | `BrokerAdapter` 抽象接口 + EasytraderAdapter（Windows 同花顺 GUI 自动化）与 QMT/PTrade(xtquant)，检测到已安装且显式开启才启用。**安全红线：默认绝不自动下单；状态流转 待执行→已执行→已回填（里程碑1 已有「已执行」localStorage 标记）** | 新 broker_adapter.py |
| 1 | 🟡 中 | **coverage 类策略重测** | P2 面板化已落地，Magic Formula / 行业动量轮动 / 资金价量背离 三策略原 coverage 不足，用 UI 体检（周度、2024-03 起）重测并更新终版名单 | factorlab.py 体检入口 |
| 2 | 🟡 中 | **🟡/🟠 组策略降频改造** | 日频动量反转T（反向）、MAX 反向、A股短期反转、RSRS：信号平滑/降持仓周期降换手 → 按方向复算成本后净收益 → 复检 t 与经济性，达 🟢 标准才可加权 | factorlab.py、策略注册表 |
| 3 | 🟡 中 | **复权基准统一（防接缝复发）** | 现状：历史段=腾讯源、每日增量=东财源，基准差异已被整段覆盖掩盖，但每日东财 upsert 只刷前 250 根，约 1 年后 250/800 接缝会重现。根治：改存 hfq 因子或每日对变动股全量重刷 | data-service/jobs/postmarket.py, pipelines/kline.py |
| 4 | 🟡 中 | **市值中性化** | stock_info 表有 market_cap（当前快照）；按市值十分位去均值后重算 IC，区分"小票效应"与真选股能力。注意：无历史股本，用当前市值为近似并注明 | data-service/factorlab.py |
| 5 | 🟡 中 | **样本外 + 滚动窗口** | 因子检验加：滚动 60 期 ICIR 曲线、样本外段（前 70% 拟合/后 30% 验证）——补齐稳健性评分的"样本外"分量（当前 robustness 只含牛熊+行业中性） | factorlab.py `_rate` |
| 6 | 🟡 中 | **p 值展示** | 由 t 值算双侧 p（scipy.stats.t.sf），加入 ic_summary 与前端 | factorlab.py, 前端面板 |
| 7 | 🟡 中 | **预测四层拆分**（Skill §5） | 个股预测页重组为 趋势/买点/风险/历史验证 四层；后端 calibration 已就绪，前端 PredictionPanel.vue 重组；相似信号历史表现可复用 predict_calibration 分桶 | frontend/.../PredictionPanel.vue, predictor.py |
| 8 | 🟡 中 | **权重云同步** | 用户自定义策略权重存前端 localStorage → 上服务端；模拟盘与综合评分即可用真实用户权重（当前用注册表默认权重，面板已注明） | frontend/src/stores/strategy.ts, backend 权重接口, jobs/paper_trade.py `_strategy_weights` |
| 9 | 🟢 低 | **指标相关性去重**（Skill §6） | 8 个预测维度相关性矩阵 → 高相关组内降权；产品内说明"综合评分≠独立证据" | predictor.py |
| 10 | 🟢 低 | **部署提醒** | `:80` 前端与 `data-service/backend` 每次改码后需 rebuild；生产推送需配置 `ALERT_WEBHOOK_URL` 环境变量 | docker-compose |

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
# P2 批量加载器一致性验收（host，抽 20 只股新旧路径评分必须一致）
DB_HOST=127.0.0.1 DB_PORT=23307 DB_USER=root DB_PASSWORD=$(docker exec stock-data-service printenv DB_PASSWORD) DB_NAME=stock_screener python - <<EOF
from api.strategies_v2 import _load_ctx, _bulk_load_panels, _score_all
from repo import base
eng = base.engine()
with eng.connect() as conn:
    rows = conn.exec_driver_sql("SELECT code FROM stock_kline_daily GROUP BY code ORDER BY RAND() LIMIT 20").fetchall()
codes = [r[0] for r in rows]
panels = _bulk_load_panels(codes)
for c in codes:
    old_r = _score_all(_load_ctx(c)); new_r = _score_all(panels[c])
    assert old_r[0] == new_r[0] and old_r[1] == new_r[1], c
print("PARITY OK")
EOF
# P2 全市场计时（容器内跑，勿 import app——会拉起调度器；spot 缓存经 redis 共享）
docker exec stock-data-service python -c "import time, jobs.strategy_score as ss; t=time.time(); ss.run(); print('elapsed', round(time.time()-t,1),'s')"
# 委托单接口冒烟（需登录 token；或容器内 Flask test_client 直测 bp）
curl -s "http://localhost:18080/api/paper/orders" -H "Authorization: Bearer $TOKEN"
```

## 已知问题/坑

- 容器内跑 python 脚本用 `docker exec -i`（stdin 要传）；host 直连东财被 TLS 指纹拦截，数据抓取一律在容器内跑
- **容器内测试脚本严禁 `import app`**——app.py 在 import 时就启动调度器，会拉起重复后台任务；universe 用 `cache.get("spot")`（redis 共享，服务进程已暖）
- 文件行尾混用 LF/CRLF——python 补丁脚本用「按行分割 + nl 探测」，锚点断言失败先查行尾
- 前端是 PWA（service worker 预缓存）：rebuild 后第一次 reload 可能仍被旧 SW 控制，验证新 UI 前先确认资源 hash（`document.querySelectorAll("script[src]")`）与 `frontend/dist/assets` 一致
- 测试账号 uidemo2026 / Ui#Demo2026!
- 周度体检原始结果已归档 `docs/weekly_sweep_2026-09.json`（原 data-service/_weekly_sweep.json 运行时产物已清理）
