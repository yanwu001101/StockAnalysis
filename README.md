# A股智能选股平台

全栈量化选股平台，支持十大策略评分、用户自定义策略、自选股管理、策略回测。

## 技术栈

| 层 | 技术 |
|---|------|
| **前端** | Vue 3 + TypeScript + Element Plus + ECharts + Pinia |
| **后端** | Java 17 + Spring Boot 3 + MyBatis-Plus |
| **数据服务** | Python + Flask + akshare |
| **数据库** | MySQL 8 + Redis |
| **部署** | Docker Compose + Nginx |

## 十大策略

| # | 策略 | 权重 |
|---|------|------|
| 1 | MACD + 均线趋势共振 | 12% |
| 2 | 多因子价值投资 | 25% |
| 3 | 动量突破策略 | 10% |
| 4 | RSI 超卖反弹 | 8% |
| 5 | 布林带收口突破 | 8% |
| 6 | 筹码集中 + 机构增持 | 10% |
| 7 | 股息率 + 分红稳定性 | 8% |
| 8 | 北向资金流入 | 7% |
| 9 | 行业轮动策略 | 7% |
| 10 | KDJ + RSI 双指标共振 | 5% |

## 快速启动

### Docker 一键部署（推荐）

```bash
# 克隆项目
git clone <repo-url>
cd 股票分析

# 启动所有服务
docker-compose up -d

# 访问 http://localhost
```

### 本地开发

```bash
# 1. 启动数据服务
cd data-service
pip install -r requirements.txt
python app.py

# 2. 启动后端
cd backend
mvn spring-boot:run

# 3. 启动前端
cd frontend
npm install
npm run dev
# 访问 http://localhost:3000
```

## 项目结构

```
stock-screener/
├── frontend/          # Vue 3 前端
├── backend/           # Java Spring Boot 后端
├── data-service/      # Python 数据采集服务
├── docker-compose.yml # Docker 编排
└── stock_screener.py  # 原始 CLI 筛选器（保留）
```

## 功能

- **智能选股**: 十大策略综合评分，一键筛选优质股票
- **个股详情**: K线图、策略雷达图、财务指标一览
- **策略实验室**: 自定义策略权重，打造专属选股模型
- **自选股**: 分组管理自选股，实时跟踪评分变化
- **策略回测**: 历史数据验证策略有效性

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| DB_PASSWORD | Stock@2024 | MySQL 密码 |
| REDIS_HOST | localhost | Redis 地址 |
| JWT_SECRET | (内置) | JWT 签名密钥 |
| DATA_SERVICE_URL | http://localhost:5000 | 数据服务地址 |

---

> 原始 CLI 筛选器 (`stock_screener.py`) 保留不动，可独立使用：
> ```powershell
> python .\stock_screener.py --roe 20 --min-score 70
> ```
