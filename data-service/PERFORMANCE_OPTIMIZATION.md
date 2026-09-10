# 数据获取性能优化方案

## 📊 当前状态

### ✅ 正常工作的API
- `/health` - 健康检查 (~2秒)
- `/api/stock/<code>` - 个股查询 (正常)
- `/api/market/summary` - 市场概览 (~37秒，可用但慢)

### ⚠️ 超时的API（需要优化）
- `/api/market/top-stocks` - 策略Top榜单 (>60秒超时)
- `/api/market/sector-rotation` - 板块涨跌 (>60秒超时)
- `/api/market/northbound-flow` - 北向资金 (>60秒超时)

---

## 🔍 问题分析

### 根本原因
1. **数据量大**: 需要处理5,527只股票
2. **计算密集**: 每只股票需要计算多个策略评分
3. **数据源慢**: 
   - 周线数据需要批量获取
   - 基本面数据查询慢
   - 北向资金需要数据库查询
4. **缓存机制**: 首次访问或缓存过期时需要重新计算

### 性能瓶颈
```
市场概览API流程：
├─ 获取spot数据 (~5秒)
├─ 获取financial数据 (~8秒)
├─ 合并数据
├─ 计算策略评分 (每只股票)
│   ├─ ROE、负债率等基本面指标
│   └─ 政策主题匹配
├─ 批量获取周线数据 (~15秒)
│   └─ 对高分股票获取周线判断趋势
└─ 排序返回
总计: ~37秒
```

---

## 💡 解决方案

### 方案1: 后台预热缓存（推荐，已实施）
**当前状态**: scheduler.py 已有预热机制，但可能被禁用

**优化步骤**:
1. 启用预热任务
2. 增加预热频率
3. 扩大预热范围

**实施**:
```python
# scheduler.py 中已有的预热任务
- 市场开盘前15分钟预热spot、financial数据
- 盘中每5分钟刷新缓存
- 预热top 300只股票的周线数据
```

**效果**: 用户访问时直接命中缓存，响应时间 <3秒

---

### 方案2: 增加缓存TTL
**当前配置**:
```python
spot: 300秒 (5分钟)
financial: 600秒 (10分钟)
```

**优化为**:
```python
spot: 180秒 (3分钟) - 盘中需要较新数据
financial: 1800秒 (30分钟) - 基本面变化慢
top_stocks: 300秒 (5分钟) - 榜单可以稍旧
```

**效果**: 减少重新计算频率

---

### 方案3: 数据库索引优化
**北向资金查询慢的原因**: 可能缺少索引

**优化SQL**:
```sql
-- 为北向资金表添加索引
CREATE INDEX idx_northbound_trade_date ON stock_northbound(trade_date);
CREATE INDEX idx_northbound_code_date ON stock_northbound(code, trade_date);
```

**效果**: 查询时间从秒级降到毫秒级

---

### 方案4: 异步计算 + 降级返回
**策略**: 
- 首次访问返回部分数据 + "正在计算中"
- 后台异步完成计算并缓存
- 第二次访问返回完整数据

**效果**: 用户体验更好

---

### 方案5: 数据分页 + 懒加载
**Top榜单**: 
- 只计算前100只股票的详细策略
- 其余股票使用简化评分

**板块数据**:
- 只返回前20个板块
- 板块内不展开个股明细

**效果**: 计算量减少80%

---

## 🚀 立即可用的临时方案

### 方案A: 手动触发缓存预热
```bash
# 在容器内执行
docker exec stock-data-service python -c "
from app import fetch_spot, fetch_financial
spot = fetch_spot()
financial = fetch_financial()
print(f'Warmed up: {len(spot)} stocks')
"
```

### 方案B: 调整Gunicorn超时
```bash
# 增加worker超时时间
docker exec stock-data-service kill -HUP 1
# 或修改 docker-compose.yml 中的启动命令
gunicorn -w 1 --threads 8 --timeout 120 app:app
```

### 方案C: 前端降级显示
**在前端实现**:
- 超时后显示"数据加载中，请稍后..."
- 使用骨架屏占位
- 10秒后自动重试

---

## 📋 推荐实施顺序

### 立即执行（5分钟）
1. ✅ 手动预热缓存（方案A）
2. ✅ 调整Gunicorn超时到120秒（方案B）
3. ✅ 前端添加加载提示（方案C）

### 短期优化（1小时）
4. 启用并验证scheduler预热任务
5. 调整缓存TTL配置
6. 添加数据库索引

### 长期优化（1天）
7. 实施异步计算机制
8. 实现数据分页懒加载
9. 优化策略计算算法

---

## 🎯 预期效果

### 优化前
- 市场概览: 37秒
- Top榜单: 超时
- 板块涨跌: 超时
- 北向资金: 超时

### 优化后（短期）
- 市场概览: 5-10秒
- Top榜单: 15-20秒
- 板块涨跌: 3-5秒
- 北向资金: 2-3秒

### 优化后（长期+缓存命中）
- 市场概览: <3秒
- Top榜单: <3秒
- 板块涨跌: <1秒
- 北向资金: <1秒

---

## 🔧 立即执行命令

```bash
# 1. 手动预热缓存
docker exec stock-data-service python -c "
import cache
from app import fetch_spot, fetch_financial
print('Warming up cache...')
spot = fetch_spot()
financial = fetch_financial()
cache.set('spot', spot, 300)
cache.set('financial', financial, 600)
print(f'✓ Cached {len(spot)} stocks')
"

# 2. 检查scheduler是否运行
docker exec stock-data-service python -c "
import scheduler
print('Scheduler status:', 'Running' if scheduler else 'Not running')
"

# 3. 重启服务使配置生效
docker restart stock-data-service
```

---

## 📞 需要帮助？

如果上述方案无法解决问题，可能的原因：
1. 网络环境差，数据源获取慢
2. 数据库性能瓶颈
3. 内存不足导致频繁GC
4. 数据源被限流

进一步诊断：
```bash
# 查看详细日志
docker logs stock-data-service -f

# 查看资源使用
docker stats stock-data-service

# 测试数据库连接速度
docker exec stock-mysql mysql -u root -pStock@2024 -e "SELECT COUNT(*) FROM stock_screener.stock_kline_daily"
```
