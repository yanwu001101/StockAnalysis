<template>
  <div class="factor-lab" :class="{ mobile: isMobile }">
    <div class="config-col">
      <AppCard title="因子检验" sub="IC / 分层回测 / 衰减分析 · 检验策略得分是否真的能排序未来收益">
        <el-form label-position="top" size="small" class="config-form">
          <el-form-item label="策略">
            <el-select v-model="config.strategyId" style="width: 100%;">
              <el-option v-for="s in strategyStore.strategies" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </el-form-item>
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
              <SegmentTabs v-model="config.rebalance" :options="rebalanceOptions" small />
            </el-form-item>
            <el-form-item label="分层数">
              <el-input-number v-model="config.layers" :min="3" :max="10" :step="1" style="width: 100%;" />
            </el-form-item>
          </div>
          <el-button type="primary" :loading="loading" @click="run" style="width: 100%;">
            <el-icon><DataAnalysis /></el-icon>开始检验
          </el-button>
          <p class="method-note">
            每个调仓日只用当日可见数据重新评分（无前视），截面做去极值+标准化后
            按得分分层，检验排序能力。分层为等权纸面组合，不计成本。
          </p>
        </el-form>
      </AppCard>

      <AppCard title="全策略体检" sub="顺序检验全部策略，按 |ICIR| 排序，约 10 分钟" compact>
        <div class="sweep-actions">
          <el-button type="primary" size="small" :loading="sweep.running" @click="runSweep">开始体检</el-button>
          <el-button v-if="sweep.running" size="small" @click="sweep.stopped = true">停止</el-button>
          <el-button v-if="!sweep.running && sweep.summaries.length" size="small" @click="clearSweep">清空</el-button>
        </div>
        <div v-if="sweep.running || sweep.total" class="sweep-progress">
          <el-progress :percentage="sweep.total ? Math.round(sweep.done / sweep.total * 100) : 0" :stroke-width="8" />
          <div class="sweep-status">
            {{ sweep.done }}/{{ sweep.total }}
            <span v-if="sweep.current" class="sweep-current">· 正在检验 {{ sweep.current }}</span>
            <span v-if="sweep.stopped && sweep.running" class="sweep-stop">· 停止中</span>
          </div>
        </div>
      </AppCard>
    </div>

    <div class="result-area" v-if="result">
      <AppCard title="因子评级" sub="方向性 · 稳定性 · 显著性 · 分层表现 · 样本量 → 综合评级">
        <div class="rating-row">
          <div class="grade-badge" :class="'grade-' + (rating?.grade || 'D')">
            <span class="grade-letter">{{ rating?.grade || '—' }}</span>
            <span class="grade-score">{{ rating?.composite ?? '—' }}</span>
          </div>
          <div class="rating-dims">
            <div class="dim" v-for="d in dimRows" :key="d.key">
              <span class="dim-label">{{ d.label }}</span>
              <div class="dim-bar"><div class="dim-fill" :style="{ width: d.value + '%' }" /></div>
              <span class="dim-val">{{ d.value }}</span>
            </div>
          </div>
        </div>
        <div class="flag-row" v-if="rating?.flags?.length">
          <span v-for="f in rating.flags" :key="f" class="flag-chip">{{ f }}</span>
        </div>
        <div class="rating-meta">
          <span>净多空年化 <b>{{ fmtPct(rating?.net_spread_ann) }}</b>（毛 {{ fmtPct(result.top_minus_bottom_annualized) }}，摩擦 {{ ((rating?.cost_per_turnover || 0) * 100).toFixed(2) }}%/次换手 × 年换手 {{ result.turnover_annualized ?? '—' }}x）</span>
          <span v-if="result.ic_neutral_summary">行业中性 IC {{ result.ic_neutral_summary.mean.toFixed(4) }}（原始 {{ result.ic_summary.mean.toFixed(4) }}）</span>
          <span v-if="result.regime">牛市 IC {{ result.regime.bull.ic_mean.toFixed(3) }} / 熊市 IC {{ result.regime.bear.ic_mean.toFixed(3) }}</span>
        </div>
        <div class="verdict" :class="verdictCls">
          <el-icon :size="18"><component :is="verdictIcon" /></el-icon>
          <div class="verdict-main">{{ verdictText }}</div>
        </div>
      </AppCard>

      <AppCard title="统计摘要" compact>
        <StatGrid :items="icItems" :cols="isMobile ? 2 : 4" />
      </AppCard>

      <AppCard title="分层净值" sub="按得分分层的等权组合净值（L1 最低分 → L5 最高分）" compact>
        <BaseChart :option="layerOption" :height="isMobile ? 260 : 340" />
      </AppCard>

      <AppCard title="RankIC 序列" sub="每期得分与前瞻收益的秩相关" compact>
        <BaseChart :option="icOption" :height="isMobile ? 200 : 260" />
      </AppCard>

      <AppCard title="衰减分析" sub="得分对未来 +N 日收益的预测力衰减" compact>
        <StockTable :rows="decayRows" :columns="decayColumns" :stock="false" :clickable="false" dense row-key="horizon" />
      </AppCard>
    </div>

    <!-- 全策略体检结果 -->
    <div class="result-area sweep-area" v-if="sweep.summaries.length">
      <AppCard title="体检结果" sub="按 |ICIR| 从高到低 · 点击「查看」载入单策略详情">
        <template #actions>
          <span class="sweep-meta">体检窗口 {{ config.startDate }} ~ {{ config.endDate }}</span>
        </template>
        <StockTable
          :rows="sweepRowsSorted"
          :columns="sweepColumns"
          :stock="false"
          :clickable="false"
          dense
          row-key="strategyId"
        >
          <template #cell-verdict="{ row }">
            <span class="verdict-chip" :class="row.verdict.cls">{{ row.verdict.text }}</span>
          </template>
          <template #cell-view="{ row }">
            <el-button link size="small" @click="viewStrategy(row.strategyId)">查看</el-button>
          </template>
        </StockTable>
      </AppCard>
    </div>

    <EmptyState v-if="!loading && !result && !sweep.summaries.length && !isMobile" title="选择策略开始检验"
        description="检验策略得分对未来收益的排序能力：IC、分层净值与衰减分析"
        class="empty-hint" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { DataAnalysis, CircleCheckFilled, WarningFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import type { EChartsOption } from 'echarts'
import { runFactorLab } from '@/api/strategy'
import { useStrategyStore } from '@/stores/strategy'
import { useDevice } from '@/composables/useDevice'
import { useChartTokens, baseTooltip } from '@/composables/useEcharts'
import type { FactorLabResult } from '@/types'
import type { StatItem, SegmentOption, StockColumn } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import StatGrid from '@/components/ui/StatGrid.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import StockTable from '@/components/stock/StockTable.vue'
import BaseChart from '@/components/charts/BaseChart.vue'
import EmptyState from '@/components/ui/EmptyState.vue'

const strategyStore = useStrategyStore()
const { isMobile } = useDevice()
const tokens = useChartTokens()

const loading = ref(false)
const result = ref<FactorLabResult | null>(null)

const config = reactive({
  strategyId: 'quality_factor',
  startDate: defaultStart(),
  endDate: defaultEnd(),
  rebalance: 'monthly',
  layers: 5,
})

function defaultStart(): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - 1)
  return d.toISOString().slice(0, 10)
}
function defaultEnd(): string {
  return new Date().toISOString().slice(0, 10)
}

