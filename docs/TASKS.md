# 量化系统任务清单

> 更新：2026-10-13。本页分开记录「源码已修」「本地已验证」「生产待验」，不把三者混写成已上线。
> 所有量化改动遵循 `.claude/skills/quant-product-engineer/SKILL.md`：数据/计算正确性优先，不以缺失值冒充 0，不用新功能掩盖旧数据问题。
> 本轮未触发真实下单、模拟盘调仓、生产回填或容器重启；历史策略收益没有重新跑测，不能据此更新权重。

## 本轮已修复（2026-10-12～13，源码）

- **数据刷新 D1**：`scheduler.warmup_klines()` 对非空 DataFrame 做 `not frame` 导致首批后中止；改为明确判断 None/empty，51/101 只合成宇宙验证全部批次、缺键/None/空帧 fallback。
- **复权写入 D2**：`get_daily()` 提前裁掉重叠段导致所有增量都被 adjustment_guard 拒绝；保留重叠锚点。同步读穿透、定时日/周线和异步 fallback 对需重定基股票重拉完整历史一次。源仍截断/失败时保留旧序列与待刷标志，绝不猜因子缩放。
- **执行可信性 Q1**：单股择时由 t 日收盘成交改为 t 收盘信号、下一市场交易日开盘成交；停牌/缺棒/开盘涨跌停不成交，陈旧订单不顺延；期末保留持仓估值，不制造强平。
- **共享评分 Q3**：`_score_at/_score_at_cached` 与单股共用可用性解析；no_data/insufficient_data/no_lhb/no_rank 占位分与异常、非有限分均排除，真实 0 保留为观测；因子 provider 不再把失败算样本。`ENGINE_VERSION=factorlab-2026-10-12-v4` 使旧挖掘缓存失效，历史检验需要重跑。
- **费用 Q2**：单股现金、成交金额、买卖佣金、印花税、净盈亏可复算；无平仓样本胜率为 null。共享整手预算同时修复组合回测最低佣金导致负现金的问题。
- **研究队列 R1**：仅清理 DONE/FAILED，结果 TTL 自完成起算；运行/排队不被 40 份结果上限挤掉。最多 8 个未完成任务（2 个 worker），满载返回 429 + Retry-After，线程池拒绝不留幽灵 QUEUED；轮询也执行过期清理。
- **接口契约 R2**：Java 三个回测入口共用 BacktestResultMapper；业务失败不会被扁平化吞掉，missing/non-finite 不补 0，保留原始 metrics/执行/样本元数据；研究接口保留上游可操作错误信息。
- **页面 U1**：回测 loading/error/insufficient/partial 状态分开；新任务立即清旧结果，保存绑定提交时参数快照；null 显示「—」，真实 0 保留，展示未平仓与执行口径。
- **预测 U2**：未校准显示 `/100` 评分而非涨跌概率；历史频率与未来概率分离，校准缺值不变 0，数据不足时隐藏旧 50/50 占位分。
- **任务结果 D3**：盘后/周末返回版本化 outcome；零写入/全源失败为 failed，部分管线异常或零写入为 partial，周末明确 skipped。旧任务 None/全表行数为 unknown，不再无异常即成功。股票池统一 0=全市场、去重、活跃过滤。admin 最多 2 个运行任务，同名拒绝，活跃记录不被历史清理；400/409/429/503 两套 Java 入口均透传，启动失败不留幽灵任务。
- **数据监控 D4**：历史覆盖与参考期覆盖拆开，99 旧+1 新显示 1%；周线按周、事件/报告期不按每日全市场判断。提供分母来源、滞后/无历史、最新记录字段非空覆盖、进程内待重定基列表。参考日来自库内已观测日并显示日历未验证/日历滞后，不能声称全库已追平市场。
- **汇总统计 Q4**：空/单观测、非有限/缺失净值、未定义夏普/Calmar 输出 null+原因，真实零保留；基准按策略实际日期端点对齐，曲线缺口不填。胜率明确 CLOSED_TRADES 或 EQUITY_UP_PERIODS 及样本 n；单股无平仓不回退上涨日口径。回测/模拟盘展示消费同一证据状态，模拟盘读取错误与未启动分离。
- **管理端 U4**：健康未加载不假报断线；任务成功/部分完成/失败/跳过/未验证分开；任务步骤和报告写入行数可展开，运行中自动轮询，卸载停止，提交与历史刷新竞态补查。主应用设置页同样适配新状态与轮询失败重试。
- **研究任务隔离 R3a**：所有者取自 Java 登录身份，签名绑定 owner/时间/方法/路径/实际 UTF-8 请求体；Python 验签再入队或查询，跨用户/不存在/旧无 owner 统一 404，完整 UUID 防碰撞。两端需要相同且非默认的 `JWT_SECRET`，缺配置明确 503，绝不回退裸 owner 或共享账号；见 `docs/research-job-auth.md`。不包含任务持久化或取消。
- **测试基线 T1**：修正新浪资金流测试 fixture：真实接口以 num 控制深度、忽略 page1，不再用虚构分页行为测试正确实现。新增 `data-service/requirements-dev.txt`，测试环境为根目录隔离 `.venv`。

## 活跃待办（按收益与风险排序）

