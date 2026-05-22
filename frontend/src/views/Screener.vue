<template>
  <div class="page-container screener">
    <header class="page-head rise rise-1">
      <h1>智能选股</h1>
      <p class="dek">设定财务与技术参数，按综合评分输出候选名单。</p>
    </header>

    <section class="card filter-card rise rise-2">
      <header class="card-head">
        <h3>筛选条件</h3>
        <div class="actions">
          <el-button @click="resetFilters">重 置</el-button>
          <el-button type="primary" :loading="loading" @click="runFilter">
            <el-icon style="margin-right: 6px;"><Search /></el-icon>开 始 选 股
          </el-button>
        </div>
      </header>

      <div class="filter-grid">
        <div class="field">
          <span class="field-label">最低综合分</span>
          <el-slider v-model="filters.minScore" :min="0" :max="100" :step="5" show-input input-size="small" />
        </div>
        <div class="field">
          <span class="field-label">最低 ROE (%)</span>
          <el-slider v-model="filters.minRoe" :min="0" :max="40" :step="1" show-input input-size="small" />
        </div>
        <div class="field">
          <span class="field-label">最高负债率 (%)</span>
          <el-slider v-model="filters.maxDebtRatio" :min="10" :max="90" :step="5" show-input input-size="small" />
        </div>
        <div class="field">
          <span class="field-label">最低市值 (亿)</span>
          <el-input-number v-model="filters.minMarketCap" :min="0" :step="50" size="small" />
        </div>
        <div class="field">
          <span class="field-label">行业筛选</span>
          <el-select v-model="filters.industries" multiple collapse-tags placeholder="全部行业" size="small" style="width: 100%;">
            <el-option v-for="ind in industryOptions" :key="ind" :label="ind" :value="ind" />
          </el-select>
        </div>
        <div class="field">
          <span class="field-label">输出数量</span>
          <el-input-number v-model="filters.limit" :min="10" :max="200" :step="10" size="small" />
        </div>
      </div>
    </section>

    <section class="results-area" v-if="results.length">
      <article class="card result-card rise rise-3">
        <header class="card-head">
          <div>
            <h3>筛选结果 <span class="count num">{{ results.length }}</span></h3>
            <p class="card-sub">点击行查看个股详情</p>
          </div>
          <el-button @click="exportResults">
            <el-icon style="margin-right: 6px;"><Download /></el-icon>导 出
          </el-button>
        </header>

        <div class="table-wrap">
          <table class="t-table">
            <thead>
              <tr>
                <th class="t-rank">#</th>
                <th>名称</th>
                <th>代码</th>
                <th>行业</th>
                <th class="t-right">最新价</th>
                <th class="t-center">评分</th>
                <th class="t-right">ROE</th>
                <th class="t-right">负债率</th>
                <th class="t-right">市值</th>
                <th class="t-center">信号</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in results" :key="row.code" class="row" @click="goStock(row)">
                <td class="t-rank num">{{ i + 1 }}</td>
                <td><span class="stock-name">{{ row.name }}</span></td>
                <td class="mono dim">{{ row.code }}</td>
                <td class="dim">{{ row.industry }}</td>
                <td class="t-right num" :class="row.changePercent >= 0 ? 'price-up' : 'price-down'">{{ row.price }}</td>
                <td class="t-center">
                  <span class="score-pill" :class="scoreCls(row.compositeScore)">{{ row.compositeScore }}</span>
                </td>
                <td class="t-right num">{{ row.roe }}%</td>
                <td class="t-right num">{{ row.debtRatio }}%</td>
                <td class="t-right num">{{ row.marketCap?.toFixed(0) }}</td>
                <td class="t-center">
                  <span class="sig" :class="row.signal">{{ sigText(row.signal) }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <aside class="card dist-card rise rise-4">
        <header class="card-head compact"><h3>评分分布</h3></header>
        <div ref="distChartRef" style="height: 280px;"></div>
      </aside>
    </section>

    <div v-if="!loading && !results.length" class="empty-state rise rise-2">
      <p>设置筛选条件后点击「开始选股」</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { runScreener } from '@/api/strategy'
import { useStrategyStore } from '@/stores/strategy'
import { useSettingsStore } from '@/stores/settings'
import { useRefreshable } from '@/composables/useRefreshable'
import * as echarts from 'echarts'

const router = useRouter()
const strategyStore = useStrategyStore()
const settings = useSettingsStore()

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
  limit: settings.defaultLimit,
})

