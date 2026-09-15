<template>
  <div class="score-screener">
    <AppCard title="筛选条件" class="filter-card">
      <template #actions>
        <el-button size="small" @click="resetFilters">重 置</el-button>
        <el-button size="small" type="primary" :loading="loading" @click="runFilter">
          <el-icon style="margin-right: 6px;"><Search /></el-icon>开 始 选 股
        </el-button>
      </template>
      <div class="filter-grid">
        <div class="field">
          <span class="field-label">最低综合分</span>
          <el-slider v-model="filters.minScore" :min="0" :max="100" :step="5" :show-input="!isMobile" input-size="small" />
        </div>
        <div class="field">
          <span class="field-label">最低 ROE (%)</span>
          <el-slider v-model="filters.minRoe" :min="0" :max="40" :step="1" :show-input="!isMobile" input-size="small" />
        </div>
        <div class="field">
          <span class="field-label">最高负债率 (%)</span>
          <el-slider v-model="filters.maxDebtRatio" :min="10" :max="90" :step="5" :show-input="!isMobile" input-size="small" />
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
    </AppCard>

    <SnapshotMetaBar v-if="meta" :snapshot="metaSnapshot" :prev="prevHeader" :kline-date="meta.kline_date" :note="metaNote">
      <span v-if="meta.mode === 'snapshot'" class="meta-hint">同一快照下刷新结果不变;下一快照最晚 15 分钟后(交易时段)</span>
    </SnapshotMetaBar>

    <div v-if="results.length || loading" class="results-area">
      <AppCard class="result-card">
        <template #title>筛选结果 <span class="count num">{{ results.length }}</span></template>
        <template #sub>{{ meta?.mode === 'snapshot' ? '实时排名 = 模型当前动态结果,不等于买入建议;买入决策请看「决策」页' : '点击查看个股详情' }}</template>
        <template #actions>
          <SegmentTabs v-model="sortBy" :options="sortOptions" small />
          <el-button v-if="!isMobile" size="small" @click="exportResults">
            <el-icon style="margin-right: 6px;"><Download /></el-icon>导 出
          </el-button>
        </template>
        <StockTable :rows="results" :columns="columns" rank :loading="loading" :max-height="isMobile ? undefined : 600" empty="没有符合条件的股票">
          <template #cell-strategyStats="{ row }">
            <StrategyStatsPill :stats="row.strategyStats" />
          </template>
          <template #cell-proSignal="{ row }">
            <ProSignalPill :signal="row.proSignal" :code="row.code" />
          </template>
          <template #cell-change="{ row }">
            <RankChangeCell :change="row.change" :rank="row.snapshotRank" :composite-now="row.compositeScore" :price="row.price" :prev-slot="prevHeader?.slot" />
          </template>
          <template #cell-buyState="{ row }">
            <el-tag v-if="row.buy" :type="BUY_STATE_TYPE[row.buy.state as BuyState]" size="small" effect="light">{{ row.buy.label }}</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </StockTable>
      </AppCard>

      <AppCard title="评分分布" compact class="dist-card">
        <BaseChart :option="distOption" :height="isMobile ? 200 : 280" :loading="loading" />
      </AppCard>
    </div>

    <EmptyState
      v-else-if="!loading"
      variant="no-results"
      title="没有符合条件的股票"
      description="放宽综合分 / 市值 / 负债率条件后再试"
    >
      <el-button size="small" type="primary" @click="runFilter()">用默认条件重新筛选</el-button>
    </EmptyState>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { EChartsOption } from 'echarts'
import { runScreener } from '@/api/strategy'
import { runScreenerSnapshot, BUY_STATE_TYPE, type BuyState, type ScreenSnapshotMeta, type SnapshotHeader } from '@/api/decision'
import { getStockProSignal } from '@/api/stock'
import { useStrategyStore } from '@/stores/strategy'
import { useSettingsStore } from '@/stores/settings'
import { useRefreshable } from '@/composables/useRefreshable'
import { useDevice } from '@/composables/useDevice'
import { useChartTokens, baseTooltip } from '@/composables/useEcharts'
import type { StockColumn, SegmentOption } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import StockTable from '@/components/stock/StockTable.vue'
import StrategyStatsPill from '@/components/stock/StrategyStatsPill.vue'
import ProSignalPill from '@/components/stock/ProSignalPill.vue'
import BaseChart from '@/components/charts/BaseChart.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import SnapshotMetaBar from '@/components/decision/SnapshotMetaBar.vue'
import RankChangeCell from '@/components/decision/RankChangeCell.vue'