| ID | 优先级 / 状态 | 任务 | 验收标准 / 代码入口 |
|---|---|---|---|
| D6 | P1 待补 | 独立交易日历、维护任务结果与守卫持久化 | D4 仅库内参考日，不是独立市场日历；D3 的行数是管线报告 upsert 总数，不证明每只股票更新成功。补逐股票失败汇总；迁移盘前/盘中/strategy_score 到 outcome；任务/复权标志持久化，跨 worker 与调度/手工入口互斥。 |
| Q5 | P1 待补数据 | point-in-time 股票池/市值/财报版本 | Magic Formula 缺历史市值/EV，历史检验保持不可用；不得用当前市值回填历史或声称近似无前视。市值中性化等历史数据完整后再实现。现有活跃股池仍有幸存者偏差，财报截止日兜底也非原始披露证据。 |
| R3 | P1 部分完成 | 长任务恢复与取消 | R3a 所有者隔离已修。队列仍是单进程内存，重启会丢；前端 15 分钟超时不会停止后台。下一步持久化 job id/owner/status、断线续查、幂等提交、取消与超时释放资源。异步化不是性能优化。 |
| P1 | P1 待优化 | as-of 面板切片与截面缓存 | 保持时间语义不变；预排序后二分切片、共享截面分数缓存。测冷/热耗时、峰值内存、每次调仓分数与旧正确基准一致，不以全期数据预选替代历史宇宙。 |
| Q6 | P1 待重跑 | 周度名单与降频研究 | 在 D3/D4 修复并确认覆盖后，以同 ENGINE_VERSION、同截止日/股票池重跑；保存参数、raw/normalized、train/test、成本、样本。旧 #2/#3 不再把已撤销的候选默认当有效因子。 |
| U3 | P2 部分完成 | 预测四层 UI 与证据去重 | 模型诊断已有评分/频率/风险拆分，本轮修语义；仍需完整趋势/买点/风险/历史验证布局与相关指标组内去重，不显示伪概率。 |
| D5 | P2 待验 | 股东/分红/分钟/行业字段覆盖 | 分红映射与股东部分更新保护已有代码，未证明生产覆盖恢复；分别验真实字段/时间/样本；分钟线目前没有已实现表契约，监控标 UNKNOWN，不能据 README 猜测已采集。行业小配额补齐需看逐日下降；概念表无消费方不优先建设。 |
| P2 | P2 待评估 | 决策宇宙扩容 | 800→1200/1500 或成交额分层须先看新鲜覆盖、单次快照耗时/内存，不因历史表行数变多直接扩。 |
| B1 | P3 待环境与显式启用 | 券商适配（旧 #1） | 只在数据与回测可信后推进；BrokerAdapter + 券商环境检查 + dry-run + 回执/人工确认；默认不下单。不能把股票终端快捷方式当可用适配器。 |
| OPS1 | P1 待部署验收 | 将本轮源码部署并核实运行版本 | 保存旧镜像 ID，确认无运行研究任务、两端非默认 JWT_SECRET 相同后同步发布 backend/data-service；其他服务逐个 build/up，核对真实资源 hash、健康与接口，再验一个更新批次；不以 docker cp 或已有旧容器健康判定上线。 |

## 从旧待办移除（实现已存在，不代表所有业务目标完备）

- `/api/user/info`：`stores/user.ts` 已有短 TTL 和 single-flight，旧重复请求任务关闭；有复现再重开。
- AlphaLab 帮助 popover：`AlphaExprInput.vue` 已按屏宽计算上限，旧固定 380px 待办关闭；移动实测仍应纳入发布检查。
- 旧 #6 样本内外/滚动窗口、#7 p 值、#9 权重云同步已有实现与测试，移出未开工清单。
- 旧 #4 复权守卫已有；本轮补齐 read-through/定时/fallback 的重拉入口，线上回填与监控验收仍归 D6/OPS1。
- 旧同步请求超时已有异步研究入口；真正性能、超时取消/恢复分别归 P1/R3，不能混为一个任务。

## 当前可信结论与过期材料

1. **本轮没有重新做全市场策略体检，不给任何策略新增“有效/可加权”结论。**
2. `docs/weekly_sweep_2026-09.*` 与 `docs/weekly_sweep_2026-10.*` 都是历史归档：股票池、样本深度、引擎与方向/成本口径曾变化，不是当前引擎的统一验收名单。
3. Magic Formula 的“coverage 解锁、当前市值可近似”等历史说法已失效：当前 factorlab 明确拒绝缺历史市值/EV 的历史检验。旧结果不得展示为有效研究证据。
4. 资金价量背离历史数据/研究面板已经接入；“只剩资金流 coverage 缺口”“page1 可加深”的旧说明失效。数据新鲜度需重新实测，不能从旧回补总量推断。
5. 行业动量曾有不同会话的 IC/t 值误记和口径变更。历史数值保留作追溯，统一新版本重跑前不拼接成终版排名；候选也不代表成本后可交易。
6. AlphaLab 因子 t 日收盘可知、组合与单股下一交易日开盘成交；仍需审计历史财报版本、股票池和市值，不能宣称全系统已无前视。

## 本地验证（2026-10-13）

Python：288 passed（含本轮执行/队列/数据刷新/维护结果/参考期覆盖/统计/身份签名及跨用户回归）；主前端：63 passed；管理端：9 passed；Java：62 passed（容器 Maven，BUILD SUCCESS）；主前端与管理端生产构建通过。Python 有 1 项既有 Pydantic 弃用提示，Vite 有既有大包与第三方注释警告。