function resetFilters() {
  filters.minScore = 60
  filters.minRoe = 15
  filters.maxDebtRatio = 50
  filters.minMarketCap = 200
  filters.industries = []
  filters.limit = settings.defaultLimit
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
    ElMessage.success(`筛选完成，共 ${results.value.length} 只`)
    nextTick(renderDistChart)
  } catch {
    ElMessage.error('筛选失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

function sigText(s: string) {
  return s === 'bullish' ? '看多' : s === 'bearish' ? '看空' : '中性'
}
function scoreCls(s: number) {
  if (s >= 80) return 'high'
  if (s >= 60) return 'mid'
  return 'low'
}

function chartTokens() {
  const cs = getComputedStyle(document.documentElement)
  return {
    text: cs.getPropertyValue('--text').trim(),
    text3: cs.getPropertyValue('--text-3').trim(),
    line: cs.getPropertyValue('--line').trim(),
    up: cs.getPropertyValue('--up').trim(),
    down: cs.getPropertyValue('--down').trim(),
    warn: cs.getPropertyValue('--warn').trim(),
    bg: cs.getPropertyValue('--surface').trim(),
  }
}

function renderDistChart() {
  if (!distChartRef.value || !results.value.length) return
  const t = chartTokens()
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
    textStyle: { fontFamily: 'system-ui, -apple-system, sans-serif', color: t.text },
    grid: { left: 36, right: 12, top: 16, bottom: 28 },
    xAxis: { type: 'category', data: ranges,
      axisLabel: { color: t.text3, fontSize: 10 },
      axisLine: { lineStyle: { color: t.line } },
      axisTick: { show: false } },
    yAxis: { type: 'value',
      splitLine: { lineStyle: { color: t.line, type: 'dashed' } },
      axisLabel: { color: t.text3, fontSize: 10 },
      axisLine: { show: false }, axisTick: { show: false } },
    series: [{
      type: 'bar',
      data: counts.map((v, i) => ({
        value: v,
        itemStyle: {
          color: [t.up, t.up, t.warn, t.warn, t.down, t.down, t.down][i],
          borderRadius: [4, 4, 0, 0],
        },
      })),
      barWidth: '58%',
    }],
    tooltip: { trigger: 'axis', backgroundColor: t.bg,
      borderColor: t.line, borderWidth: 1, textStyle: { color: t.text } },
  })
}

function goStock(row: any) { router.push(`/stock/${row.code}`) }
function exportResults() { ElMessage.info('导出功能开发中') }

onMounted(() => strategyStore.loadFromStorage())
useRefreshable('综合评分选股', runFilter, { immediate: false, autoRefresh: false })
</script>

<style scoped>
.page-head { margin-bottom: 18px; }
.page-head h1 { font-size: 22px; font-weight: 600; }
.page-head .dek { margin-top: 4px; color: var(--text-3); font-size: 13px; }

.card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 18px 20px 16px;
}
.filter-card { margin-bottom: 16px; }

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}
.card-head.compact { margin-bottom: 8px; }
.card-head h3 { font-size: 16px; font-weight: 600; }
.card-sub { color: var(--text-3); font-size: 12px; margin-top: 2px; }
.count {
  color: var(--brand);
  font-weight: 600;
  margin-left: 4px;
}

.actions { display: flex; gap: 8px; }

.filter-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px 24px;
}
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; color: var(--text-3); }

.results-area {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
}

.table-wrap { margin: 0 -8px; max-height: 600px; overflow-y: auto; }
.t-table {
  width: 100%;
  border-collapse: collapse;
}
.t-table th {
  text-align: left;
  font-weight: 500;
  font-size: 12px;
  color: var(--text-3);
  padding: 10px 8px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  position: sticky;
  top: 0;
  z-index: 1;
}
.t-table td {
  padding: 12px 8px;
  font-size: 14px;
  color: var(--text-2);
  border-bottom: 1px solid var(--line);
}
.t-table tbody tr:last-child td { border-bottom: 0; }
.row { cursor: pointer; transition: background 0.15s ease; }
.row:hover { background: var(--surface-hover); }
.t-rank { width: 36px; color: var(--text-4); }
.t-right { text-align: right; }
.t-center { text-align: center; }
.stock-name { font-weight: 500; color: var(--text); }
.dim { color: var(--text-3); font-size: 13px; }

.score-pill {
  display: inline-block;
  font-size: 12px; font-weight: 600;
  padding: 2px 9px;
  border-radius: var(--radius-pill);
  font-variant-numeric: tabular-nums;
}
.score-pill.high { background: var(--brand-soft); color: var(--brand); }
.score-pill.mid  { background: var(--warn-soft); color: #B88800; }
.score-pill.low  { background: var(--up-soft); color: var(--up); }

.sig {
  font-size: 12px; font-weight: 500;
  padding: 2px 9px;
  border-radius: var(--radius-pill);
}
.sig.bullish { background: var(--up-soft); color: var(--up); }
.sig.bearish { background: var(--down-soft); color: var(--down); }
.sig.neutral { background: var(--surface-2); color: var(--text-3); }

.empty-state {
  text-align: center; padding: 80px 20px;
  color: var(--text-3);
}

@media (max-width: 1100px) {
  .results-area { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
  .filter-grid { grid-template-columns: 1fr; }
}
</style>
