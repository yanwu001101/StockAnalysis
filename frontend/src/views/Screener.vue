<template>
  <div class="page-container">
    <div class="filter-panel glass-card">
      <div class="filter-header">
        <h3>筛选条件</h3>
        <div class="filter-actions">
          <el-button size="small" @click="resetFilters">重置</el-button>
          <el-button type="primary" size="small" :loading="loading" @click="runFilter">
            <el-icon><Search /></el-icon>开始选股
          </el-button>
        </div>
      </div>
      <div class="filter-grid">
        <div class="filter-item">
          <span class="filter-label">最低综合分</span>
          <el-slider v-model="filters.minScore" :min="0" :max="100" :step="5" show-input input-size="small" />
        </div>
        <div class="filter-item">
          <span class="filter-label">最低ROE (%)</span>
          <el-slider v-model="filters.minRoe" :min="0" :max="40" :step="1" show-input input-size="small" />
        </div>
        <div class="filter-item">
          <span class="filter-label">最高负债率 (%)</span>
          <el-slider v-model="filters.maxDebtRatio" :min="10" :max="90" :step="5" show-input input-size="small" />
        </div>
        <div class="filter-item">
          <span class="filter-label">最低市值 (亿)</span>
          <el-input-number v-model="filters.minMarketCap" :min="0" :step="50" size="small" />
        </div>
        <div class="filter-item">
          <span class="filter-label">行业筛选</span>
          <el-select v-model="filters.industries" multiple collapse-tags placeholder="全部行业" size="small" style="width: 100%;">
            <el-option v-for="ind in industryOptions" :key="ind" :label="ind" :value="ind" />
          </el-select>
        </div>
        <div class="filter-item">
          <span class="filter-label">输出数量</span>
          <el-input-number v-model="filters.limit" :min="10" :max="200" :step="10" size="small" />
        </div>
      </div>
    </div>

    <div class="result-area">
      <div class="glass-card result-card" v-if="results.length">
        <div class="card-header">
          <h3>筛选结果 ({{ results.length }}只)</h3>
          <el-button size="small" type="primary" plain @click="exportResults">
            <el-icon><Download /></el-icon>导出
          </el-button>
        </div>
        <el-table :data="results" stripe @row-click="goStock" :row-style="{ cursor: 'pointer' }" size="small" max-height="600">
          <el-table-column type="index" label="排名" width="60" />
          <el-table-column prop="name" label="名称" width="100">
            <template #default="{ row }"><span class="stock-name">{{ row.name }}</span></template>
          </el-table-column>
          <el-table-column prop="code" label="代码" width="80" />
          <el-table-column prop="industry" label="行业" width="100" />
          <el-table-column prop="price" label="最新价" width="80" align="right">
            <template #default="{ row }">
              <span :class="row.changePercent >= 0 ? 'price-up' : 'price-down'">{{ row.price }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="compositeScore" label="综合分" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.compositeScore >= 80 ? 'success' : row.compositeScore >= 60 ? 'warning' : 'danger'" size="small" effect="dark">{{ row.compositeScore }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="roe" label="ROE%" width="80" align="right" />
          <el-table-column prop="debtRatio" label="负债率%" width="80" align="right" />
          <el-table-column prop="marketCap" label="市值(亿)" width="100" align="right">
            <template #default="{ row }">{{ row.marketCap?.toFixed(0) }}</template>
          </el-table-column>
          <el-table-column prop="signal" label="信号" width="70" align="center">
            <template #default="{ row }">
              <span v-if="row.signal === 'bullish'" class="signal bullish">看多</span>
              <span v-else-if="row.signal === 'bearish'" class="signal bearish">看空</span>
              <span v-else class="signal neutral">中性</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="glass-card dist-card" v-if="results.length">
        <h3>评分分布</h3>
        <div ref="distChartRef" style="height: 300px;"></div>
      </div>
    </div>

    <el-empty v-if="!loading && !results.length" description="设置筛选条件后点击「开始选股」" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { runScreener } from '@/api/strategy'
import { useStrategyStore } from '@/stores/strategy'
import * as echarts from 'echarts'

const router = useRouter()
const strategyStore = useStrategyStore()

const loading = ref(false)
const results = ref<any[]>([])
const distChartRef = ref<HTMLElement>()
const industryOptions = ref<string[]>([])

const filters = reactive({
  minScore: 60,
  minRoe: 15,
  maxDebtRatio: 50,
  minMarketCap: 200,
  industries: [] as string[],
  limit: 80,
})

function resetFilters() {
  filters.minScore = 60
  filters.minRoe = 15
  filters.maxDebtRatio = 50
  filters.minMarketCap = 200
  filters.industries = []
  filters.limit = 80
}

async function runFilter() {
  loading.value = true
  try {
    results.value = await runScreener({
      strategies: strategyStore.getConfigMap(),
      filters: {
        minScore: filters.minScore,
        minMarketCap: filters.minMarketCap,
        maxDebtRatio: filters.maxDebtRatio,
        minRoe: filters.minRoe,
        industries: filters.industries,
      },
      limit: filters.limit,
    })
    ElMessage.success(`筛选完成，共 ${results.value.length} 只股票`)
    nextTick(renderDistChart)
  } catch {
    ElMessage.error('筛选失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

function renderDistChart() {
  if (!distChartRef.value || !results.value.length) return
  const chart = echarts.init(distChartRef.value)
  const ranges = ['0-20', '20-40', '40-60', '60-70', '70-80', '80-90', '90-100']
  const counts = [0, 0, 0, 0, 0, 0, 0]
  results.value.forEach(r => {
    const s = r.compositeScore || 0
    if (s < 20) counts[0]++
    else if (s < 40) counts[1]++
    else if (s < 60) counts[2]++
    else if (s < 70) counts[3]++
    else if (s < 80) counts[4]++
    else if (s < 90) counts[5]++
    else counts[6]++
  })
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: ranges, axisLabel: { color: '#8892A4', fontSize: 10 }, axisLine: { lineStyle: { color: '#2A3A4A' } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(42,58,74,0.3)' } }, axisLabel: { color: '#8892A4' } },
    series: [{
      type: 'bar',
      data: counts.map((v, i) => ({ value: v, itemStyle: { color: ['#FF4757','#FF4757','#FFC312','#FFC312','#2AE8A4','#2AE8A4','#00D4FF'][i] } })),
      barWidth: '60%',
    }],
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(15,32,53,0.95)', borderColor: 'rgba(0,212,255,0.2)', textStyle: { color: '#E8EDF3' } },
  })
}

function goStock(row: any) { router.push(`/stock/${row.code}`) }
function exportResults() { ElMessage.info('导出功能开发中') }

onMounted(() => strategyStore.loadFromStorage())
</script>

<style scoped>
.filter-panel { padding: 20px; margin-bottom: 16px; }
.filter-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.filter-header h3 { margin: 0; font-size: 16px; color: var(--text-primary); }
.filter-actions { display: flex; gap: 8px; }
.filter-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.filter-item { display: flex; flex-direction: column; gap: 6px; }
.filter-label { font-size: 13px; color: var(--text-secondary); }
.result-area { display: grid; grid-template-columns: 1fr 320px; gap: 16px; }
.result-card { padding: 20px; }
.dist-card { padding: 20px; }
.dist-card h3 { font-size: 15px; color: var(--text-primary); margin: 0 0 12px 0; }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.card-header h3 { margin: 0; font-size: 16px; color: var(--text-primary); }
.stock-name { font-weight: 600; color: var(--text-primary); }
.signal { font-size: 12px; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
.signal.bullish { background: rgba(255,71,87,0.15); color: #FF4757; }
.signal.bearish { background: rgba(42,232,164,0.15); color: #2AE8A4; }
.signal.neutral { background: rgba(136,146,164,0.15); color: #8892A4; }
@media (max-width: 1200px) { .result-area { grid-template-columns: 1fr; } .filter-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