测试不连接生产数据库，不导入会启动调度器的 app.py。独立 Chrome 合成数据组件验证：390px / 1280px × 未校准/已校准零频率/样本不足/回测部分缺失与失败，共 8 个场景通过；无横向溢出、无 pageerror。未使用生产行情或登录会话。截图与结果：`.playwright-cli/analysis-2026-10-12/`（忽略目录）。第二批额外 Chrome 390px：主端 6 场景（含模拟盘加载失败）+ 管理端 3 场景（覆盖/检查失败/任务状态）通过；报告在 `frontend/tests/artifacts/visual-smoke.json`、`admin-frontend/tests/artifacts/visual-smoke.json`，fixture 与测试脚本保留，产物忽略入库。Java 证据：`backend/target/backend-test-20261013.log` 与 `backend/target/verification-20261013/surefire-reports/`（均为本地忽略目录）。

```powershell
# 在仓库根目录创建测试环境（已有 .venv 时跳过第一行）
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r data-service/requirements-dev.txt
Push-Location data-service
../.venv/Scripts/python.exe -m pytest tests -q
Pop-Location
Push-Location frontend
npm ci
npm test
npm run build
Pop-Location
Push-Location admin-frontend
npm ci
npm test
npm run build
Pop-Location
# 本机有 Maven/JDK 17 时
mvn -f backend/pom.xml test
```

生产部署与历史数据重跑另行执行，不在单元测试中暗中触发。

## 历史实现记录（截至 2026-10-11）

以下保留当时记录用于追溯；包含已被上文更正的结论，“已上线/覆盖率”不是本轮生产验收。

