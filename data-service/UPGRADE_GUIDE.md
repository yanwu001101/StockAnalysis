# 数据源稳定性升级方案

## 概述

本次升级实现了一个**多源容错 + 智能降级 + 数据质量验证**的稳定数据系统。

## 核心改进

### 1. 多源聚合器 (`sources/aggregator.py`)
- **自动降级链**: Eastmoney → Tencent → Sina → AkShare → Browser (可选)
- **数据质量验证**: 每个数据源的返回结果都经过验证
- **透明切换**: 自动尝试下一个数据源，无需手动干预

### 2. 增强缓存 (`cache_enhanced.py`)
- **Stale-While-Revalidate**: 数据过期后仍可使用旧缓存
- **优雅降级**: 新数据获取失败时自动返回旧数据
- **三级TTL**: fresh (新鲜) → stale (可用) → expired (过期)

### 3. 健康检查 (`core/health.py`)
- **实时监控**: 跟踪每个数据源的成功率、延迟、可用性
- **智能排序**: 根据健康评分自动调整数据源优先级
- **熔断感知**: 集成现有的熔断器状态

### 4. 浏览器爬虫 (`sources/browser.py`)
- **Playwright驱动**: 使用真实浏览器绕过反爬检测
- **最终后备**: 仅在所有API失败时启用
- **可选功能**: 通过 `ENABLE_PLAYWRIGHT=true` 启用

### 5. 改进的AkShare适配器 (`sources/akshare_src.py`)
- **异步封装**: 使用 `asyncio.to_thread` 避免阻塞
- **更好的列名规范化**: 处理AkShare的多种列名变体
- **更多数据源**: 增加资金流向、北向资金等数据

## 使用方法

### 快速切换到新系统

#### 方法1: 在 `app.py` 中替换导入
```python
# 旧代码
import eastmoney
spot = eastmoney.fetch_all_spot()

# 新代码
from data_service_v2 import fetch_spot
spot = fetch_spot()
```

#### 方法2: 直接使用聚合器 (推荐用于新代码)
```python
from sources.aggregator import default_aggregator

# 异步环境
agg = default_aggregator()
spot = await agg.fetch_spot()
kline = await agg.fetch_kline("600519", "daily", 250)

# 同步环境
from data_service_v2 import fetch_spot, fetch_kline
spot = fetch_spot()
kline = fetch_kline("600519", "daily", 250)
```

### 启用浏览器爬虫后备
```bash
# 1. 安装依赖
pip install playwright
python -m playwright install chromium

# 2. 设置环境变量
export ENABLE_PLAYWRIGHT=true

# 3. 重启服务
```

### 查看数据源健康状态
```python
from data_service_v2 import get_sources_health_sync

health = get_sources_health_sync()
# 输出:
# {
#   "eastmoney": {"available": true, "success_rate": 95.2, "health_score": 87.3},
#   "tencent": {"available": true, "success_rate": 89.1, "health_score": 72.1},
#   ...
# }
```

## 配置参数

### 环境变量
```bash
# HTTP客户端
HTTP_TIMEOUT_S=10                    # 请求超时
HTTP_MAX_CONNECTIONS=64              # 最大连接数
HTTP_CONCURRENCY_DEFAULT=8           # 单域名并发数

# 重试策略
RETRY_MAX_ATTEMPTS=4                 # 最大重试次数
RETRY_BASE_WAIT_S=0.5               # 基础等待时间
RETRY_MAX_WAIT_S=8.0                # 最大等待时间

# 熔断器
CB_FAILURE_THRESHOLD=0.5            # 失败率阈值 (50%)
CB_SAMPLE_WINDOW=20                 # 采样窗口 (最近20次)
CB_OPEN_SECONDS=60                  # 熔断冷却时间

# 限流
RL_JITTER_MIN_MS=50                 # 最小抖动
RL_JITTER_MAX_MS=200                # 最大抖动
RL_COOLDOWN_S=5.0                   # 429后冷却时间
RL_SPEEDUP_AFTER=30                 # 30次成功后提速

# 浏览器爬虫
ENABLE_PLAYWRIGHT=false             # 是否启用浏览器爬虫
```

## 数据质量保证

