# 量化系统任务交接表

> 供新会话接续：当前基线 = P0/P1/P3 + P2 性能面板化 + P4 里程碑1 + 回测引擎 T+1 修复 + AlphaLab 自定义因子 全部落地（2026-09-13）。
> 规范：所有量化相关改动必须遵循 `.claude/skills/quant-product-engineer/SKILL.md`。

## 当前系统基线（已完成，勿重做）

| 模块 | 状态 | 关键文件 |
|---|---|---|
| 回测引擎（成本/涨跌停/停牌/T+1/整手） | ✅ 已上线 | data-service/backtest/engine.py |
| **回测引擎 t+1 开盘执行**（前视修复：t 收盘出信号 → t+1 开盘成交，开盘一字板不可成交；as-of 评分 TTL 缓存 10min；面板加载加预热下界） | ✅ 2026-09-13 | backtest/engine.py `run()` |
| **AlphaLab 自定义因子**（WorldQuant 式截面表达式：rank/zscore/ts_mean/ts_corr/delay/pct_chg 等算子；point-in-time 财务面板；检验与组合回测双入口） | ✅ 2026-09-13 | data-service/alphalab.py、api/alphalab.py、AlphaLabController.java、BacktestPanel.vue 因子模式、FactorLabPanel.vue 自定义因子 |
| **factorlab 统一管线**（`analyze_scores(score_provider)`：内置策略与自定义因子共用 IC/分层/衰减/牛熊/行业中性/评级；宇宙改为日均成交额排序） | ✅ 2026-09-13 | data-service/factorlab.py |
| 因子检验（IC/分层/衰减/牛熊/行业中性/多维评级） | ✅ 已上线 | data-service/factorlab.py |
| 预测校准层（历史胜率替代 sigmoid 伪概率） | ✅ 已上线 | data-service/predict_calibration.py |
| 模拟盘（每日 17:50 自动调仓+净值跟踪） | ✅ 已上线，2026-09-11 已建仓 | data-service/jobs/paper_trade.py |
| 通知通道（企业微信/钉钉/飞书/raw webhook） | ✅ 已实测 | data-service/notifier.py（env: ALERT_WEBHOOK_URL） |
| 前端因子实验室（双评分/五态/体检/排序切换） | ✅ 已上线 | frontend/src/components/screener/FactorLabPanel.vue |
| 模拟盘面板（净值/持仓/调仓/重置） | ✅ 已上线 | frontend/src/components/screener/PaperPanel.vue |
| **P2 批量面板加载器**（5913 只全市场 42.4s；20 只股新旧路径评分一致） | ✅ 2026-09-13 | api/strategies_v2.py `_bulk_load_panels`、jobs/strategy_score.py、/api/v2/screen |
| **P4 里程碑1 委托单生成器**（/api/paper/orders + PaperPanel 委托单卡 + Java 透传；GUI 已验证） | ✅ 2026-09-13 | api/paper.py、PaperController.java、DataService.java、PaperPanel.vue |
| **周度全策略体检终版名单**（29 策略 × 周度 131 期，无 🟢；旧口径=代码序宇宙） | ✅ 2026-09-13 | docs/weekly_sweep_2026-09.md + .json |
| **全站留白治理**（SKILL §34/信息优先：BaseChart/KLineChart/StatGrid/StockHeader 加载骨架 + 空态占位；评分选股进入即自动选股；盘面侧栏 loading 骨架、北向移至末位） | ✅ 2026-09-13 | BaseChart.vue、KLineChart.vue、StatGrid.vue、StockHeader.vue、ScoreScreener.vue、Dashboard.vue、MarketRankCard.vue、theme.css |
| **移动端布局修复**（FactorLabPanel rating-head 移动端断点：评分块对半换行/标题整行下移/metric-line 收窄——修复结果卡横向溢出错位；score-block 补齐样式定义；RefreshBar 窄壳溢出防护） | ✅ 2026-09-13 | FactorLabPanel.vue、RefreshBar.vue |
| 3.5 年历史回补（1015 只 × 659,887 行，2023-03~今） | ✅ 已完成 | 数据库 stock_kline_daily |
| 数据时钟修复（ann_date point-in-time、指数日历） | ✅ 已上线 | data-service/migrations.py |

