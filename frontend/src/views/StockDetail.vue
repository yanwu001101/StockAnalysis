<template>
  <div class="page-container">
    <div class="stock-header glass-card">
      <div class="header-left">
        <h2 class="stock-title">
          <span class="stock-name">{{ stockInfo.name }}</span>
          <span class="stock-code">{{ stockInfo.code }}</span>
          <el-tag size="small" type="info">{{ stockInfo.industry }}</el-tag>
        </h2>
        <div class="price-row">
          <span class="current-price" :class="stockInfo.change >= 0 ? 'price-up' : 'price-down'">
            {{ stockInfo.price }}
          </span>
          <span class="price-change" :class="stockInfo.change >= 0 ? 'price-up' : 'price-down'">
            {{ stockInfo.change >= 0 ? '+' : '' }}{{ stockInfo.change }}
            ({{ stockInfo.changePercent >= 0 ? '+' : '' }}{{ stockInfo.changePercent }}%)
          </span>
        </div>
      </div>
      <div class="header-right">
        <ScoreGauge :score="compositeScore" :size="90" />
        <div class="action-btns">
          <el-button type="primary" plain size="small" @click="addToWatchlist">
            <el-icon><Star /></el-icon>加自选
          </el-button>
          <el-button size="small" @click="$router.back()">返回</el-button>
        </div>
      </div>
    </div>

    <div class="content-grid">
      <div class="glass-card kline-card">
        <div class="card-header">
          <h3>K线图</h3>
          <el-radio-group v-model="klinePeriod" size="small">
            <el-radio-button label="daily">日K</el-radio-button>
            <el-radio-button label="weekly">周K</el-radio-button>
          </el-radio-group>
        </div>
        <KLineChart :data="klineData" :height="480" />
      </div>

      <div class="strategy-panel">
        <div class="glass-card radar-card">
          <h3>策略评分雷达</h3>
          <RadarChart :indicators="radarIndicators" :values="radarValues" :height="280" />
        </div>

        <div class="glass-card detail-card">
          <h3>核心指标</h3>
          <div class="metrics-grid">
            <div class="metric-item" v-for="m in coreMetrics" :key="m.label">
              <span class="metric-label">{{ m.label }}</span>
              <span class="metric-value" :style="{ color: m.color }">{{ m.value }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="glass-card strategies-card">
      <h3>十大策略评分详情</h3>
      <div class="strategy-grid">
        <div class="strategy-item glass-card" v-for="(score, id) in strategyScores" :key="id">
          <div class="strategy-header">
            <span class="strategy-name">{{ getStrategyName(id) }}</span>
            <el-tag :type="getScoreType(score)" size="small" effect="dark">{{ score }}</el-tag>
          </div>
          <el-progress :percentage="score" :color="getProgressColor(score)" :show-text="false" :stroke-width="6" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getStockDetail, getStockKLine, getStockStrategies } from '@/api/stock'
import { addToWatchlist as addWatchlistApi } from '@/api/user'
import { useStrategyStore } from '@/stores/strategy'
import KLineChart from '@/components/charts/KLineChart.vue'
import RadarChart from '@/components/charts/RadarChart.vue'
import ScoreGauge from '@/components/charts/ScoreGauge.vue'
import type { KLineData } from '@/types'

const route = useRoute()
const strategyStore = useStrategyStore()

const code = computed(() => route.params.code as string)
const stockInfo = ref<any>({})
const klineData = ref<KLineData[]>([])
const klinePeriod = ref('daily')
const compositeScore = ref(0)
const strategyScores = ref<Record<string, number>>({})

const radarIndicators = computed(() =>
  strategyStore.strategies.map(s => ({ name: s.name, max: 100 }))
)
const radarValues = computed(() =>
  strategyStore.strategies.map(s => strategyScores.value[s.id] || 0)
)

