<template>
  <div class="backtest-panel" :class="{ mobile: isMobile }">
    <div class="config-col">
      <AppCard title="回测参数" sub="基于历史数据验证策略有效性">
        <el-form label-position="top" size="small" class="config-form">
          <SegmentTabs v-model="mode" :options="modeOptions" small style="margin-bottom: 12px;" />

          <template v-if="mode === 'strategy'">
            <el-form-item label="股票代码 (留空=组合回测)">
              <el-input v-model="config.stockCode" placeholder="例如 600519，留空跑十大策略组合" clearable>
                <template #append v-if="config.stockCode">单股择时</template>
              </el-input>
            </el-form-item>
            <el-form-item label="策略">
              <el-select v-model="config.strategyId" style="width: 100%;">
                <el-option v-for="s in strategyStore.strategies" :key="s.id" :label="s.name" :value="s.id" />
              </el-select>
            </el-form-item>
          </template>

          <template v-else>
            <el-form-item label="因子表达式（截面 alpha，t 收盘出信号 → t+1 开盘成交）">
              <AlphaExprInput v-model="config.expression" :rows="3" />
            </el-form-item>
          </template>

          <div class="date-row">
            <el-form-item label="开始日期">
              <el-date-picker v-model="config.startDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 100%;" />
            </el-form-item>
            <el-form-item label="结束日期">
              <el-date-picker v-model="config.endDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 100%;" />
            </el-form-item>
          </div>
          <div class="date-row">
            <el-form-item label="调仓频率">
              <el-select v-model="config.rebalance" style="width: 100%;">
                <el-option label="日度" value="daily" />
                <el-option label="周度" value="weekly" />
                <el-option label="月度" value="monthly" />
              </el-select>
            </el-form-item>
            <el-form-item label="初始资金 (万元)">
              <el-input-number v-model="config.initialCapital" :min="10" :max="10000" :step="10" style="width: 100%;" />
            </el-form-item>
          </div>
          <div class="date-row">
            <el-form-item label="每期选股数量" v-if="!config.stockCode">
              <el-input-number v-model="config.topN" :min="1" :max="50" :step="1" style="width: 100%;" />
            </el-form-item>
          </div>
          <el-button type="primary" :loading="loading" @click="runTest" style="width: 100%;">
            <el-icon><TrendCharts /></el-icon>{{ mode === 'factor' ? '回测自定义因子' : '开始回测' }}
          </el-button>
        </el-form>
      </AppCard>

      <AppCard v-if="userStore.isLoggedIn && savedList.length" compact>
        <template #title>已保存回测 <span class="saved-count">{{ savedList.length }}</span></template>
        <div class="saved-list">
          <div v-for="item in savedList" :key="item.id" class="saved-item">
            <div class="saved-main" @click="loadSaved(item)">
              <div class="saved-name" :title="item.name">{{ item.name }}</div>
              <div class="saved-meta">
                <ChangeText :value="item.totalReturn * 100" :digits="1" />
                <span class="saved-date">{{ fmtDate(item.createdAt) }}</span>
              </div>
            </div>
            <el-icon class="saved-del" @click.stop="removeSaved(item)"><Delete /></el-icon>
          </div>
        </div>
      </AppCard>
    </div>

    <div class="result-area" v-if="result">
      <AppCard title="回测结果">
        <template #actions>
          <el-button size="small" type="success" plain @click="saveCurrent">
            <el-icon><Star /></el-icon>&nbsp;保存
          </el-button>
        </template>
        <StatGrid :items="metricItems" :cols="isMobile ? 2 : 3" />
      </AppCard>

      <AppCard v-if="(result as any).picks?.length" title="本次回测选股"
               :sub="mode === 'factor' ? '按因子值降序 TopN（最近一个调仓期）' : '按策略综合分排名'">
        <div class="picks-grid">
          <span v-for="(code, idx) in (result as any).picks" :key="code" class="pick-chip"
                @click="$router.push(stockPath(code))">
            <span class="pick-rank">{{ idx + 1 }}</span>
            <span class="pick-code num">{{ code }}</span>
          </span>
        </div>
      </AppCard>

      <AppCard title="收益曲线" compact>
        <BaseChart :option="curveOption" :height="isMobile ? 240 : 350" />
      </AppCard>

      <AppCard v-if="(result as any).trades?.length">
        <template #title>交易明细 <span class="trades-count">共 {{ (result as any).trades.length }} 笔</span></template>
        <template #actions>
          <SegmentTabs v-model="tradeSideFilter" :options="sideOptions" small />
        </template>
        <StockTable
          :rows="filteredTrades"
          :columns="tradeColumns"
          :stock="false"
          :max-height="isMobile ? undefined : 420"
          dense
          row-key="date"
          :to="(row: any) => (row.code ? stockPath(row.code) : null)"
        >
          <template #cell-side="{ row }">
            <span :class="['side-tag', row.side]">{{ row.side === 'buy' ? '买入' : row.side === 'sell' ? '卖出' : row.side }}</span>
          </template>
        </StockTable>
      </AppCard>
    </div>

    <el-empty v-if="!loading && !result && !isMobile" description="设置回测参数后点击「开始回测」" class="empty-hint" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { EChartsOption } from 'echarts'