## 关键结论（新会话勿被旧数字误导）

- **⚠ 宇宙口径已变更（2026-09-13）**：factorlab 的截面宇宙从「按代码排序前 N」改为「日均成交额前 N」（更标准、避免深市偏差）。`docs/weekly_sweep_2026-09` 的旧数字用的是代码序口径，与新口径结果**不可直接对比**；下次全策略体检用新口径重跑后才能更新终版名单。
- **⚠ 回测口径已变更（2026-09-13）**：engine.run() 从「信号日收盘成交」改为「t 收盘信号 → t+1 开盘成交」（修复轻度前视）。历史回测结果整体会略降（尤其高换手策略），这是挤掉水分，不是退化。
- **周度终版名单（旧口径）**：无任何策略达 🟢。🟡 观察：日频动量反转T（反向）；🟠：MAX反向/A股短期反转/RSRS；⚪ 待面板化重测：Magic Formula、行业动量轮动、资金价量背离。详见 docs/weekly_sweep_2026-09.md。
- **AlphaLab 时间语义**：时序算子向后窗口；截面因子值 t 日收盘可知；组合回测 t+1 开盘成交；财务按公告日进入（无未来函数）。无历史市值数据，**不提供市值字段**（防止用当前市值回填历史）。
- 预测概率已改为历史校准胜率（9,400 观测回放），未校准时明确标注"模型评分"。

## 待办任务表