| 模块 | 状态 | 关键文件 |
| --- | --- | --- |
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
| **周度全策略体检终版名单**（29 策略 × 周度 131 期，无 🟢；旧口径=代码序宇宙） | ✅ 已归档（2026-10-11 已被下方 v2 取代） | docs/weekly_sweep_2026-09.md + .json |
| **周度全策略体检 v2（全市场日K池重跑）**（与 09 名单同参数、只换池：成交额前 300 从 1015 只里挑 → 从 5531 只里挑，价格类 n 104~~131→135 无缺口；29 策略耗时 2621s。结论：**仍无 🟢**（最高 |t|=1.62，边缘项 |ICIR| 0.12~~0.15 远<0.3）；旧 🟡「日频动量反转T」扩池后 t -1.78→-1.36 **被撤销**，MAX/RSRS 降为无证据（RSRS 方向翻正）；新增 🟠 观察北向/低波动/A股短期反转三项但均不得加权。附带查出：三个 ⚪ 策略卡的是**字段**不是窗口，基本面类策略卡在 `stock_fundamental` 只有 5 期（龙虎榜 n=25 属样本不足）。跑测脚本把全市场 pivot 的 TTL 提到 4h 以免 29 次重复 pivot（进程内局部改动，不影响服务） | ✅ 2026-10-11 | docs/weekly_sweep_2026-10.md + .json、factorlab.py |
| **全站留白治理**（SKILL §34/信息优先：BaseChart/KLineChart/StatGrid/StockHeader 加载骨架 + 空态占位；评分选股进入即自动选股；盘面侧栏 loading 骨架、北向移至末位） | ✅ 2026-09-13 | BaseChart.vue、KLineChart.vue、StatGrid.vue、StockHeader.vue、ScoreScreener.vue、Dashboard.vue、MarketRankCard.vue、theme.css |
| **移动端布局修复**（FactorLabPanel rating-head 移动端断点：评分块对半换行/标题整行下移/metric-line 收窄——修复结果卡横向溢出错位；score-block 补齐样式定义；RefreshBar 窄壳溢出防护） | ✅ 2026-09-13 | FactorLabPanel.vue、RefreshBar.vue |
| 3.5 年历史回补（1015 只 × 659,887 行，2023-03~今） | ✅ 已完成（2026-10-11 已扩至 5531 只/434 万行，见下） | 数据库 stock_kline_daily |
| 数据时钟修复（ann_date point-in-time、指数日历） | ✅ 已上线 | data-service/migrations.py |
| **腾讯全市场行情源**（东财 clist 自 2026-09 起 TLS 指纹层全面拦截，curl_cffi 也失效；qt.gtimg.cn 批量报价无墙，~5866 只含总市值；legacy 中文列 tx_realtime.py + v2 英文列 sources/tencent.fetch_spot 双形态；spot 链 tencent 优先；调度 5 分钟/TTL 300；北交所 92/4/8 前缀映射已修） | ✅ 2026-10-10 | data-service/tx_realtime.py、sources/tencent.py、sources/**init**.py、scheduler.py、app.py |
| **决策快照窗口同交易日护栏**（recent_ids 只取锚点同 trade_date 快照；停摆 24 天缺口曾使 Δ排名 ▲121/稳定度 σ 全失真；跨日对比属因子重算噪声，窗口只算当日） | ✅ 2026-10-10 | data-service/decision/snapshot.py `recent_ids` |
| **spot 帧补行业列**（qt.gtimg.cn 行情不含行业，而板块涨跌/领涨板块/板块强度/sector_flow 全部按 spot 的「行业」列聚合 → 缺列即整条链空。改：stock_industry_map 从 stock_info 联表，模块缓存 1h，缺行业填 "-" 沿用消费方既有过滤惯例；两套帧都补） | ✅ 2026-10-11 | sources/tencent.py、tx_realtime.py |
| **httpx 跨事件循环死锁修复**（`_client` 原为模块级单例，而 tx_realtime/pipelines/调度器/各 job 都用 asyncio.run() 新建循环复用同一 client → 连接池与 anyio 锁属于已关闭循环，永久阻塞：并发全市场抓取曾把 gunicorn worker 全部挂死、/health 无响应且 CPU 0%。改：客户端按运行中的循环持有并回收已关闭循环的残留；ratelimit 的 asyncio.Lock 同样按 (循环,host) 持有） | ✅ 2026-10-11 | core/http_client.py、core/ratelimit.py |
| **spot 冷抓取单飞 + 时段化 TTL**（冷缓存时并发请求曾各抓一次全市场：6 个请求 60s 且重复打腾讯接口。改：进程内锁 + 锁内写缓存（写在锁外会让等待者重复抓）；盘中 TTL 300s、盘外 3600s——非交易时段这一帧就是最后收盘） | ✅ 2026-10-11 | app.py `fetch_spot` `_spot_ttl` |
| **停牌股不得进候选**（实测：停牌的中国重工 601989 全天 0 成交，却以宇宙第 14、「进入买点」、is_actionable=True 出现在今日新建仓候选——照做挂单买不到。改：宇宙入口与选股页按 成交额>0 过滤，与模拟盘既有的「停牌跳过」对齐） | ✅ 2026-10-11 | decision/snapshot.py `_select_universe`、api/strategies_v2.py |
| **北向停披露显式化 + 涨跌幅榜剔新股**（北向卡不再用 2024-08 的数据画"实时"柱图，改显式停披露说明；资金页加仓榜加最后可得窗口标注；summary 的 northboundFlow 由硬编码 0 改 null（缺失禁写 0）；顶栏北向 pill 移除；涨幅/跌幅榜与 topGainers 剔 N/C 前缀首日新股，XD/XR、TCL 不误伤） | ✅ 2026-10-11 | NorthboundChart.vue、MoneyFlowPanel.vue、Header.vue、app.py `_drop_new_listings` |
| **决策页数据过期显式提示**（/api/decision/today 以日K日历 MAX(trade_date) 判最近交易日，快照日落后可见告警 + 高亮描边，盘外/周末不再静默展示旧数字；实测 9-16 旧快照 → stale=true/23 天，周日快照 → 无误报） | ✅ 2026-10-11 | api/decision.py、SnapshotMetaBar.vue、Decision.vue |
| **主力资金源换新浪**（东财 fflow/daykline 被墙后 stock_moneyflow 停在 09-18、主力榜恒空。改：sina `ssl_qsfx_lscjfb` 进 moneyflow 源链首位（r0~~r3_net 元口径，main=超大+大 与东财一致；r1 缺失置 null 不冒充）；/main-rank 响应加 asOf/stale；warm 改交易锚定（比对 stock_moneyflow vs stock_kline_daily 的 MAX(trade_date)）+ 单飞每日一次 + 宇宙=窗口已有股∪成交额 top240；17:10 调度宇宙改成交额 top600；前端主力标签加「覆盖 N/窗口」列与过期/覆盖不足提示；全市场 5870 只×60 日一次性回补 → 33.1 万行 / 5486 只 / 2010-07~~2026-10-09） | ✅ 2026-10-11 | sources/sina.py、sources/**init**.py、api/moneyflow.py、scheduler.py、MoneyFlowPanel.vue、api/moneyflow.ts |
| **个股财务与估值 tab**（新端点 /api/stock/<code>/financials：最近 10 个报告期营收/净利/YoY/ROE/EPS + 同期行业中位数（pandas 取中位，不用 AVG）+ PE/PB/ROE 行业内分位；Java 需加显式 Controller 映射（逐端点白名单，无泛化透传）TTL 600s；前端 FinancialsCard=三张分位条（标注方向：PE/PB 越低越便宜、ROE 越高越强）+ 营收/净利润/ROE 三视图（柱=金额 亿，线=YoY%，虚线=行业中位）+ 诚实脚注（报告期数与区间、累计口径、无行业对照）；缺数据一律 null 显示「—」，无财务记录整卡走空态；与 F10 同业排名交叉一致 600519：PB 94.7%≈18/19、PE 35.7%≈5/19、ROE 94.7%≈2/19） | ✅ 2026-10-11 | api/f10.py、backend StockController/DataService、FinancialsCard.vue、StockDetail.vue、api/stock.ts |
| **日K覆盖扩至全市场**（1031 只 → **5531 只 / 434 万行**，周K 5494 只；一次性回补 count=850（≈3.5 年）5514 只活跃股耗时 615s。根因是调度器只刷市值 top300 → 榜外股票永远拿不到增量、因子与回测宇宙被悄悄截断。改：`WARMUP_TOP_N` 默认 0=全市场活跃股（成交额>0，与决策宇宙同口径），warmup_klines 支持 count；新股/科创/北交所均覆盖（301236 850 根、688981 850 根、920002 140 根、688825 长鑫科技 49 根）。/api/admin/health-detail 新增 freshness{codes,maxDate,coveragePct,universe}——行数会说谎,覆盖度才是真相） | ✅ 2026-10-11 | scheduler.py `warmup_klines`、api/admin.py `_mysql_status` |
| **日K增量第二条腿 + 口径实测**（legacy `batch_klines` 内部其实是 **腾讯→新浪→同花顺**（不是东财!），所以库内基线=这两家的口径；实测 sources.sina 与库内 **600 根逐 bar 零差**（600519/601398/000651/300750），故 warmup 漏取股票改走 `_kline_fallback`＝新浪→东财httpx（东财 fqt=1 放最后，避免在既有口径上开新接缝）。WARMUP_ON_START 改 false：每次重启打 1.1 万次请求纯属浪费且会触发行情源限流,增量靠 16:30 任务,重建库后手动 POST /api/admin/warmup） | ✅ 2026-10-11 | scheduler.py `_kline_fallback`、docker-compose.yml |
| **A股基础清单刷新（新股/改名/行业）**（官方清单口径：上交所主板1702+科创618、深交所2904、北交所349≈5573 只。只维护 code/name（update_columns=['name'] 绝不碰 industry/market_cap/财务列）→ 实跑**新增 45 只次新股**（长鑫科技/燧原科技/沈鼓集团等，2026-07 后上市）+ **113 处改名**（修掉 spot 快照带来的 `XD`/`*ST` 前缀与 8 字截断名）。缺失行业用东财单股 f127（申万口径，与现值同源；深市清单里的证监会分类 taxonomy 不同，不采用）——配额 30 只/1s，每日 08:40 跑，周日 20:00 全量刷新。空 industry 已被 `stock_industry_map` 过滤，不会在板块图里长出空名分桶。**传导链已打通**：`tx_realtime`/现货帧的代码清单就是 `stock_info`（`_stock_info_codes` 现返回 5912 只并含 688825/601091），此前新股在盘面/选股/决策/F10 全线不可见的根因即此——周一 09:00 现货刷新起新股自动进入各消费方 | ✅ 2026-10-11（新股/改名已落库；380 只行业补齐受东财封锁延后到每日小配额任务） | jobs/stock_list.py、scheduler.py |
| **基准指数日线停更修复（回测基准 + 交易日历）**（index_kline_daily 的 000300/000905 停在 2026-09-11（落后 21 个交易日），唯一写入方 jobs/postmarket.py 不在调度表内 → 回测基准曲线与「指数 bar 充当的交易日历」被静默截断，最近窗口的超额收益是在跟旧曲线比。改：①sources/sina 补 `fetch_index_kline`（东财 secid `1.000300` → 新浪 `sh000300`），管线改东财→新浪双源；②调度新增每日 16:20 `index_kline_refresh`（先于 16:30 全市场增量）。实跑：东财 push2his 仍在封锁期，两只指数均由新浪供数，900→914 根追平 2026-10-09；口径交叉校验 库内 close 4317.255 == 实时 4317.25、7251.006 == 7251.01） | ✅ 2026-10-11 | pipelines/index_kline.py、sources/sina.py、scheduler.py |
| **盘面请求风暴治理（重复订阅 + 策略分 N+1）**（根因不是「双 onMounted」而是 refresh store 的**单槽 reloader**：`registerReloader` 覆盖前一个组件的 loader，而每个 `useRefreshable` 组件挂载都调 `invokeReloader()`＝跑「当前」那个 → 同页 N 个组件＝同一批接口拉 N 次，且可能跑的是别人的 loader。改：①store 改多路注册（Map<label,{fn,autoRefresh,running}>）+ `invokeLabel`（组件挂载/keep-alive 切回只跑自己的，各自防重入）+ `invokeReloader`（全局刷新按钮/轮询才把所有各跑一次），`reloader` 保留真值语义以兼容 RefreshBar 显隐；②新增 `POST /api/v2/strategies/batch`（复用 `_bulk_load_panels` + `_score_all` + `_parse_weights`，与 /screen、/stock/<code>/score 同引擎同权重口径，上限 60 只），Java 加 `POST /api/stock/strategies/batch`；③Dashboard 用 1 次批量替掉 20 次逐股 GET。**顺带修好一个死 UI**：legacy `/api/stock/<code>/strategies` 根本不返回 `aggregate`，盘面「策略评分」列一直显示 `—`，现在 20 行全部渲染真实「看多/有效·触发」。实测一次盘面加载：8 个市场接口各 1 次（原 3 次）+ 1 次批量 POST（原 20 次）；个股页同样每接口只发一次） | ✅ 2026-10-11 | stores/refresh.ts、useRefreshable.ts、api/strategies_v2.py、backend StockController/DataService、Dashboard.vue |
| **资金流历史加深 + 研究面板补 mf 一路**（「资金价量背离」的 ⚪ 是**双重缺失**：①取数——上一版按 `page1` 分页 + `num=60` 想加深，实测新浪该接口 **page1 被忽略**（page1=2 返回与 page1=1 完全相同的 250 行），num=2000 才不截断，所以库里平均永远只有 60.4 天/只；改单次大 num 后全市场回补 700 交易日 → **avg 60.4 → 675.1 天/只**、5853 只有数、395 万行 / 250s。②接线——`backtest.engine._load_panel` 只有 dk/fund/nb/lhb 四路，`ctx.moneyflow_df` 恒为 None，策略每期 insufficient_data；补 mf 一路（as-of 尾部 30 行、只取 main_net 非空），`run_single` 同步接上 mf 与行业强度，体检/组合回测/单股回测三条链路同口径。验证：factorlab 周度 n 0→**135**，IC -0.0029 / t -0.34 / grade D / 成本后净价差 -18.1% → 结论从「测不了」变成「可检验且无证据」。附带揪出并修掉一个内存缺陷：`run()` 调 `_load_panel` 时**没传 start**→ 无日期下界全历史载入，加深后实测把容器吃到 10.4 GiB 并拖停 Docker VM；传 start 后同一次回测峰值 3.47 GiB） | ✅ 2026-10-11 | sources/sina.py、backtest/engine.py、tools/backfill_moneyflow.py |
| **申万二级行业指数日线 + as-of 行业强度排名**（「行业动量轮动」长期 ⚪ coverage 的真因不是窗口，而是研究链路根本没注入 `sector_rank`——唯一注入点 api/strategies_v2 用的是**当日**涨跌幅均值排名，既不符合策略文档的 20 日相对强度，也无法按 as-of 回放，于是每期都 no_data。数据源选申万官网（`sw_index_second_info` + `index_hist_sw`）：实测 128 个行业名里 **127 个与 stock_info.industry 完全一致**（本就是同一口径），行业指数与个股行业可直接 JOIN、无需会漂移的人工映射表，且完全绕开已封锁的东财板块列表；首轮回补 131 指数 / 19.2 万行（2019 起）。新增 core/sector_rank 统一口径（只用 ≤as_of 的收盘算 20 日动量截面排名，0.0=最强，面板缓存 30min），实时与研究两条链路共用**同一份**实现；原先 api/strategies_v2 里那套「当日涨跌幅快照排名」已删除——同一字段留两种定义会让盘面与体检对同一只股票给出互不相容的数字，表为空/对不上口径时返回 None 走 no_data（银行股因此 effective 27 vs 其他 28，是可见的诚实降级而非错数）。银行类**不合并口径**：申万把银行拆成国有大行/股份行/城商行/农商行，我们只有「银行Ⅱ」，对不上就返回 None，宁可缺也不把两套 taxonomy 混进同一个截面。踩到两个坑：①`DataFrame / Series` 默认按**列**对齐，用日期索引的 n 去除排名会让列数从 131 炸到 2013 且全 NaN（必须 `.div(n, axis=0)`）；②工具脚本的 `main()` 写在模块顶层导致 import 即触发跑测。验证：sector_rotation n 0→135、IC -0.0073、t -0.41、grade D（无证据）；technical_resonance 数值与改动前完全一致（t -0.72），证明注入没有扰动其它策略口径。调度工作日 16:22 增量刷新（先于 16:30 全市场日K） | ✅ 2026-10-11 | core/sector_rank.py、pipelines/industry_index.py、repo/industry_index_repo.py、backtest/engine.py、api/strategies_v2.py、scheduler.py  |
| **基本面历史深度回补（2021Q4~2026Q1，18 个报告期）**（akshare 业绩报表+资产负债表按报告期整表拉。三个坑：①业绩表 11639 行里含**新三板同号重复**（同一公司 920296/874332 数值完全一致）→ 必须按 stock_info 宇宙过滤，否则污染财务表；②同比增速有 5e10 级极值，直接写会撞 decimal(10,4) 列宽导致整批 1264 回滚（第一次试跑就是 0 行入库）→ 超界一律置 None，不裁成边界值冒充真实数字；③upsert 原先固定 update_columns=COLS[3:]，会把别的链路写过的 current_assets/fixed_assets/ebit 覆写成 NULL → 改成只写 df 里真实存在的列。结果：avg_periods **4.27 → 17.72**，`total_assets` 从全表 0 变成每季 ~~5200 行（应计利润质量/资产增长异象正靠它），并补上 **2025Q1 只有 308 行** 的历史漏洞（此前只有 2025Q2 起才完整）。**前视纪律**：实测 yjbb 的『最新公告日期』是「最近一次公告」而非原始披露日（FY2024 中位数落在 2026-04-24，99% 的行晚于报告期末+200 天），拿它当 ann_date 会让回测 as-of 门控把 2022~~2024 整段看成不可知、比留空更糟 → 该列刻意不采信，留 NULL 由引擎按法定披露截止日兜底。影响：piotroski n 108→135（t 1.17→1.70，现为全表第二高）、应计利润 126→135、资产增长 74→135（t 由 -0.43 翻正 1.14）、PEAD 126→135、quality 126→135 → **v2 名单里基本面那一族的旧数字属样本受限，以重跑结果为准**） | ✅ 2026-10-11 | pipelines/fundamental.py、repo/fundamental_repo.py、tools/backfill_fundamental.py |
| **统计引擎 v2（quant_stats + ENGINE_VERSION + 样本内外验证）**（缺失证据永不为 0：所有摘要统计统一走 quant_stats（finite-only），None/NaN/inf 不过阈值、显示「—」；IC 摘要含 p 值（双侧 Student t，df=n-1）；评级引擎版本化 ENGINE_VERSION 并入 factormine 缓存 hash（引擎升级自动失效旧缓存）；方向判定 direction_source=TRAIN_ONLY（只用训练段定方向，防验证段信息泄漏）；validation 块含 train/test 拆分 + 滚动窗口 ICIR；tradability 未实测显式 null + note，不得用净收益冒充交易可行性；分层净收益可复算＝毛−换手×成本） | ✅ 2026-10-11 | data-service/quant_stats.py、factorlab.py、tests/test_factor_statistics.py、tests/test_mining_nullable_stats.py |
| **行业指数日线管线（申万二级 131 只，2019-01-02 起，19.2 万行）**（选申万是因 stock_info.industry 就是申万二级口径（128 个行业名 127 个与官方一致，「银行Ⅱ」去后缀匹配），同名直接 JOIN 无映射漂移；只取 close（动量算相对强度，OHLC 口径存疑）；首次全量后按 MAX(trade_date) 增量；串行+停顿防限流；每日调度 industry_index_refresh） | ✅ 2026-10-11 已回补 | pipelines/industry_index.py、repo/industry_index_repo.py、scheduler.py |
| **sector_rank 口径统一**（「行业 20 日动量前 20%」原先唯一注入点（api/strategies_v2）用的是**当日**涨跌幅均值排名，与策略文档不符，且研究链路（factorlab/回测）完全拿不到 sector_rank → 行业动量轮动每期 no_data 判 coverage。改：core/sector_rank 一处口径（≤as_of 行业指数收盘 20 日动量截面排名，rank_pct 0.0=最强），api 与 engine.\_score_at_cached 同源注入。坑：DataFrame/Series 运算默认按列对齐，n 必须 axis=0 按日期对齐否则整片 NaN） | ✅ 2026-10-11 | core/sector_rank.py、api/strategies_v2.py、backtest/engine.py |
| **行业动量轮动解锁：⚪ → 🟡 候选（反向）**（周度 135 期实测：n=135/截面 299/40406 观测，IC **-0.041**、t **-2.52**、p **0.013**，direction=reverse（TRAIN_ONLY），grade C；A股行业动量在个股层呈**反转**效应。但成本侵蚀：方向调整后毛收益 +4.0% 年化、净 **-9.4%**，多空两腿年化换手 44.7x → 判 CANDIDATE，**不得加权**） | ✅ 2026-10-11 | strategies/sector_rotation.py、冒烟实测（收尾会话） |
| **因子挖掘管线 factormine**（漏斗：GENERATE 模板族×原子（MAX_DEPTH=4/算子≤6/变量≤5 硬上限+归一化去重）→ STATIC 负窗口泄漏扫描 → QUICK 快速 IC（|RankIC|≥门槛且 |ICIR|≥0.15）→ DEDUP Spearman 聚类（|corr|≥0.85 归簇含已入库因子）→ VALIDATE 走 factorlab.analyze_scores 完整检验（与内置策略同引擎）+ 样本内外/年度稳定/Walk Forward/成本敏感 → PASS/WATCH/REJECT；挖掘队列持久化） | ✅ 2026-10-11 代码+单测落地，**未跑全量挖掘** | data-service/factormine/*、api/factormine.py、FactorMinePanel/Detail.vue、FactorMineController.java |
| **交互式长计算改后台 job**（回测/因子检验原为同步 HTTP 靠 RestTemplate 5 分钟超时硬撑；改提交即返 job_id 前端轮询，内存保留 1h/40 份，重启即失不持久化） | ✅ 2026-10-11 | research_jobs.py、api/research_jobs.py、useResearchJob.ts、ResearchJobController.java、Research.vue |
| **预测诊断重构（评分/频率/风险三者分离）**（修复「预测评分被当成涨跌概率显示」的混淆：combine() 输出趋势评分（-100~100）、历史频率、风险分列，unmodeled 风险显式列出；MODEL_VERSION=prediction-2026-10-11-v2） | ✅ 2026-10-11 | prediction_research.py |
| **权重云同步 + 单位统一**（待办 #9 关闭：用户自定义权重 localStorage → 服务端（StrategyConfigController/Service + strategyConfig.ts）。**单位坑**：云端/UI 是百分点（12）、注册表是比率（.12），合并新策略前必须 /100 统一；模拟盘权重改 PAPER_WEIGHT_USER_ID 显式绑定，共享账户不再「最后用户赢」，绑定缺失/非法即中止调仓，不静默回退默认） | ✅ 2026-10-11 | strategy_preferences.py、api/strategyConfig.ts、stores/strategy.ts、StrategyConfigController.java、tests/test_strategy_preferences.py |
| **复权守卫 adjustment_guard**（复权失败造成的局部重定基被拒：重叠段价格有实质变动且新数据未完整覆盖旧区间 → 判整股需全量重刷，绝不用猜测因子缩放旧价制造接缝） | ✅ 2026-10-11 | core/adjustment_guard.py、tests/test_data_quality_repairs.py |
| **AI 对话面板**（会话/消息落库（ai_chat_session/message），后端 AiChatService + 前端 AiChatPanel（My 页）） | ✅ 2026-10-11 | AiChatService.java、AiChat*Mapper/Entity、AiChatPanel.vue |
| **Magic Formula 历史检验显式拒绝**（factorlab.analyze 对 magic_formula 直接返回失败：缺历史市值/企业价值，当前市值或市值=0 的近似**不得**用于历史检验——宁缺毋假） | ✅ 2026-10-11 | factorlab.py `analyze()` |


## 已知问题/坑

- **禁止用 `asyncio.run()` 包 http_client 的异步代码后再复用 client**：httpx.AsyncClient 与 asyncio.Lock 绑定首次驱动它们的循环，跨循环复用不是报错而是**静默永久阻塞**（CPU 0%、gunicorn worker 全挂、/health 都不返回，日志只剩半句"Fetching market spot"）。已按循环持有（core/http_client.py `_clients`），新增同步入口时沿用 `http_client.run()` 或确保走 `_get_client()`，别自己缓存 client
- **Vue setup 里 `watch(x, fn, { immediate: true })` 的同步回调不能引用其后才声明的 `let`**（TDZ：`Cannot access 'x' before initialization`）；若该调用包在 `try/catch` 里会被静默吞掉，表现为「请求根本没发出且不再重试」。要么把状态声明提前，要么 initial 加载走独立入口（2026-10-11 财务 tab 踩过）
- **Java 网关是逐端点显式 Controller + 白名单缓存，没有泛化透传**：新增 data-service 接口必须同步改 StockController/DataService（`docker compose build backend` 内置 mvn，约 1 分钟），否则 18080 返回 `{"code":404,"message":"接口不存在"}` 而 5001 直连正常。`/api/moneyflow/stock/<code>` 至今未放行（无前端消费方）
- **东财全市场 clist 已死**（2026-09 起）：push2/push2delay 连 curl_cffi chrome 指纹都返回 0 行，别再调 em_realtime.fetch_all_spot 排障——全市场行情走 tx_realtime（qt.gtimg.cn）。东财**单股**行情接口（push2his K线/trends2/details）可用；**fflow 资金流（含 daykline）也被墙**——资金流走新浪 `ssl_qsfx_lscjfb`（sina 源已在链首位）
- **`docker cp` 进容器不是部署**（2026-10-11 踩过）：data-service/frontend 都没有 bind mount，`docker compose up -d <svc>` 会用**镜像**重建容器，静默抹掉此前 cp 进去的所有改动（一次抹掉了 sina 资金流链、/financials、admin freshness 三块已验证代码）。正确流程：改完 → `docker compose build <svc>` → `up -d` → 在容器内 `ls/grep` 确认文件真的在，再验接口。临时排障可以 cp，但必须 `docker restart`（不是 compose up）才不被覆盖
- **构建期 pip 源会整段卡死，且管道会吞掉构建失败**（2026-10-11 踩过）：data-service 的 pip 层原先写死阿里云镜像，本机实测 curl_cffi(2MB 的 win 轮子跑 91s 没下完)、容器内 13.5MB 轮子卡 150s+ 零进度 → 镜像构建失败。而 `docker compose build svc1 svc2 svc3 | tail -5` 的退出码取的是 **tail**（恒 0）→ 失败被静默略过，`&& up -d` 照跑，结果只有部分服务更新，data-service 仍在跑旧代码（症状：容器内 `ls` 不到新文件、镜像时间戳还是几小时前）。排障务必 `docker compose build --progress=plain <svc> > /tmp/build.log 2>&1` 落盘看。速修：腾讯镜像同文件 5s、全量 pip 层 <100s（`--build-arg PIP_INDEX=https://mirrors.cloud.tencent.com/pypi/simple --build-arg PIP_TRUSTED_HOST=mirrors.cloud.tencent.com`；Dockerfile 已参数化，默认值仍为阿里云）
- **对东财单股接口突发请求会换来分钟级封锁**（2026-10-11 实测）：380 只 × 0.15s 间隔之后，`push2/api/qt/stock/get` 与 `push2his kline`（httpx）全部返回 None，而同主机的 `trends2` 与 legacy aiohttp 路径仍通——封锁是按 host+指纹分档的。所以批量补齐一律走小配额（jobs/stock_list 30 只/1s）而不是并发扫
- 容器内跑 python 脚本用 `docker exec -i`（stdin 要传）；host 直连东财被 TLS 指纹拦截，数据抓取一律在容器内跑；从 host 传 `/app/...` 路径进容器要加 `MSYS_NO_PATHCONV=1`，否则 Git Bash 会把它改写成 `C:/Program Files/Git/app/...`（连 `-e KEY=/path` 的环境变量值也会被改）
- **给 `_load_panel` 加数据源前先确认下界**：`backtest.engine.run()` 曾调 `_load_panel(codes, end)` **不传 start**，于是 K线/北向/龙虎榜/资金流全按无下界全历史载入；主力资金加深到 700 天/只后，一次 6 个月组合回测把容器顶到 **10.4 GiB** 并拖停 Docker VM。修法是传 `start`（内部 `start-400天` 已足够预热 260 根 K 线 + 60 日北向/龙虎榜 + 30 日资金流），同一次回测峰值降到 **3.47 GiB**。任何新面板列都要按宇宙规模估内存，别只看单只股票。
- **容器内测试脚本严禁 `import app`**——app.py 在 import 时就启动调度器；universe 用 `cache.get("spot")`（redis 共享，服务进程已暖）
- **alphalab 与 factorlab 的宇宙必须同源**——两个"前 N"集合若不相交（如代码序 vs 流动性序），覆盖门槛会把所有期数清零（2026-09-13 踩过）；provider 与 codes 一起传给 analyze_scores
- **alphalab.build_panel 已把 K 线/财务面板索引统一为 DatetimeIndex**——K 线原生是 date 对象，不归一则混合表达式（行情×财务）索引对齐全 NaN；新增面板字段时注意
- 文件行尾混用 LF/CRLF——python 补丁脚本用「按行分割 + nl 探测」，锚点断言失败先查行尾
- 前端是 PWA（service worker 预缓存）：rebuild 后第一次 reload 可能仍被旧 SW 控制；验证新 UI 前先注销 SW+清 caches（浏览器 console）或核对资源 hash 与 `frontend/dist/assets` 一致
- **新卡片/图表必须接 loading 骨架**：BaseChart(`loading`/`placeholder`)、KLineChart(`loading`)、StatGrid(`loading`)、StockHeader(`loading`) 都已支持——禁止裸空白渲染（2026-09-13 全站留白治理的约定）
- 评分选股页 `runFilter({ silent: true })` 是进入页面自动跑的静默路径，不带成功/失败 toast；手动按钮仍走带提示路径
- 回测结果受幸存者偏差影响：K 线表现含 5531 只（2026-10-11 起=全市场活跃股），但**仍只含当前在市股票**，退市股从未入库 → 绝对收益和横向排序都可能有偏，alphalab 回测同理；只可在明确同口径限制下比较
- 周度体检原始结果已归档 `docs/weekly_sweep_2026-09.json`（旧口径=代码序宇宙）