const coreMetrics = computed(() => [
  { label: 'ROE', value: (stockInfo.value.roe ?? '--') + '%', color: '#00D4FF' },
  { label: '负债率', value: (stockInfo.value.debtRatio ?? '--') + '%', color: '#FFC312' },
  { label: '现金流', value: stockInfo.value.cashFlowPerShare ?? '--', color: '#2AE8A4' },
  { label: '营收增长', value: (stockInfo.value.revenueGrowth ?? '--') + '%', color: '#A78BFA' },
  { label: '净利润增长', value: (stockInfo.value.profitGrowth ?? '--') + '%', color: '#FF9F43' },
  { label: '毛利率', value: (stockInfo.value.grossMargin ?? '--') + '%', color: '#FF6B81' },
  { label: 'PE', value: stockInfo.value.pe ?? '--', color: '#48DBFB' },
  { label: 'PB', value: stockInfo.value.pb ?? '--', color: '#FECA57' },
])

function getStrategyName(id: string) {
  return strategyStore.strategies.find(s => s.id === id)?.name || id
}
function getScoreType(score: number) {
  return score >= 80 ? 'success' : score >= 60 ? 'warning' : 'danger'
}
function getProgressColor(score: number) {
  return score >= 80 ? '#2AE8A4' : score >= 60 ? '#FFC312' : '#FF4757'
}

async function addToWatchlist() {
  try {
    await addWatchlistApi(0, code.value)
    ElMessage.success('已加入自选股')
  } catch {}
}

async function loadData() {
  const c = code.value
  if (!c) return
  try {
    const [detail, kline, strategies] = await Promise.allSettled([
      getStockDetail(c),
      getStockKLine(c, klinePeriod.value, 250),
      getStockStrategies(c),
    ])
    if (detail.status === 'fulfilled') stockInfo.value = detail.value
    if (kline.status === 'fulfilled') klineData.value = kline.value
    if (strategies.status === 'fulfilled') {
      const s = strategies.value as any
      compositeScore.value = s.total || 0
      strategyScores.value = {}
      Object.entries(s.strategies || {}).forEach(([k, v]: [string, any]) => {
        strategyScores.value[k] = v.score || 0
      })
    }
  } catch {}
}

watch(() => code.value, loadData)
watch(klinePeriod, () => getStockKLine(code.value, klinePeriod.value, 250).then(d => klineData.value = d))

onMounted(loadData)
</script>

<style scoped>
.stock-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  margin-bottom: 16px;
}
.stock-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 8px 0;
}
.stock-name { font-size: 20px; color: var(--text-primary); }
.stock-code { font-size: 14px; color: var(--text-muted); }
.current-price { font-size: 28px; font-weight: 700; margin-right: 12px; }
.price-change { font-size: 15px; }
.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}
.action-btns { display: flex; flex-direction: column; gap: 8px; }
.content-grid {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  margin-bottom: 16px;
}
.kline-card { padding: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.card-header h3 { font-size: 15px; color: var(--text-primary); margin: 0; }
.strategy-panel { display: flex; flex-direction: column; gap: 16px; }
.radar-card { padding: 16px; }
.radar-card h3 { font-size: 15px; color: var(--text-primary); margin: 0 0 8px 0; }
.detail-card { padding: 16px; }
.detail-card h3 { font-size: 15px; color: var(--text-primary); margin: 0 0 12px 0; }
.metrics-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.metric-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid rgba(0,212,255,0.06); }
.metric-label { font-size: 13px; color: var(--text-secondary); }
.metric-value { font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; }
.strategies-card { padding: 20px; }
.strategies-card h3 { font-size: 16px; color: var(--text-primary); margin: 0 0 16px 0; }
.strategy-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.strategy-item { padding: 14px; }
.strategy-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.strategy-name { font-size: 13px; color: var(--text-secondary); }
@media (max-width: 1200px) { .content-grid { grid-template-columns: 1fr; } }
</style>