| # | 优先级 | 任务 | 要点/验收标准 | 涉及文件 |
|---|---|---|---|---|
| 0 | 🟡 中 | **全策略周度体检按流动性宇宙重跑** | 宇宙口径已变（代码序→成交额序），旧名单需重跑刷新：UI 全策略体检（周度、2024-03 起）→ 按五态出 v2 名单，与旧名单对比并归档 | FactorLabPanel 全策略体检 |
| 0 | 🟡 中 | **AlphaLab 帮助面板移动端适配** | 字段/算子 popover 宽 380px，小屏可能溢出；检查移动端并收窄 | AlphaExprInput.vue |
| 1 | 🔴 高 | **P4 里程碑2 券商适配（需券商客户端环境，未开工）** | `BrokerAdapter` 抽象接口 + EasytraderAdapter（Windows 同花顺 GUI 自动化）与 QMT/PTrade(xtquant)，检测到已安装且显式开启才启用。**安全红线：默认绝不自动下单；状态流转 待执行→已执行→已回填（里程碑1 已有「已执行」localStorage 标记）** | 新 broker_adapter.py |
| 2 | 🟡 中 | **coverage 类策略重测** | P2 面板化已落地，Magic Formula / 行业动量轮动 / 资金价量背离 三策略原 coverage 不足，用 UI 体检（周度、2024-03 起）重测并更新终版名单 | factorlab.py 体检入口 |
| 3 | 🟡 中 | **🟡/🟠 组策略降频改造** | 日频动量反转T（反向）、MAX 反向、A股短期反转、RSRS：信号平滑/降持仓周期降换手 → 按方向复算成本后净收益 → 复检 t 与经济性，达 🟢 标准才可加权 | factorlab.py、策略注册表 |
| 4 | 🟡 中 | **复权基准统一（防接缝复发）** | 现状：历史段=腾讯源、每日增量=东财源，每日东财 upsert 只刷前 250 根，约 1 年后接缝会重现。根治：改存 hfq 因子或每日对变动股全量重刷 | data-service/jobs/postmarket.py, pipelines/kline.py |
| 5 | 🟡 中 | **市值中性化** | stock_info 有 market_cap（当前快照，无历史）；alphalab 已因无历史市值而排除该字段。做法：按市值十分位去均值后重算 IC，并注明"当前市值为近似" | data-service/factorlab.py |
| 6 | 🟡 中 | **样本外 + 滚动窗口** | 因子检验加：滚动 60 期 ICIR 曲线、样本外段（前 70% 拟合/后 30% 验证）——补齐稳健性评分的"样本外"分量 | factorlab.py `_rate` |
| 7 | 🟡 中 | **p 值展示** | 由 t 值算双侧 p（scipy.stats.t.sf），加入 ic_summary 与前端 | factorlab.py, 前端面板 |
| 8 | 🟡 中 | **预测四层拆分**（Skill §5） | 个股预测页重组为 趋势/买点/风险/历史验证 四层 | frontend/.../PredictionPanel.vue, predictor.py |
| 9 | 🟡 中 | **权重云同步** | 用户自定义策略权重存前端 localStorage → 上服务端 | frontend/src/stores/strategy.ts, backend, jobs/paper_trade.py |
| 10 | 🟢 低 | **指标相关性去重**（Skill §6） | 8 个预测维度相关性矩阵 → 高相关组内降权 | predictor.py |
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
# AlphaLab 冒烟（host）
DB_HOST=127.0.0.1 DB_PORT=23307 DB_USER=root DB_PASSWORD=$(docker exec stock-data-service printenv DB_PASSWORD) DB_NAME=stock_screener python - <<EOF
import alphalab, datetime as dt
r = alphalab.analyze_expr("-pct_chg(close, 20)", dt.date(2026,1,1), dt.date(2026,9,11), rebalance="weekly")
print(r.get("ic_summary"))
b = alphalab.backtest_expr("rank(roe) - rank(debt)", dt.date(2026,1,1), dt.date(2026,9,11), top_n=10, rebalance="monthly")
print(b.get("metrics"))
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
# 回测引擎 t+1 验收：每笔成交价 == 次日开盘价×(1±滑点)，且成交日不是信号日
# （见 2026-09-13 会话：29/29 笔零偏差；评分缓存第二遍省 ~25%）
```

## 已知问题/坑

- 容器内跑 python 脚本用 `docker exec -i`（stdin 要传）；host 直连东财被 TLS 指纹拦截，数据抓取一律在容器内跑
- **容器内测试脚本严禁 `import app`**——app.py 在 import 时就启动调度器；universe 用 `cache.get("spot")`（redis 共享，服务进程已暖）
- **alphalab 与 factorlab 的宇宙必须同源**——两个"前 N"集合若不相交（如代码序 vs 流动性序），覆盖门槛会把所有期数清零（2026-09-13 踩过）；provider 与 codes 一起传给 analyze_scores
- **alphalab.build_panel 已把 K 线/财务面板索引统一为 DatetimeIndex**——K 线原生是 date 对象，不归一则混合表达式（行情×财务）索引对齐全 NaN；新增面板字段时注意
- 文件行尾混用 LF/CRLF——python 补丁脚本用「按行分割 + nl 探测」，锚点断言失败先查行尾
- 前端是 PWA（service worker 预缓存）：rebuild 后第一次 reload 可能仍被旧 SW 控制；验证新 UI 前先注销 SW+清 caches（浏览器 console）或核对资源 hash 与 `frontend/dist/assets` 一致
- **新卡片/图表必须接 loading 骨架**：BaseChart(`loading`/`placeholder`)、KLineChart(`loading`)、StatGrid(`loading`)、StockHeader(`loading`) 都已支持——禁止裸空白渲染（2026-09-13 全站留白治理的约定）
- 评分选股页 `runFilter({ silent: true })` 是进入页面自动跑的静默路径，不带成功/失败 toast；手动按钮仍走带提示路径
- 回测结果受幸存者偏差影响：K 线表只含当前存活 1015 只，绝对收益偏高，横向对比有效； alphalab 回测同理
- 测试账号 uidemo2026 / Ui#Demo2026!
- 周度体检原始结果已归档 `docs/weekly_sweep_2026-09.json`（旧口径=代码序宇宙）

