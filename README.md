# A 股智能选股 / 量化分析平台

[![Vue](https://img.shields.io/badge/Vue-3.4-42b883)](https://vuejs.org/)
[![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.x-6db33f)](https://spring.io/)
[![Python](https://img.shields.io/badge/Python-3.11-3776ab)](https://python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

> 全栈量化选股平台：十大学术经典策略 + 条件选股 + 表达式选股 + 回测 + 龙虎榜 + 资金流 + F10 + 自选股提醒。前端 Vue 3，后端 Spring Boot 网关 + Python 数据微服务，多源异步爬虫 + MySQL 持久化。

![architecture](https://img.shields.io/badge/Frontend-Vue%203%20%2B%20TS%20%2B%20Element%20Plus%20%2B%20ECharts-42b883)
![architecture](https://img.shields.io/badge/Backend-Spring%20Boot%203%20%2B%20MyBatis--Plus%20%2B%20JWT-6db33f)
![architecture](https://img.shields.io/badge/DataService-Flask%20%2B%20httpx%20%2B%20APScheduler%20%2B%20pydantic-3776ab)
![architecture](https://img.shields.io/badge/Storage-MySQL%208%20%2B%20Redis-dc382d)

---

## ✨ 核心特性

### 选股三档能力（同花顺 / Wind 风格）

| 档次 | 入口 | 适用人群 |
|---|---|---|
| 🟢 **综合评分选股** | `策略实验室` | 普通用户：拖滑块调权重 + 调每个策略的内部阈值，实时预览 Top 20 |
| 🟡 **条件选股** | `条件选股` | 进阶用户：23 字段表单式 AND/OR 组合 + 5 个一键模板（价值/成长/动量/主力/低波） |
| 🔴 **表达式选股** | `表达式选股` | 量化玩家：Python-like DSL + 22 个时序函数 + 安全 AST eval |

### 十大学术经典策略

每个策略都有公开学术或业界 alpha 来源，**所需数据全部能拉到**（不是占位）。

| # | 策略 | α 来源 | 默认权重 |
|---|---|---|---|
| 1 | **Piotroski F-Score** | Piotroski 2000，9 项基本面打分 | 12% |
| 2 | **Magic Formula** | Greenblatt，ROC × 盈利收益率 | 10% |
| 3 | **Quality Factor** | MSCI Quality，稳定 ROE + 现金流 + 低杠杆 | 18% |
| 4 | **12-1 月动量** | Jegadeesh-Titman 1993 | 10% |
| 5 | **低波动异象** | Frazzini-Pedersen Betting Against Beta | 8% |
| 6 | **PEAD 盈余惊喜后漂移** | Ball-Brown 1968 | 10% |
| 7 | **北向资金追踪** | A 股聪明钱跟踪 | 8% |
| 8 | **龙虎榜机构跟随** | 事件驱动 | 8% |
| 9 | **行业动量轮动** | Moskowitz-Grinblatt | 8% |
| 10 | **技术共振** | MACD + 量价 + 北向短期 | 10% |

每个策略 2-3 个**可调阈值参数**通过滑块暴露（如 Piotroski F-Score 看多阈值 / Quality min ROE / Momentum 回看天数 / PEAD 事件窗口...）。

### 其他能力

- 📈 **大盘面板** — 7 大指数实时（上证/深证/创业/沪深300/科创50/上证50/中证500）+ 涨停跌停统计 + 涨幅/跌幅/活跃榜
- 🐯 **龙虎榜专页** — 近 60 天 3066 行明细 + 净买榜 + 个股频次榜
- 💰 **资金流专页** — 主力净流入/流出榜 + 北向加仓 TopN + 板块资金轮动
- 🔬 **F10 个股资料** — 公司概况 / 十大流通股东 / 分红送转 / **同行业 PE/PB/ROE 排名**
- ⏰ **策略回测** — 两种模式：横截面 Top-N 组合回测 / 单股择时回测（bullish 买 / bearish 卖）
- ⭐ **自选股** — 分组管理 + 加自选幂等（软删复活 / 浏览器状态联动）
- 🎯 **K 线 + 雷达图** — 个股详情页 ECharts 联动

---

## 🏗️ 架构

```
┌──────────────────────────────────────────────────────────────────┐
│                          浏览器                                  │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                     ┌──────────▼──────────┐
                     │   Nginx :80         │  frontend container
                     │   (Vue 3 静态资源)  │
                     │   /api/* → backend  │  反代
                     └──────────┬──────────┘
                                │
              ┌─────────────────▼─────────────────┐
              │   Spring Boot :8080               │  backend container
              │   网关 + JWT 鉴权 + Redis 缓存    │
              │   /api/screen, /api/lhb, /api/... │
              └─────────────────┬─────────────────┘
                                │
              ┌─────────────────▼─────────────────┐
              │   Flask :5001                     │  data-service container
              │   ├ core/ httpx + 限流 + 熔断     │
              │   ├ sources/ 7 个数据源适配器     │
              │   ├ pipelines/ 10 个采集管道      │
              │   ├ strategies/ 十大策略          │
              │   ├ backtest/ 矩阵化回测引擎      │
              │   └ jobs/ APScheduler 调度        │
              └────────┬─────────────┬────────────┘
                       │             │
                ┌──────▼─────┐ ┌─────▼─────┐
                │  MySQL 8   │ │  Redis 7  │
                │ 17 张数据表│ │ 二级缓存   │
                └────────────┘ └───────────┘
```

### data-service 数据栈

| 数据 | 表 | 数据源 |
|---|---|---|
| 实时行情 | spot 缓存 | 东方财富 push2delay |
| 日 / 周 / 月 K | `stock_kline_daily/weekly` | 腾讯主，新浪兜底，akshare 后备 |
| 财务三表 | `stock_fundamental` | akshare 业绩报表批量预拉（**200x 提速过**） |
| 资金流（5/超大/大/中/小单） | `stock_moneyflow` | 东方财富 push2 fflow |
| 北向持股 | `stock_northbound` | akshare hsgt + 东方财富 datacenter |
| 龙虎榜（含席位） | `stock_lhb` | 东方财富 datacenter（分页拉取 60 天） |
| 股东户数 | `stock_shareholder` | akshare gdhs |
| 分红送转 | `stock_dividend` | 东方财富 datacenter |
| 公告 | `stock_announcement` | 东方财富 ann |
| 分钟 K（5/15/30/60min） | `stock_kline_minute` | 腾讯 mkline |
| 概念板块 | `stock_concept` | 同花顺 + akshare |

调度（`jobs/`）：盘前 8:30 + 盘中 9-15/5min + 盘后 16:30 + 周末 10:00，4 时段任务独立 lock。

### 反爬技术栈（`core/`）

- ✅ httpx + HTTP/2 + 连接池
- ✅ **自适应限流** — 按域名独立令牌桶，429/418/403 自动退避，连续 200 提速
- ✅ **熔断器** — 连续失败切到 fallback 源，冷却后半开探测
- ✅ **UA / Referer / Cookie 三池**轮换（fake-useragent + 自维护）
- ✅ **tenacity 重试** — 区分 transient 5xx/网络（重试）vs fatal 4xx（直接 raise）
- ✅ **Playwright 浏览器池**（opt-in，针对同花顺 hexin-v JS 加密）
- ✅ **代理池接口**（`PROXY_POOL_URL` env，免费用直连）
- ✅ pydantic v2 数据校验，脏数据进 dlq
- ✅ Prometheus 指标 `/metrics` + 熔断状态 `/circuits`

---

## 🚀 快速启动

### Docker 一键部署（推荐）

```bash
git clone https://github.com/yanwu001101/StockAnalysis.git
cd StockAnalysis
docker-compose up -d
# 等待 ~30 秒数据预热
# 浏览器打开 http://localhost
```

5 个容器全部健康后即可用：

```
stock-frontend     :80     ✓ Vue3 + Nginx
stock-backend      :8080   ✓ Spring Boot 3
stock-data-service :5001   ✓ Flask
stock-mysql        :3306   ✓ healthy
stock-redis        :6379   ✓ healthy
```

### 数据预热（首次启动后建议跑一次）

```bash
# 拉日 K + 资金流 + 北向 + 龙虎榜
docker exec stock-data-service python -c "
import asyncio
from jobs.postmarket import run
run()
"

# 拉财务三表 + 股东 + 分红 + 概念板块
docker exec stock-data-service python -c "
import asyncio
from jobs.weekend import run
run()
"
```

之后 4 时段调度会自动维护数据新鲜度。

---

## 🌐 公网暴露（可选）

### SakuraFrp 内网穿透（最快）

1. 注册 https://www.natfrp.com/
2. 创建 TCP 或 HTTP 隧道：
   ```
   本地地址: 127.0.0.1
   本地端口: 80
   ```
3. SakuraLauncher 启动隧道 → 拿到公网 URL（类似 `https://xxx.frp.one`）

### Cloudflare Tunnel（长期免费）

```bash
cloudflared tunnel --url http://localhost:80
```

详见 [Cloudflare 文档](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/)。

---

## 📂 项目结构

```
StockAnalysis/
├── frontend/                  Vue 3 + TS + Element Plus + ECharts
│   └── src/
│       ├── views/
│       │   ├── Dashboard.vue              大盘指数 + 涨跌榜
│       │   ├── Screener.vue               简易选股
│       │   ├── ConditionScreener.vue      条件选股 (Phase 2)
│       │   ├── ExpressionScreener.vue     表达式选股 (Phase 3)
│       │   ├── StrategyLab.vue            策略实验室（权重+阈值）
│       │   ├── Backtest.vue               组合 / 单股回测
│       │   ├── StockDetail.vue            K线 + 策略雷达 + F10
│       │   ├── Lhb.vue                    龙虎榜专页
│       │   ├── MoneyFlow.vue              资金流专页
│       │   └── Watchlist.vue              自选股
│       └── api/, stores/, components/
│
├── backend/                   Spring Boot 网关
│   └── src/main/java/com/stock/
│       ├── controller/        Market/Stock/Screener/Backtest/User/Watchlist/Lhb/MoneyFlow
│       ├── service/DataService.java         统一转发 + Redis 缓存
│       ├── config/AuthInterceptor.java      JWT 鉴权 + 白名单
│       └── mapper/                          MyBatis-Plus
│
├── data-service/              Python 数据微服务
│   ├── api/                   8 个 Flask blueprint
│   │   ├── backtest.py        矩阵化回测端点
│   │   ├── strategies_v2.py   十大策略评分 + 综合选股
│   │   ├── conditions.py      条件 DSL 选股
│   │   ├── expression.py      表达式 AST 安全 eval
│   │   ├── lhb.py             龙虎榜聚合
│   │   ├── moneyflow.py       主力 / 北向 / 板块资金
│   │   ├── f10.py             公司概况 / 股东 / 分红 / 同业排名
│   │   └── metrics.py         /metrics + /circuits
│   ├── core/                  9 个基础设施模块
│   │   ├── http_client.py     httpx + HTTP/2 + 限流 + 重试 + 熔断
│   │   ├── ratelimit.py       自适应令牌桶
│   │   ├── retry.py           tenacity 装饰器
│   │   ├── circuit.py         熔断器（closed→open→half-open）
│   │   ├── headers.py         UA / Referer / Cookie 三池
│   │   ├── proxy.py           代理池接口
│   │   ├── browser.py         Playwright（opt-in）
│   │   ├── parser.py          jsonp / json / dataframe 解析
│   │   └── trace.py           structlog + Prometheus
│   ├── sources/               8 个数据源适配器
│   │   ├── eastmoney.py       东财（行情/F10/资金流/龙虎榜/股东/北向）
│   │   ├── tencent.py         腾讯 K 线 + 分钟 K
│   │   ├── sina.py            新浪 K 线兜底
│   │   ├── xueqiu.py          雪球 F10
│   │   ├── ths.py             同花顺概念（Playwright）
│   │   ├── akshare_src.py     akshare 包装
│   │   └── tushare_src.py     Tushare Pro（opt-in TUSHARE_TOKEN）
│   ├── pipelines/             10 个采集管道 (多源 fallback + 校验 + 入库)
│   ├── repo/                  9 个 MySQL repo (upsert 幂等)
│   ├── strategies/            十大策略 (每个独立 + pydantic Params)
│   ├── jobs/                  APScheduler 4 时段
│   ├── backtest/              矩阵化回测引擎 + Metrics
│   ├── config.py              pydantic-settings 集中配置
│   └── models.py              pydantic v2 数据模型
│
├── docker-compose.yml
└── README.md
```

---

## 🔧 环境变量

```bash
# 必备
DB_PASSWORD=Stock@2024
REDIS_HOST=redis
DATA_SERVICE_URL=http://data-service:5001

# 可选数据源
TUSHARE_TOKEN=                # Tushare Pro token（≥2000 积分可拿龙虎榜席位）
XUEQIU_COOKIE=                # 雪球 xq_a_token cookie
ENABLE_PLAYWRIGHT=false       # 同花顺 hexin-v 兜底
PROXY_POOL_URL=               # 代理池 URL

# 限流 / 重试调参
HTTP_TIMEOUT_S=10
RL_JITTER_MIN_MS=50
RL_JITTER_MAX_MS=200
RETRY_MAX_ATTEMPTS=4
CB_FAILURE_THRESHOLD=0.5      # 熔断阈值

# 调度
WARMUP_ON_START=true          # 启动后 60s 跑一次 postmarket
WARMUP_TOP_N=300
```

---

## 🧪 表达式选股 DSL 参考

```python
# 价值股
PE > 0 and PE <= 25 and PB <= 3 and ROE >= 15 and DEBT <= 60

# 动量突破
CLOSE > MA(CLOSE, 60) and MACD_GC(5) and V > MA(V, 20) * 2

# RSI 超卖反弹
RSI(6) < 30 and CLOSE > REF(CLOSE, 1) and V > MA(V, 10) * 1.5

# 20 日新高 + 量能放大
CLOSE > HHV(HIGH, 20) and V > MA(V, 5) * 1.5 and PCT_CHANGE > 2

# 成长股
REV_YOY >= 20 and NP_YOY >= 30 and GROSS_MARGIN >= 30 and ROE >= 12
```

支持的字段 / 函数：

| 类别 | 标识符 |
|---|---|
| **时序** | `CLOSE C OPEN O HIGH H LOW L VOL V VOLUME AMOUNT` |
| **行情标量** | `PRICE PE PB TURNOVER MKT_CAP PCT_CHANGE` |
| **财务标量** | `ROE DEBT GROSS_MARGIN REV_YOY NP_YOY` |
| **指标函数** | `MA(S,n) EMA(S,n) STD(S,n) HHV(S,n) LLV(S,n)` |
| **位移函数** | `REF(S,n) DELTA(S,n) PCT_CHG(S,n)` |
| **技术信号** | `MACD_GC(w) MACD_DC(w) RSI(n) KDJ_K(n) KDJ_D(n) CROSS_UP(A,B) CROSS_DOWN(A,B)` |

**安全保证**：AST 节点白名单 + 函数白名单 + `__builtins__` 隔离 + 长度限制 ≤ 2000，不存在 RCE 风险。`__import__("os")` 之类一律被解析阶段拒绝。

---

## 📊 关键 API

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/market/indices` | GET | 7 大指数实时 |
| `/api/market/gainers?limit=20` | GET | 涨幅榜 |
| `/api/market/losers?limit=20` | GET | 跌幅榜 |
| `/api/market/most-active?limit=20` | GET | 活跃榜（按成交额） |
| `/api/stock/{code}` | GET | 个股详情 |
| `/api/stock/{code}/kline?period=daily&days=250` | GET | K 线 |
| `/api/stock/{code}/strategies` | GET | 十大策略评分（综合分） |
| `/api/stock/{code}/f10` | GET | 公司概况 + 十大股东 + 分红 + 同业排名 |
| `/api/screen` | POST | 综合评分选股（支持自定义权重 + 阈值） |
| `/api/screen/conditions` | POST | 条件选股（DSL） |
| `/api/screen/expression` | POST | 表达式选股（AST eval） |
| `/api/backtest` | POST | 回测（含 stockCode 切单股模式） |
| `/api/lhb/recent?days=30` | GET | 近 N 天龙虎榜 |
| `/api/lhb/institution-rank?days=30` | GET | 龙虎榜净买额榜 |
| `/api/lhb/stock-rank?days=30` | GET | 个股上榜频次榜 |
| `/api/moneyflow/main-rank?days=5&direction=inflow` | GET | 主力净流入榜 |
| `/api/moneyflow/northbound-rank` | GET | 北向加仓榜 |
| `/api/moneyflow/sector` | GET | 板块资金流 |
| `/api/strategies-meta` | GET | 十大策略 schema（含可调参数） |
| `/api/condition-fields` | GET | 条件选股 23 字段定义 |
| `/api/expression/help` | GET | 表达式语法 + 函数 + 示例 |

---

## 🛠️ 开发指南

### 加新策略

1. `data-service/strategies/your_strategy.py`：实现 `class YourStrategy(AbstractStrategy)`，定义 `id`、`name`、`default_weight`、`Params`、`score(ctx)` → `ScoreResult`
2. `data-service/strategies/__init__.py`：把类加进 `REGISTRY` + 在 `STRATEGY_PARAM_SPECS` 加可调参数 schema
3. `frontend/src/stores/strategy.ts`：把策略卡片加进 `DEFAULT_STRATEGIES`
4. 重 build data-service + frontend

### 加新数据源

1. `data-service/sources/your_src.py`：实现 `class YourSource(AbstractSource)`，覆写需要的 `fetch_xxx` 方法
2. `data-service/sources/__init__.py`：把源加进对应能力的 `_CHAINS`
3. 重 build data-service

### 加新 API 端点

1. `data-service/api/your_bp.py`：写 Flask blueprint
2. `data-service/app.py`：注册到 blueprint 列表
3. `backend/...Controller.java`：加 Spring 转发
4. `backend/AuthInterceptor.java` 白名单加 path（如果是公开端点）
5. `frontend/src/api/`：加 TS 调用函数

---

## 📈 性能

| 指标 | 数值 |
|---|---|
| 数据库表 | 17 张（基础 + K 线 + 财务 + 资金流 + 北向 + 龙虎榜 + 股东 + 分红 + 概念 + 公告） |
| 日 K 行数 | 74,293 条（top 300 × 250 日） |
| 龙虎榜行数 | 3066 条 / 39 天覆盖 |
| 财务行数 | 1498 条（top 300 × 5 季度） |
| 数据源数 | 7 个（含 4 个 fallback 链） |
| 选股响应 | < 2s（top 200 universe × 十大策略） |
| 单股 K + 策略评分 | < 500ms（含 Redis 缓存命中） |

---

## ⚠️ 已知数据局限

1. **席位类型识别**：东财免费 datacenter LHB 不返 `seat_type`（机构/游资 tag），lhb_followup 策略退化为"按净买额排名"。要拿真实席位需 Tushare Pro 2000 积分。
2. **akshare 部分接口不稳**：EM push2 在高峰时段限流，已加 fallback chain，但 `stock_individual_fund_flow` 仍可能短期 ConnectionError。
3. **同花顺 JS 加密接口**：需要 `ENABLE_PLAYWRIGHT=true` 启用，否则跳过概念板块精细数据。

---

## 📝 路线图

- [x] 数据层重构（多源爬虫 + 反爬 + 持久化 + 调度）
- [x] 十大学术策略
- [x] 矩阵化回测引擎（含单股择时）
- [x] 大盘 / 龙虎榜 / 资金流 / F10 专页
- [x] 策略实验室三档能力（权重+阈值 / 条件 / 表达式）
- [ ] Tushare Pro 接入（席位 + 财务三表 + 业绩快报 / 预告）
- [ ] AI 自然语言选股（同花顺问财式 LLM 接入）
- [ ] 实时 WebSocket 推送（替换轮询）
- [ ] 移动端 PWA 优化
- [ ] 价格预警 + 公告推送

---

## 📄 License

MIT