const rebalanceOptions: SegmentOption<string>[] = [
  { label: '月度', value: 'monthly' },
  { label: '周度', value: 'weekly' },
]

function fmtPct(v: number | undefined, d = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`
}

// ---- 判定：|ICIR| 分档 + t 检验显著性；反转类策略（负 IC）看绝对值 ----
function verdictOf(s: { icir: number; t_stat: number }): { text: string; cls: string } {
  const abs = Math.abs(s.icir)
  const significant = Math.abs(s.t_stat) >= 2
  if (abs >= 0.3 && significant) return { text: '有效', cls: 'good' }
  if (abs >= 0.1) return significant
    ? { text: '弱有效', cls: 'mid' }
    : { text: '不显著', cls: 'mid' }
  return { text: '无效', cls: 'bad' }
}

const rating = computed(() => result.value?.rating)
const absIcir = computed(() => Math.abs(result.value?.ic_summary.icir ?? 0))
const DIM_LABELS: [string, string][] = [
  ['direction', '方向性'], ['stability', '稳定性'], ['significance', '显著性'],
  ['layering', '分层表现'], ['sample', '样本量'],
]
const dimRows = computed(() => {
  const dims = rating.value?.dimensions || {}
  return DIM_LABELS.map(([key, label]) => ({ key, label, value: Math.round(dims[key] || 0) }))
})
const gradeCls = computed(() => {
  const g = rating.value?.grade || 'D'
  return g === 'A' ? 'good' : g === 'B' ? 'mid' : 'bad'
})
const verdictCls = computed(() => {
  const s = result.value?.ic_summary
  return s ? verdictOf(s).cls : 'mid'
})
const verdictIcon = computed(() =>
  verdictCls.value === 'good' ? CircleCheckFilled : verdictCls.value === 'mid' ? WarningFilled : CircleCloseFilled
)
const verdictText = computed(() => {
  const s = result.value?.ic_summary
  const g = rating.value?.grade || 'D'
  const reverse = !!rating.value?.flags.some(f => f.startsWith('反向因子'))
  if (!s) return ''
  const significant = Math.abs(s.t_stat) >= 2
  if (reverse) {
    const use = significant ? '可作为反向信号或排除名单使用' : '方向有迹象但统计不显著，先观察'
    return `强反向因子（${g} 级）— 得分越高越差，${use}`
  }
  if (g === 'A') return '评级 A — 多维证据充分，可配置较高权重'
  if (g === 'B') return '评级 B — 有可用信号，建议中等权重并持续跟踪'
  if (g === 'C') return significant
    ? '评级 C — 证据薄弱，建议低权重'
    : '评级 C — 证据薄弱且统计不显著，建议拉长窗口再判断'
  return '评级 D — 得分与未来收益几乎无关，建议关闭或重做'
})

const icItems = computed<StatItem[]>(() => {
  const r = result.value
  if (!r) return []
  return [
    { label: 'RankIC 均值', value: r.ic_summary.mean.toFixed(4), cls: r.ic_summary.mean >= 0 ? 'price-up' : 'price-down' },
    { label: 'ICIR', value: r.ic_summary.icir.toFixed(3), cls: 'brand-text' },
    { label: 'IC > 0 占比', value: `${(r.ic_summary.positive_ratio * 100).toFixed(0)}%` },
    { label: 't 统计量', value: r.ic_summary.t_stat.toFixed(2) },
  ]
})

const decayColumns: StockColumn[] = [
  { key: 'horizon', label: '前瞻窗口', format: (r: any) => `+${r.horizon} 日`, mobile: 'title' },
  { key: 'ic_mean', label: 'RankIC 均值', type: 'num', digits: 4, mobile: 'primary' },
  { key: 'icir', label: 'ICIR', type: 'num', digits: 3 },
  { key: 'n', label: '期数', type: 'num', digits: 0, mobile: 'secondary' },
]
const decayRows = computed(() => result.value?.decay ?? [])

async function run() {
  loading.value = true
  try {
    const r = await runFactorLab({
      strategyId: config.strategyId,
      startDate: config.startDate,
      endDate: config.endDate,
      rebalance: config.rebalance,
      layers: config.layers,
      maxCodes: 300,
    })
    if (r.error) {
      ElMessage.warning(r.error)
      return
    }
    result.value = r
    ElMessage.success('因子检验完成')
  } catch {
    ElMessage.error('因子检验失败')
  } finally {
    loading.value = false
  }
}

// ---- 全策略体检 ----
interface SweepRow {
  strategyId: string
  name: string
  ic_mean: number
  icir: number
  positive_ratio: number
  t_stat: number
  spread: number
  n: number
  verdict: { text: string; cls: string }
  grade?: string
  composite?: number
  error?: string
}

const SWEEP_KEY = 'factorlab_sweep_v1'
const fullResults = new Map<string, FactorLabResult>()
const sweep = reactive({
  running: false,
  stopped: false,
  current: '',
  done: 0,
  total: 0,
  summaries: [] as SweepRow[],
})

const sweepRowsSorted = computed(() =>
  [...sweep.summaries].sort((a, b) => Math.abs(b.icir) - Math.abs(a.icir))
)

const sweepColumns: StockColumn[] = [
  { key: 'name', label: '策略', mobile: 'title' },
  { key: 'ic_mean', label: 'RankIC', type: 'num', digits: 4, colored: true, mobile: 'primary' },
  { key: 'icir', label: 'ICIR', type: 'num', digits: 3 },
  { key: 'positive_ratio', label: 'IC>0', align: 'center', mobile: 'secondary', format: (r: any) => `${(r.positive_ratio * 100).toFixed(0)}%` },
  { key: 'spread', label: '多空年化', type: 'num', digits: 4, colored: true, format: (r: any) => r.spread, mobile: 'secondary' },
  { key: 't_stat', label: 't 值', type: 'num', digits: 2, mobile: 'hidden' },
  { key: 'grade', label: '评级', align: 'center', mobile: 'secondary', format: (r: any) => (r.grade === '—' ? '—' : `${r.grade} · ${r.composite}`) },
  { key: 'verdict', label: '结论', align: 'center', mobile: 'primary' },
  { key: 'view', label: '', align: 'center', mobile: 'hidden' },
]

function saveSweep() {
  try {
    localStorage.setItem(SWEEP_KEY, JSON.stringify({
      startDate: config.startDate, endDate: config.endDate, rows: sweep.summaries,
    }))
  } catch { /* 存不下就算了 */ }
}

function loadSweep() {
  try {
    const raw = localStorage.getItem(SWEEP_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (parsed?.rows?.length) {
      sweep.summaries = parsed.rows
      sweep.total = parsed.rows.length
      sweep.done = parsed.rows.length
      config.startDate = parsed.startDate || config.startDate
      config.endDate = parsed.endDate || config.endDate
    }
  } catch { /* ignore */ }
}

function clearSweep() {
  sweep.summaries = []
  sweep.done = 0
  sweep.total = 0
  fullResults.clear()
  localStorage.removeItem(SWEEP_KEY)
}

function viewStrategy(id: string) {
  const full = fullResults.get(id)
  if (full) {
    result.value = full
    window.scrollTo({ top: 0, behavior: 'smooth' })
    return
  }
  // 刷新后 full result 不在内存 — 重跑该策略
  config.strategyId = id
  run()
}

async function runSweep() {
  const list = strategyStore.strategies
  if (!list.length) return
  sweep.running = true
  sweep.stopped = false
  sweep.done = 0
  sweep.total = list.length
  sweep.summaries = []
  fullResults.clear()

  for (const s of list) {
    if (sweep.stopped) break
    sweep.current = s.name
    try {
      const r = await runFactorLab({
        strategyId: s.id,
        startDate: config.startDate,
        endDate: config.endDate,
        rebalance: config.rebalance,
        layers: config.layers,
        maxCodes: 300,
      })
      if (r.error) {
        const covered = r.error.includes('截面不足')
        sweep.summaries.push({
          strategyId: s.id,
          name: s.name,
          ic_mean: 0, icir: 0, positive_ratio: 0, t_stat: 0, spread: 0, n: 0,
          verdict: { text: covered ? '覆盖不足' : '失败', cls: 'mid' },
          error: r.error,
        })
      } else {
      fullResults.set(s.id, r)
      const v = verdictOf(r.ic_summary)
      sweep.summaries.push({
        strategyId: s.id,
        name: s.name,
        ic_mean: r.ic_summary.mean,
        icir: r.ic_summary.icir,
        positive_ratio: r.ic_summary.positive_ratio,
        t_stat: r.ic_summary.t_stat,
        spread: r.top_minus_bottom_annualized,
        n: r.ic_summary.n,
        verdict: v,
        grade: r.rating?.grade || "—",
        composite: r.rating?.composite ?? 0,
      })
      }
    } catch {
      sweep.summaries.push({
        strategyId: s.id,
        name: s.name,
        ic_mean: 0, icir: 0, positive_ratio: 0, t_stat: 0, spread: 0, n: 0,
        verdict: { text: '失败', cls: 'bad' },
        error: '分析失败',
      })
    }
    sweep.done++
    saveSweep()
  }
  sweep.running = false
  sweep.current = ''
  ElMessage.success(sweep.stopped ? '体检已停止（保留已完成部分）' : '全策略体检完成')
}

onMounted(loadSweep)

const layerOption = computed<EChartsOption | null>(() => {
  const rows = result.value?.layer_curves
  if (!rows?.length) return null
  const t = tokens.value
  const keys = Object.keys(rows[0]).filter(k => k !== 'date')
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: t.font },
    legend: { data: keys, top: 0, right: 8, textStyle: { color: t.text3, fontSize: 11 }, itemWidth: 14 },
    grid: { left: 56, right: 20, top: 32, bottom: 36 },
    xAxis: { type: 'category', data: rows.map(r => String(r.date)),
      axisLabel: { color: t.text3, fontSize: 10 },
      axisLine: { lineStyle: { color: t.line } } },
    yAxis: { type: 'value', scale: true,
      splitLine: { lineStyle: { color: t.line } },
      axisLabel: { color: t.text3 } },
    series: keys.map((k, i) => ({
      type: 'line',
      name: k,
      data: rows.map(r => r[k]),
      symbol: 'none',
      smooth: true,
      lineStyle: { color: t.series[i % t.series.length], width: k === `L${keys.length}` ? 2.2 : 1.4 },
    })),
    tooltip: { trigger: 'axis', ...baseTooltip(t) },
  }
})

const icOption = computed<EChartsOption | null>(() => {
  const rows = result.value?.ic_series
  if (!rows?.length) return null
  const t = tokens.value
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: t.font },
    grid: { left: 56, right: 20, top: 16, bottom: 36 },
    xAxis: { type: 'category', data: rows.map(r => r.date),
      axisLabel: { color: t.text3, fontSize: 10 },
      axisLine: { lineStyle: { color: t.line } } },
    yAxis: { type: 'value',
      splitLine: { lineStyle: { color: t.line } },
      axisLabel: { color: t.text3 } },
    series: [{
      type: 'bar',
      data: rows.map(r => ({
        value: r.ic,
        itemStyle: { color: r.ic >= 0 ? t.up : t.down },
      })),
    }],
    tooltip: { trigger: 'axis', ...baseTooltip(t) },
  }
})
</script>

<style scoped>
.factor-lab { display: grid; grid-template-columns: 320px 1fr; gap: 16px; align-items: start; }
.factor-lab.mobile { grid-template-columns: 1fr; gap: 12px; }
.config-col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.factor-lab.mobile .config-col { gap: 12px; }
.config-form :deep(.el-form-item) { margin-bottom: 12px; }
.date-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.method-note { margin: 4px 0 0; font-size: 11px; color: var(--text-4); line-height: 1.6; }
.result-area { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.factor-lab.mobile .result-area { gap: 12px; }
.empty-hint { grid-column: 1 / -1; }
.sweep-area { grid-column: 1 / -1; }

.sweep-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.sweep-progress { margin-top: 10px; }
.sweep-status { margin-top: 6px; font-size: 12px; color: var(--text-3); }
.sweep-current { color: var(--text-2); }
.sweep-stop { color: var(--warn-text); }
.sweep-meta { font-size: 12px; color: var(--text-3); }

.verdict-chip { font-size: 11px; padding: 2px 10px; border-radius: var(--radius-pill); }
.verdict-chip.good { background: var(--color-green-soft); color: var(--color-green); }
.verdict-chip.mid { background: var(--warn-soft); color: var(--warn-text); }
.verdict-chip.bad { background: var(--color-red-soft); color: var(--color-red); }

.rating-row { display: flex; align-items: center; gap: 18px; }
.grade-badge {
  width: 72px; height: 72px; border-radius: 14px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.grade-badge.grade-A { background: var(--color-green-soft); color: var(--color-green); }
.grade-badge.grade-B { background: var(--brand-soft); color: var(--brand); }
.grade-badge.grade-C { background: var(--warn-soft); color: var(--warn-text); }
.grade-badge.grade-D { background: var(--color-red-soft); color: var(--color-red); }
.grade-letter { font-size: 26px; font-weight: 800; line-height: 1.1; }
.grade-score { font-size: 12px; opacity: 0.8; }
.rating-dims { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.dim { display: grid; grid-template-columns: 60px 1fr 34px; align-items: center; gap: 10px; }
.dim-label { font-size: 12px; color: var(--text-3); }
.dim-bar { height: 8px; border-radius: 4px; background: var(--bg-2); overflow: hidden; }
.dim-fill { height: 100%; border-radius: 4px; background: var(--brand); }
.dim-val { font-size: 12px; color: var(--text-2); text-align: right; font-variant-numeric: tabular-nums; }
.flag-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.flag-chip { font-size: 11px; padding: 3px 10px; border-radius: var(--radius-pill);
  background: var(--warn-soft); color: var(--warn-text); }
.rating-meta { display: flex; flex-wrap: wrap; gap: 4px 18px; margin-top: 12px;
  font-size: 12px; color: var(--text-3); }
.rating-meta b { color: var(--text); }

.verdict { display: flex; align-items: center; gap: 12px; padding: 4px 2px; margin-top: 12px; }
.verdict.good { color: var(--color-green); }
.verdict.mid { color: var(--warn-text); }
.verdict.bad { color: var(--color-red); }
.verdict-text { min-width: 0; }
.verdict-main { font-size: 15px; font-weight: 600; color: var(--text); }
.verdict-sub { font-size: 12px; color: var(--text-3); margin-top: 2px; }
@media (max-width: 1000px) { .factor-lab { grid-template-columns: 1fr; } }
</style>