const strategyStore = useStrategyStore()
const settings = useSettingsStore()
const { isMobile } = useDevice()
const tokens = useChartTokens()

const loading = ref(false)
const results = ref<any[]>([])
// 快照口径:results 来自最近一次排名快照(服务端按用户权重重算),同一快照下刷新不变
const meta = ref<ScreenSnapshotMeta | null>(null)
const prevHeader = ref<SnapshotHeader | null>(null)
const metaSnapshot = computed<SnapshotHeader | null>(() => meta.value?.mode === 'snapshot' ? ({
  snapshot_id: meta.value.snapshot_id!, computed_at: meta.value.computed_at!, quote_time: meta.value.quote_time ?? null,
  quote_source: meta.value.quote_source ?? null, universe_n: meta.value.universe_n ?? 0, scored_n: meta.value.scored_n ?? 0,
  trade_date: '', slot: '', buyzone_n: 0, weights_key: meta.value.weights || 'default', elapsed_ms: 0, status: 'ok',
}) : null)
const metaNote = computed(() => {
  if (!meta.value) return null
  if (meta.value.mode === 'live') return '本次为实时计算(未入快照):' + (meta.value.reason || '') + ';刷新可能变化'
  if (meta.value.mode === 'none') return meta.value.reason || '尚无快照,已改为实时计算'
  return null
})
const industryOptions = ref<string[]>([])
type SortKey = 'composite' | 'strategy' | 'pro'
const sortBy = ref<SortKey>('composite')
const sortOptions: SegmentOption<SortKey>[] = [
  { label: '综合评分', value: 'composite' },
  { label: '策略评分', value: 'strategy' },
  { label: '专业信号', value: 'pro' },
]

const columns: StockColumn[] = [
  { key: 'price', label: '最新价', type: 'price', mobile: 'primary' },
  { key: 'changePercent', label: '涨跌幅', type: 'change', mobile: 'primary' },
  { key: 'compositeScore', label: '综合分', type: 'score', align: 'center' },
  { key: 'strategyStats', label: '策略评分', align: 'center', tooltip: '看多策略数 / 有效策略数 · 触发策略数' },
  { key: 'roe', label: 'ROE', type: 'percent', digits: 1 },
  { key: 'debtRatio', label: '负债率', type: 'percent', digits: 1 },
  { key: 'marketCap', label: '市值(亿)', type: 'num', digits: 0, format: r => (r.marketCap > 0 ? r.marketCap : null) },
  { key: 'signal', label: '信号', type: 'signal', align: 'center' },
  { key: 'proSignal', label: '专业信号', align: 'center', tooltip: 'Leading 指标: T+1~T+5 短期方向' },
  { key: 'buyState', label: '买点状态', align: 'center', tooltip: '评分高 ≠ 现在可买:按快照时刻价格与回踩买点区判断;只对综合分前 120 名计算', mobile: 'secondary' },
  { key: 'change', label: 'Δ排名', align: 'center', tooltip: '相对上一快照(同一权重口径)的排名变化;点开看趋势/量价/板块等各组贡献', mobile: 'secondary' },
]

// Defaults are deliberately permissive — composite scores live in the 30-70
// range now that look-ahead is fixed, and a strict 60 floor would empty the
// table. Users can tighten via the sliders.
const filters = reactive({
  minScore: 40,
  minRoe: 8,
  maxDebtRatio: 70,
  minMarketCap: 50,
  industries: [] as string[],
  limit: settings.defaultLimit,
})

function resetFilters() {
  filters.minScore = 40
  filters.minRoe = 8
  filters.maxDebtRatio = 70
  filters.minMarketCap = 50
  filters.industries = []
  filters.limit = settings.defaultLimit
}