import * as echarts from 'echarts'
import { runBacktest, runAlphaBacktest, saveBacktest, listSavedBacktests, getSavedBacktest, deleteSavedBacktest } from '@/api/strategy'
import AppCard from '@/components/ui/AppCard.vue'
import StatGrid from '@/components/ui/StatGrid.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import StockTable from '@/components/stock/StockTable.vue'
import ChangeText from '@/components/stock/ChangeText.vue'
import BaseChart from '@/components/charts/BaseChart.vue'
import AlphaExprInput from '@/components/screener/AlphaExprInput.vue'
import { useStrategyStore } from '@/stores/strategy'
import { useUserStore } from '@/stores/user'
import { useRefreshable } from '@/composables/useRefreshable'
import { useDevice } from '@/composables/useDevice'
import { useChartTokens, baseTooltip, hexToRgba } from '@/composables/useEcharts'
import { stockPath } from '@/utils/score'
import type { BacktestResult, SavedBacktestSummary } from '@/types'
import type { StockColumn, StatItem, SegmentOption } from '@/types/ui'

const strategyStore = useStrategyStore()
const userStore = useUserStore()
const { isMobile } = useDevice()
const tokens = useChartTokens()

const loading = ref(false)
const result = ref<BacktestResult | null>(null)
type Side = 'all' | 'buy' | 'sell'
const tradeSideFilter = ref<Side>('all')
const sideOptions: SegmentOption<Side>[] = [
  { label: '全部', value: 'all' }, { label: '仅买入', value: 'buy' }, { label: '仅卖出', value: 'sell' },
]
const lastRequest = ref<any>(null)              // 最近一次发给 /backtest 的请求体,保存时一并落库
const savedList = ref<SavedBacktestSummary[]>([])

const tradeColumns: StockColumn[] = [
  { key: 'date', label: '日期', mobile: 'title' },
  { key: 'code', label: '代码', mobile: 'secondary' },
  { key: 'side', label: '方向', align: 'center', mobile: 'primary' },
  { key: 'price', label: '价格', type: 'num', digits: 2 },
  { key: 'shares', label: '股数', type: 'num', digits: 0 },
  { key: 'pnl', label: '盈亏', type: 'num', digits: 0, colored: true, mobile: 'primary' },
  { key: 'reason', label: '备注', format: r => (r.reason === 'end_of_window' ? '期末强平' : ''), mobile: 'hidden' },
]

const filteredTrades = computed(() => {
  const all = ((result.value as any)?.trades ?? []) as any[]
  if (tradeSideFilter.value === 'all') return all
  return all.filter(t => t.side === tradeSideFilter.value)
})

