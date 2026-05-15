<template>
  <div class="page-container">
    <div class="summary-cards">
      <div class="glass-card stat-card" v-for="card in summaryCards" :key="card.label">
        <div class="stat-icon" :style="{ background: card.bgColor }">
          <el-icon :size="24" :color="card.color"><component :is="card.icon" /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
          <div class="stat-label">{{ card.label }}</div>
        </div>
      </div>
    </div>

    <div class="main-grid">
      <div class="glass-card top-stocks-card">
        <div class="card-header">
          <h3>Top 10 高分股票</h3>
          <el-button text type="primary" @click="$router.push('/screener')">查看全部</el-button>
        </div>
        <el-table :data="topStocks" stripe style="width: 100%" @row-click="goStock"
          :row-style="{ cursor: 'pointer' }" size="small">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column prop="name" label="名称" width="100">
            <template #default="{ row }">
              <span class="stock-name">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="code" label="代码" width="80" />
          <el-table-column prop="industry" label="行业" width="100" />
          <el-table-column prop="price" label="最新价" width="80" align="right">
            <template #default="{ row }">
              <span :class="row.change >= 0 ? 'price-up' : 'price-down'">{{ row.price }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="changePercent" label="涨跌幅" width="80" align="right">
            <template #default="{ row }">
              <span :class="row.changePercent >= 0 ? 'price-up' : 'price-down'">
                {{ row.changePercent >= 0 ? '+' : '' }}{{ row.changePercent }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="compositeScore" label="综合分" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.compositeScore >= 80 ? 'success' : row.compositeScore >= 60 ? 'warning' : 'danger'" size="small" effect="dark">
                {{ row.compositeScore }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="信号" width="70" align="center">
            <template #default="{ row }">
              <span v-if="row.signal === 'bullish'" class="signal bullish">看多</span>
              <span v-else-if="row.signal === 'bearish'" class="signal bearish">看空</span>
              <span v-else class="signal neutral">中性</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="side-charts">
        <div class="glass-card chart-card">
          <div class="card-header">
            <h3>北向资金流向</h3>
          </div>
          <div ref="northboundChartRef" style="height: 220px;"></div>
        </div>
        <div class="glass-card chart-card">
          <div class="card-header">
            <h3>板块轮动</h3>
          </div>
          <div ref="sectorChartRef" style="height: 220px;"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useMarketStore } from '@/stores/market'
import * as echarts from 'echarts'

const router = useRouter()
const marketStore = useMarketStore()

const northboundChartRef = ref<HTMLElement>()
const sectorChartRef = ref<HTMLElement>()

const topStocks = computed(() => marketStore.topStocks || [])

const summaryCards = computed(() => {
  const s = marketStore.summary
  return [
    { label: '上涨', value: s?.upCount ?? '--', icon: 'Top', color: '#FF4757', bgColor: 'rgba(255,71,87,0.1)' },
    { label: '下跌', value: s?.downCount ?? '--', icon: 'Bottom', color: '#2AE8A4', bgColor: 'rgba(42,232,164,0.1)' },
    { label: '北向净流入', value: s ? (s.northboundFlow / 10000).toFixed(1) + '亿' : '--', icon: 'Guide', color: '#00D4FF', bgColor: 'rgba(0,212,255,0.1)' },
    { label: '热门板块', value: s?.hotSectors?.[0]?.name ?? '--', icon: 'TrendCharts', color: '#FFC312', bgColor: 'rgba(255,195,18,0.1)' },
  ]
})

function goStock(row: any) {
  router.push(`/stock/${row.code}`)
}

onMounted(async () => {
  await marketStore.fetchAll()
  nextTick(() => {
    if (northboundChartRef.value && marketStore.northboundFlow.length) {
      const chart = echarts.init(northboundChartRef.value)
      chart.setOption({
        backgroundColor: 'transparent',
        grid: { left: 50, right: 20, top: 20, bottom: 30 },
        xAxis: { type: 'category', data: marketStore.northboundFlow.map((d: any) => d.date), axisLabel: { color: '#8892A4', fontSize: 10 }, axisLine: { lineStyle: { color: '#2A3A4A' } } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(42,58,74,0.3)' } }, axisLabel: { color: '#8892A4', fontSize: 10 } },
        series: [{
          type: 'bar',
          data: marketStore.northboundFlow.map((d: any) => ({
            value: d.netFlow,
            itemStyle: { color: d.netFlow >= 0 ? '#FF4757' : '#2AE8A4' },
          })),
        }],
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(15,32,53,0.95)', borderColor: 'rgba(0,212,255,0.2)', textStyle: { color: '#E8EDF3' } },
      })
    }
    if (sectorChartRef.value && marketStore.sectors.length) {
      const chart = echarts.init(sectorChartRef.value)
      const sorted = [...marketStore.sectors].sort((a, b) => b.change - a.change).slice(0, 10)
      chart.setOption({
        backgroundColor: 'transparent',
        grid: { left: 80, right: 30, top: 10, bottom: 20 },
        xAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(42,58,74,0.3)' } }, axisLabel: { color: '#8892A4', fontSize: 10 } },
        yAxis: { type: 'category', data: sorted.map(s => s.name).reverse(), axisLabel: { color: '#8892A4', fontSize: 11 } },
        series: [{
          type: 'bar',
          data: sorted.map(s => s.change).reverse(),
          itemStyle: {
            color: (params: any) => {
              const val = sorted[sorted.length - 1 - params.dataIndex]?.change || 0
              return val >= 0 ? '#FF4757' : '#2AE8A4'
            },
          },
          barWidth: 14,
        }],
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(15,32,53,0.95)', borderColor: 'rgba(0,212,255,0.2)', textStyle: { color: '#E8EDF3' } },
      })
    }
  })
})
</script>

<style scoped>
.summary-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}
.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
}
.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-value {
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.stat-label {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 2px;
}
.main-grid {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 16px;
}
.top-stocks-card {
  padding: 20px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.card-header h3 {
  font-size: 16px;
  color: var(--text-primary);
  margin: 0;
}
.stock-name {
  font-weight: 600;
  color: var(--text-primary);
}
.signal {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
}
.signal.bullish { background: rgba(255,71,87,0.15); color: #FF4757; }
.signal.bearish { background: rgba(42,232,164,0.15); color: #2AE8A4; }
.signal.neutral { background: rgba(136,146,164,0.15); color: #8892A4; }
.side-charts {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.chart-card {
  padding: 16px;
}
@media (max-width: 1200px) {
  .main-grid { grid-template-columns: 1fr; }
  .summary-cards { grid-template-columns: repeat(2, 1fr); }
}
</style>