async function runFilter(opts?: { silent?: boolean }) {
  const silent = opts?.silent === true
  loading.value = true
  try {
    const req = {
      strategies: strategyStore.getConfigMap(),
      filters: {
        minScore: filters.minScore,
        minMarketCap: filters.minMarketCap,
        maxDebtRatio: filters.maxDebtRatio,
        minRoe: filters.minRoe,
        industries: filters.industries,
      },
      limit: filters.limit,
    }
    // 先走快照口径(确定性 + 带时间戳/数据源/变化拆解);无快照时退回实时计算
    let list: any[] = []
    let snap: { items: any[]; meta: ScreenSnapshotMeta; prev?: SnapshotHeader | null } | null = null
    try { snap = await runScreenerSnapshot(req) } catch { snap = null }
    if (snap && snap.meta?.mode === 'snapshot') {
      list = snap.items
      meta.value = snap.meta
      prevHeader.value = snap.prev || null
    } else {
      list = await runScreener(req)
      meta.value = { mode: snap?.meta?.mode === 'live' ? 'live' : 'none', reason: snap?.meta?.reason }
      prevHeader.value = null
    }
    for (const r of list) r.proSignal = undefined
    results.value = list
    if (!silent) ElMessage.success(`筛选完成，共 ${results.value.length} 只`)
    loadProSignals()
  } catch {
    if (!silent) ElMessage.error('筛选失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function loadProSignals() {
  const concurrency = 6
  let idx = 0
  const worker = async () => {
    while (idx < results.value.length) {
      const i = idx++
      const row = results.value[i]
      try {
        row.proSignal = await getStockProSignal(row.code)
      } catch {
        row.proSignal = null
      }
    }
  }
  await Promise.all(Array(concurrency).fill(0).map(() => worker()))
  applySort()
}

function applySort() {
  // Use [...arr].sort(...) so the ref reference changes — sorting in-place
  // does not always trigger Vue's array tracking.
  const arr = [...results.value]
  if (sortBy.value === 'pro') {
    arr.sort((a, b) => {
      const pa = a.proSignal?.probabilityUp ?? -1
      const pb = b.proSignal?.probabilityUp ?? -1
      if (pa < 0 && pb < 0) return (b.compositeScore || 0) - (a.compositeScore || 0)
      return pb - pa
    })
  } else if (sortBy.value === 'strategy') {
    arr.sort((a, b) => {
      const ba = a.strategyStats?.bullish ?? -1
      const bb = b.strategyStats?.bullish ?? -1
      if (ba !== bb) return bb - ba
      const ta = a.strategyStats?.triggered ?? 0
      const tb = b.strategyStats?.triggered ?? 0
      if (ta !== tb) return tb - ta
      return (b.compositeScore || 0) - (a.compositeScore || 0)
    })
  } else {
    arr.sort((a, b) => (b.compositeScore || 0) - (a.compositeScore || 0))
  }
  results.value = arr
}

const distOption = computed<EChartsOption | null>(() => {
  if (!results.value.length) return null
  const t = tokens.value
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
  const colors = [t.up, t.up, t.warn, t.warn, t.down, t.down, t.down]
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: t.font, color: t.text },
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
      data: counts.map((v, i) => ({ value: v, itemStyle: { color: colors[i], borderRadius: [4, 4, 0, 0] } })),
      barWidth: '58%',
    }],
    tooltip: { trigger: 'axis', ...baseTooltip(t) },
  }
})

function exportResults() { ElMessage.info('导出功能开发中') }

onMounted(() => {
  strategyStore.loadFromStorage()
  // 信息优先：进入页面即按默认条件跑一次（静默），避免筛选区下一整屏空白。
  // keep-alive 回访（已有结果）不重复请求。
  if (!results.value.length) runFilter({ silent: true })
})
watch(sortBy, applySort)
useRefreshable('综合评分选股', runFilter, { immediate: false, autoRefresh: false })
</script>

<style scoped>
.score-screener { display: flex; flex-direction: column; gap: 16px; }
.count { color: var(--brand); font-weight: 600; margin-left: 4px; }
.meta-hint { color: var(--text-4); }
.muted { color: var(--text-4); }
.filter-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px 24px;
}
.field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.field-label { font-size: 12px; color: var(--text-3); }
.results-area {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  align-items: start;
}
@media (max-width: 1100px) {
  .results-area { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .score-screener { gap: 12px; }
  .filter-grid { grid-template-columns: 1fr; gap: 12px; }
  .results-area { gap: 12px; }
}
</style>