const metricItems = computed<StatItem[]>(() => {
  const r = result.value
  if (!r) return []
  const pct = (v: number, d = 2) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`
  const items: StatItem[] = [
    { label: '总收益率', value: pct(r.totalReturn), cls: r.totalReturn >= 0 ? 'price-up' : 'price-down' },
    { label: '年化收益率', value: pct(r.annualizedReturn), cls: r.annualizedReturn >= 0 ? 'price-up' : 'price-down' },
    { label: '最大回撤', value: `-${(r.maxDrawdown * 100).toFixed(2)}%`, cls: 'price-down' },
    { label: '夏普比率', value: r.sharpeRatio.toFixed(2), cls: 'brand-text' },
    { label: '胜率', value: `${(r.winRate * 100).toFixed(1)}%`, cls: 'warn-text' },
    { label: '交易次数', value: r.tradeCount },
  ]
  if (r.benchmarkReturn != null) {
    items.push({ label: '基准 (沪深300)', value: pct(r.benchmarkReturn), cls: r.benchmarkReturn >= 0 ? 'price-up' : 'price-down' })
  }
  if (r.excessReturn != null) {
    items.push({ label: '超额收益', value: pct(r.excessReturn), cls: r.excessReturn >= 0 ? 'price-up' : 'price-down' })
  }
  if (r.turnoverRate != null) {
    items.push({ label: '年化换手率', value: `${(r.turnoverRate * 100).toFixed(0)}%` })
  }
  if (r.totalCosts != null) {
    items.push({ label: '交易成本合计', value: `${(r.totalCosts / 10000).toFixed(2)} 万`, cls: 'price-down' })
  }
  return items
})

const config = reactive({
  stockCode: '',
  strategyId: 'quality_factor',
  startDate: '2025-01-01',
  endDate: '2025-12-31',
  initialCapital: 100,
  topN: 10,
  rebalance: 'weekly',
  expression: '',
})

// ---- 回测模式:内置策略 / 自定义因子(WorldQuant 式表达式) ----
type BtMode = 'strategy' | 'factor'
const mode = ref<BtMode>('strategy')
const modeOptions: SegmentOption<BtMode>[] = [
  { label: '策略回测', value: 'strategy' },
  { label: '因子回测', value: 'factor' },
]

async function runTest() {
  if (mode.value === 'factor' && !config.expression.trim()) {
    ElMessage.warning('请输入因子表达式')
    return
  }
  loading.value = true
  try {
    if (mode.value === 'factor') {
      result.value = await runAlphaBacktest({
        expression: config.expression.trim(),
        startDate: config.startDate,
        endDate: config.endDate,
        initialCapital: config.initialCapital * 10000,    // 万元 -> 元
        topN: config.topN,
        rebalance: config.rebalance,
      })
      lastRequest.value = {
        mode: 'factor',
        expression: config.expression.trim(),
        startDate: config.startDate,
        endDate: config.endDate,
        initialCapital: config.initialCapital * 10000,
        topN: config.topN,
        rebalance: config.rebalance,
      }
      ElMessage.success('因子回测完成')
      return
    }
    const body: any = {
      strategyId: config.strategyId,
      startDate: config.startDate,
      endDate: config.endDate,
      initialCapital: config.initialCapital * 10000,    // 万元 -> 元
      rebalance: config.rebalance,
    }
    if (config.stockCode.trim()) {
      body.stockCode = config.stockCode.trim().padStart(6, '0')
    } else {
      body.topN = config.topN
      body.strategyConfig = strategyStore.getConfigMap()
    }
    result.value = await runBacktest(body)
    lastRequest.value = body
    ElMessage.success(config.stockCode ? `${config.stockCode} 择时回测完成` : '组合回测完成')
  } catch {
    ElMessage.error('回测失败')
  } finally {
    loading.value = false
  }
}

const curveOption = computed<EChartsOption | null>(() => {
  const data = result.value?.equityCurve
  if (!data?.length) return null
  const t = tokens.value
  const bench = (result.value as any)?.benchmarkCurve as { date: string; value: number }[] | undefined
  const series: any[] = [{
    type: 'line',
    data: data.map(d => d.value),
    smooth: true,
    symbol: 'none',
    name: '策略净值',
    lineStyle: { color: t.brand, width: 2 },
    areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: hexToRgba(t.brand, 0.18) },
      { offset: 1, color: hexToRgba(t.brand, 0.02) },
    ]) },
  }]
  if (bench?.length) {
    series.push({
      type: 'line',
      data: bench.map(d => d.value),
      smooth: true,
      symbol: 'none',
      name: '沪深300',
      lineStyle: { color: t.series[5] || t.text3, width: 1.5, type: 'dashed' },
    })
  }
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: t.font },
    legend: bench?.length
      ? { data: ['策略净值', '沪深300'], top: 0, right: 8, textStyle: { color: t.text3, fontSize: 11 }, itemWidth: 16 }
      : undefined,
    grid: { left: 60, right: 24, top: bench?.length ? 32 : 20, bottom: 40 },
    xAxis: { type: 'category', data: data.map(d => d.date),
      axisLabel: { color: t.text3, fontSize: 10 },
      axisLine: { lineStyle: { color: t.line } } },
    yAxis: { type: 'value',
      splitLine: { lineStyle: { color: t.line } },
      axisLabel: { color: t.text3 } },
    series,
    tooltip: { trigger: 'axis', ...baseTooltip(t) },
  }
})

// ---- 保存 / 历史 ----

function defaultName(): string {
  const stratName = strategyStore.strategies.find(s => s.id === config.strategyId)?.name || config.strategyId
  const prefix = config.stockCode ? `${config.stockCode} ` : ''
  return `${prefix}${stratName} ${config.startDate}~${config.endDate}`
}

async function saveCurrent() {
  const snapshot = result.value
  if (!snapshot) return
  if (!userStore.isLoggedIn) {
    ElMessage.warning('请先登录后再保存回测')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt('给这次回测起个名字', '保存回测', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: defaultName(),
      inputValidator: (v: string) => (!!v && v.trim().length > 0) || '名字不能为空',
    })
    await saveBacktest({ name: value.trim(), request: lastRequest.value, result: snapshot })
    ElMessage.success('已保存')
    await refreshSaved()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error('保存失败')
  }
}

async function refreshSaved() {
  if (!userStore.isLoggedIn) { savedList.value = []; return }
  try {
    savedList.value = await listSavedBacktests()
  } catch { /* 静默,不打扰回测主流程 */ }
}

async function loadSaved(item: SavedBacktestSummary) {
  try {
    const detail = await getSavedBacktest(item.id)
    result.value = detail.result
    // 回填配置标量,方便对照;故意不动全局策略权重 store(避免覆盖用户当前调参)
    const req = detail.request || {}
    config.stockCode = req.stockCode || item.stockCode || ''
    config.strategyId = req.strategyId || item.strategyId || config.strategyId
    config.startDate = item.startDate || config.startDate
    config.endDate = item.endDate || config.endDate
    if (req.initialCapital) config.initialCapital = req.initialCapital / 10000
    if (req.topN) config.topN = req.topN
    tradeSideFilter.value = 'all'
    ElMessage.success(`已载入「${item.name}」`)
  } catch {
    ElMessage.error('载入失败')
  }
}

async function removeSaved(item: SavedBacktestSummary) {
  try {
    await ElMessageBox.confirm(`删除「${item.name}」?`, '删除回测', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
    await deleteSavedBacktest(item.id)
    ElMessage.success('已删除')
    await refreshSaved()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error('删除失败')
  }
}

function fmtDate(s: string): string {
  if (!s) return ''
  return s.replace('T', ' ').slice(5, 16)   // MM-DD HH:mm
}

onMounted(refreshSaved)
useRefreshable('回测', runTest, { immediate: false, autoRefresh: false })
</script>

<style scoped>
.backtest-panel { display: grid; grid-template-columns: 320px 1fr; gap: 16px; align-items: start; }
.backtest-panel.mobile { grid-template-columns: 1fr; gap: 12px; }
.config-col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.backtest-panel.mobile .config-col { gap: 12px; }
.config-form :deep(.el-form-item) { margin-bottom: 12px; }
.date-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.result-area { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.backtest-panel.mobile .result-area { gap: 12px; }
.empty-hint { grid-column: 1 / -1; }
.picks-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.trades-count { margin-left: 8px; font-size: 12px; color: var(--text-3); font-weight: 400; }
.side-tag { font-size: 11px; padding: 2px 10px; border-radius: var(--radius-pill); }
.side-tag.buy  { background: var(--up-soft); color: var(--up); }
.side-tag.sell { background: var(--down-soft); color: var(--down); }
.pick-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  background: var(--brand-soft);
  border-radius: 16px;
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}
.pick-chip:hover { background: var(--surface-hover); }
.pick-rank {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px;
  border-radius: 50%;
  background: var(--brand);
  color: var(--on-brand);
  font-size: 10px;
  font-weight: 700;
}
.saved-count { margin-left: 6px; font-size: 12px; color: var(--text-3); font-weight: 400; }
.saved-list { display: flex; flex-direction: column; gap: 6px; max-height: 360px; overflow-y: auto; }
.saved-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: var(--radius);
  background: var(--surface-hover);
  transition: background 0.15s;
}
.saved-item:hover { background: var(--brand-soft); }
.saved-main { flex: 1; min-width: 0; cursor: pointer; }
.saved-name {
  font-size: 13px; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.saved-meta { display: flex; gap: 10px; align-items: center; margin-top: 2px; font-size: 12px; }
.saved-date { color: var(--text-3); }
.saved-del { color: var(--text-3); cursor: pointer; flex-shrink: 0; padding: 4px; }
.saved-del:hover { color: var(--down); }
@media (max-width: 1000px) { .backtest-panel { grid-template-columns: 1fr; } }
</style>