### Spot数据验证
- ✅ 必须包含 `code` 和 `name` 列
- ✅ 至少3000条记录 (覆盖大部分A股)
- ✅ `price` 字段非空率 > 70%

### K线数据验证
- ✅ 必须包含 `trade_date`, `open`, `close`, `high`, `low`
- ✅ 至少30条记录 (或请求数量的1/5)
- ✅ OHLC字段非空率 > 80%

### 资金流/北向资金验证
- ✅ 非空数据框
- ✅ 至少1条记录
- ✅ 包含必要的时间和金额字段

## 性能优化

### 缓存策略
```python
# 不同数据的TTL设置
spot: 300秒 (5分钟)         # 盘中数据频繁变化
kline_daily: 120秒 (2分钟)   # K线数据较稳定
kline_minute: 60秒 (1分钟)   # 分钟线需要更新快
fundamental: 600秒 (10分钟)  # 基本面数据变化慢
```

### 并发控制
- **单域名限流**: 默认8并发，避免触发反爬
- **自适应速率**: 429/403后自动减速，连续成功后加速
- **智能抖动**: 每次请求间隔50-200ms，模拟人类行为

## 监控和调试

### 日志级别
```python
# 开发环境: 查看详细调试信息
import logging
logging.getLogger("core").setLevel(logging.DEBUG)
logging.getLogger("sources").setLevel(logging.DEBUG)

# 生产环境: 只记录警告和错误
logging.getLogger("core").setLevel(logging.WARNING)
```

### 关键日志
```log
[INFO] aggregator: trying eastmoney.fetch_spot
[INFO] aggregator: eastmoney.fetch_spot succeeded (4521 rows)

[WARNING] aggregator: eastmoney.fetch_spot validation failed: too few rows 2831 < 3000
[WARNING] aggregator: trying tencent.fetch_spot

[INFO] cache hit (fresh): spot_v2 (age=45.2s)
[INFO] cache hit (stale): spot_v2 (age=387.1s), using stale data
[WARNING] fetch failed, using stale cache: spot_v2
```

## 故障排查

### 问题: 所有数据源都失败
**症状**: 返回空DataFrame或旧缓存数据
**排查步骤**:
1. 检查网络连接: `curl https://push2.eastmoney.com`
2. 查看熔断器状态: `get_sources_health_sync()`
3. 检查日志中的具体错误
4. 临时启用浏览器爬虫作为后备

### 问题: 数据不完整
**症状**: 返回的股票数量少于预期
**排查步骤**:
1. 检查数据质量验证日志
2. 降低 `min_rows` 阈值 (临时)
3. 手动测试各数据源
4. 检查上游API是否限流

### 问题: 响应缓慢
**症状**: 请求耗时超过10秒
**排查步骤**:
1. 检查限流器是否过于保守
2. 增加 `HTTP_CONCURRENCY_DEFAULT`
3. 减少 `RL_JITTER_MAX_MS`
4. 检查Redis连接延迟

## 迁移清单

- [ ] 备份现有代码
- [ ] 安装新依赖: `pip install httpx tenacity pydantic-settings`
- [ ] (可选) 安装Playwright: `pip install playwright && playwright install`
- [ ] 更新环境变量配置
- [ ] 在测试环境验证新系统
- [ ] 逐步切换生产流量
- [ ] 监控错误率和响应时间
- [ ] 调整缓存TTL和质量阈值

## 回滚方案

如果新系统出现问题，可以快速回滚:

```python
# 在 app.py 中
USE_V2_DATA_SERVICE = False  # 设为 False 回滚

if USE_V2_DATA_SERVICE:
    from data_service_v2 import fetch_spot, fetch_kline
else:
    # 使用原有的 eastmoney.fetch_all_spot() 等
    import eastmoney
    fetch_spot = eastmoney.fetch_all_spot
```

## 未来改进

1. **代理池集成**: 支持轮换IP绕过限流
2. **WebSocket实时数据**: 减少轮询，降低延迟
3. **机器学习预测**: 预测数据源故障并提前切换
4. **分布式缓存**: 多实例间共享缓存状态
5. **数据一致性校验**: 交叉验证多个数据源的结果

## 技术支持

如有问题，请查看:
- 日志文件: `/var/log/data-service/`
- 监控面板: `/api/metrics`
- 健康检查: `/health`
