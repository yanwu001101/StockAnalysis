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
      <AppCard title="因子评级">
        <div class="rating-head">
          <div class="grade-badge" :class="'grade-' + (rating?.grade || 'D')">
            <span class="grade-letter">{{ rating?.grade || '—' }}</span>
            <span class="grade-score">{{ rating?.strength ?? '—' }}</span>
          </div>
          <div class="rating-head-lines">
            <div class="rating-title">
              {{ result.strategy_id }}
              <span v-if="directionMeta" class="dir-chip" :class="directionMeta.cls">{{ directionMeta.label }}</span>
              <span class="status-chip" :class="statusMeta.cls">{{ statusMeta.text }}</span>
            </div>
            <div class="rating-line">
              <span class="rl-k">因子方向</span>
              <span class="rl-v">{{ directionMeta.label }} {{ directionMeta.arrow }}</span>
            </div>
            <div class="rating-line">
              <span class="rl-k">因子实力</span>
              <span class="rl-v"><b>{{ rating?.strength ?? '—' }}</b>（{{ rating?.grade || '—' }} 级 · 经济量级）</span>
            </div>
            <div class="rating-line">
              <span class="rl-k">统计可信度</span>
              <span class="rl-v">{{ confidenceMeta.icon }} {{ rating?.confidence ?? '—' }}（{{ confidenceMeta.text }}）</span>
            </div>
          </div>
        </div>

        <div class="dims-block">
          <div class="dims-title">细分维度</div>
          <div class="rating-dims">
            <div class="dim" v-for="d in dimRows" :key="d.key">
              <span class="dim-label">{{ d.label }}</span>
              <div class="dim-bar"><div class="dim-fill" :style="{ width: d.value + '%' }" /></div>
              <span class="dim-val">{{ d.value }}</span>
            </div>
          </div>
        </div>

        <div class="metrics-block">
          <div class="metric-line" v-for="m in metricRows" :key="m.label">
            <span class="rl-k">{{ m.label }}</span>
            <span class="rl-v num" :class="m.cls">{{ m.value }} <span class="stars">{{ m.stars }}</span></span>
            <span class="rl-extra">
              <span v-if="m.warn" class="flag-chip">⚠ 收益为负</span>
              <span v-if="m.flipped" class="rl-flip">反向使用后 <b class="num">{{ m.flipped }}</b></span>
            </span>
          </div>
        </div>

        <div class="flag-row" v-if="rating?.flags?.length">
          <span v-for="f in rating.flags" :key="f" class="flag-chip">{{ f }}</span>
        </div>
        <div class="rating-meta">
          <template v-if="!isReverse">
            <span>净多空年化 <b>{{ fmtPct(rating?.net_spread_ann) }}</b>（毛 {{ fmtPct(result.top_minus_bottom_annualized) }}，摩擦 {{ ((rating?.cost_per_turnover || 0) * 100).toFixed(2) }}%/次换手 × 年换手 {{ result.turnover_annualized ?? '—' }}x）</span>
            <span v-if="result.ic_neutral_summary">行业中性 IC {{ result.ic_neutral_summary.mean.toFixed(4) }}（原始 {{ result.ic_summary.mean.toFixed(4) }}）</span>
            <span v-if="result.regime">牛市 IC {{ result.regime.bull.ic_mean.toFixed(3) }} / 熊市 IC {{ result.regime.bear.ic_mean.toFixed(3) }}</span>
          </template>
          <template v-else>
            <span>反向使用后净多空年化 <b>{{ fmtPct(-(rating?.net_spread_ann ?? 0)) }}</b>（毛 {{ fmtPct(-(result.top_minus_bottom_annualized ?? 0)) }}，摩擦 {{ ((rating?.cost_per_turnover || 0) * 100).toFixed(2) }}%/次换手 × 年换手 {{ result.turnover_annualized ?? '—' }}x）</span>
            <span v-if="result.ic_neutral_summary">行业中性 IC {{ (-(result.ic_neutral_summary.mean ?? 0)).toFixed(4) }}（原始 {{ (result.ic_neutral_summary?.mean ?? 0) >= 0 ? '' : '' }}{{ result.ic_neutral_summary?.mean?.toFixed(4) }}）</span>
            <span v-if="result.regime">牛市 IC {{ (-result.regime.bull.ic_mean).toFixed(3) }} / 熊市 IC {{ (-result.regime.bear.ic_mean).toFixed(3) }}（已按反向翻正）</span>
          </template>
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
            <el-button link size="small" @click="viewStrategy(row.strategyId)">{{ row.error ? "重试" : "查看" }}</el-button>
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

function fmtPctLocal(v: number | undefined, d = 2): string {
  if (v == null || Number.isNaN(v)) return "—"
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(d)}%`
}
function fmtPct(v: number | undefined, d = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`
}



const rating = computed(() => result.value?.rating)
const absIcir = computed(() => Math.abs(result.value?.ic_summary.icir ?? 0))
const isReverse = computed(() => rating.value?.direction === "reverse")
const DIM_LABELS: [string, string][] = [
  ['direction_ic', '方向IC强度'], ['stability', '稳定性'], ['significance', '显著性'],
  ['monotonicity', '分层单调性'], ['spread', '多空价差'], ['sample', '样本量'],
]
const dimRows = computed(() => {
  const dims = rating.value?.dimensions || {}
  return DIM_LABELS.map(([key, label]) => ({ key, label, value: Math.round(dims[key] || 0) }))
})
const gradeCls = computed(() => {
  const g = rating.value?.grade || 'D'
  return g === 'A' ? 'good' : g === 'B' ? 'mid' : 'bad'
})
const directionMeta = computed(() => {
  const d = rating.value?.direction || "neutral"
  if (d === 'reverse') return { label: '反向因子', arrow: '↓', cls: 'dir-reverse' }
  if (d === 'positive') return { label: '正向因子', arrow: '↑', cls: 'dir-positive' }
  return { label: '方向中性', arrow: '→', cls: 'dir-neutral' }
})
const confidenceMeta = computed(() => {
  const c = rating.value?.confidence ?? 0
  if (c >= 70) return { icon: '✅', text: '证据充分' }
  if (c >= 40) return { icon: '⚠', text: '尚不显著' }
  return { icon: '⚠', text: '证据不足' }
})
// 状态五态：有效/候选/不显著（有数据），覆盖不足/计算失败（无数据）
const statusMeta = computed(() => {
  const r = result.value
  if (r?.error_kind === 'coverage') return { text: '覆盖不足', cls: 'st-coverage' }
  if (r?.error_kind === 'compute') return { text: '计算失败', cls: 'st-compute' }
  const st = rating.value?.status || "不显著"
  if (st === '有效') return { text: '有效', cls: 'st-good' }
  if (st === '候选') return { text: '候选', cls: 'st-candidate' }
  return { text: '不显著', cls: 'st-insig' }
})
interface MetricRow { label: string; value: string; cls?: string; flipped?: string; stars?: string; warn?: boolean }
const metricRows = computed<MetricRow[]>(() => {
  const r = result.value
  const s = r?.ic_summary
  if (!s || !r) return []
  const rev = isReverse.value
  const sign = rev ? -1 : 1
  const f = (v: number, d = 4) => (v * sign).toFixed(d)
  const pf = (v: number) => `${Math.round((v * sign) * 100)}%`
  const clamp01 = (x: number) => Math.max(0, Math.min(1, x))
  const stars = (ratio: number) => {
    const full = Math.round(clamp01(ratio) * 5)
    return '★'.repeat(full) + '☆'.repeat(5 - full)
  }
  const mono = r.layer_monotonicity ?? 0
  const spread = r.top_minus_bottom_annualized ?? 0
  const rows: MetricRow[] = [
    { label: 'RankIC', value: f(s.mean), cls: s.mean * sign >= 0 ? 'price-up' : 'price-down', flipped: rev ? s.mean.toFixed(4) : undefined, stars: stars(clamp01(Math.abs(s.mean) / 0.05)) },
    { label: 'ICIR', value: f(s.icir, 3), flipped: rev ? s.icir.toFixed(3) : undefined, stars: stars(clamp01(Math.abs(s.icir) / 0.5)) },
    { label: 'IC > 0', value: pf(s.positive_ratio), flipped: rev ? `${Math.round(s.positive_ratio * 100)}%` : undefined, stars: stars(clamp01(Math.abs(s.positive_ratio * sign - 0.5) * 2 + 0.5) * 0 + clamp01(s.positive_ratio * sign + (rev ? -0.5 : 0.5)) * 2 * 0.5 + 0.5 * 0 + (s.positive_ratio * sign >= 0.5 ? 1 : 0.6) * 0 + 0) || stars(0.5) },
    { label: 't 值', value: s.t_stat.toFixed(2), flipped: rev ? s.t_stat.toFixed(2) : undefined, stars: stars(clamp01(Math.abs(s.t_stat) / 2.5)) },
    { label: '分层单调性', value: (mono * sign).toFixed(2), flipped: rev ? mono.toFixed(2) : undefined, stars: stars(clamp01(mono * sign)) },
    { label: '多空年化', value: fmtPctLocal(spread * sign), cls: spread * sign >= 0 ? 'price-up' : 'price-down', flipped: rev ? fmtPctLocal(spread) : undefined, stars: stars(clamp01(Math.abs(spread) / 0.20)), warn: spread * sign < 0 },
  ]
  return rows
})
const verdictCls = computed(() => statusMeta.value.cls)
const verdictIcon = computed(() =>
  verdictCls.value === 'good' ? CircleCheckFilled : verdictCls.value === 'mid' ? WarningFilled : CircleCloseFilled
)
const verdictText = computed(() => {
  const r = result.value
  if (!r || r.error) return r?.error || ''
  const st = rating.value?.status || '不显著'
  const g = rating.value?.grade || 'D'
  if (isReverse.value) {
    if (st === '有效') return '统计显著的反向因子 — 用作排除名单或反向信号，权重配置放反向侧'
    if (st === '候选') return `反向候选（实力 ${g} 级）— 反向使用后值得关注，当前样本证据不足，继续扩大样本`
    return '方向偏反向但不显著 — 暂不参与权重配置，保持观察'
  }
  if (st === '有效') return '统计显著 — 排序能力得到验证，可配置较高权重'
  if (st === '候选') return `较强候选价值（实力 ${g} 级）— 但当前样本统计证据不足，继续扩大样本`
  return '有数据但统计证据不足 — 暂不加权，拉长时间窗口后再判断'
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
const decayRows = computed(() => {
  const rev = isReverse.value
  return (result.value?.decay ?? []).map(d => ({
    horizon: d.horizon,
    ic_mean: rev ? -d.ic_mean : d.ic_mean,
    icir: rev ? -d.icir : d.icir,
    n: d.n,
  }))
})

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
  ic_mean: number | null
  icir: number | null
  positive_ratio: number | null
  t_stat: number | null
  spread: number | null
  n: number | null
  verdict: { text: string; cls: string }
  grade?: string
  composite?: number
  error?: string
}

const SWEEP_KEY = 'factorlab_sweep_v2'
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
  [...sweep.summaries].sort((a, b) => Math.abs(b.icir ?? 0) - Math.abs(a.icir ?? 0))
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
    window.scrollTo({ top: 0, behavior: "smooth" })
    return
  }
  // 刷新后 full result 不在内存 — 重跑该策略并回写体检行
  retryRow(id)
}

async function retryRow(id: string) {
  const row = sweep.summaries.find(x => x.strategyId === id)
  if (!row) return
  sweep.current = row.name
  try {
    const r = await runFactorLab({
      strategyId: id,
      startDate: config.startDate,
      endDate: config.endDate,
      rebalance: config.rebalance,
      layers: config.layers,
      maxCodes: 300,
    })
    if (r.error) { row.error = r.error; return }
    fullResults.set(id, r)
    const v = { text: r.rating?.status || "不显著", cls: "st-insig" }
    row.ic_mean = r.ic_summary.mean
    row.icir = r.ic_summary.icir
    row.positive_ratio = r.ic_summary.positive_ratio
    row.t_stat = r.ic_summary.t_stat
    row.spread = r.top_minus_bottom_annualized
    row.n = r.ic_summary.n
    row.verdict = v
    row.grade = r.rating?.grade
    row.composite = r.rating?.strength
    row.error = undefined
    result.value = r
    saveSweep()
    window.scrollTo({ top: 0, behavior: "smooth" })
  } catch {
    row.error = "重试失败"
  } finally {
    sweep.current = ""
  }
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
        const covered = r.error_kind === 'coverage' || r.error.includes('截面不足')
        sweep.summaries.push({
          strategyId: s.id,
          name: s.name,
          ic_mean: null, icir: null, positive_ratio: null, t_stat: null, spread: null, n: null,
          verdict: { text: covered ? "覆盖不足" : "计算失败", cls: covered ? "st-coverage" : "st-compute" },
          error: r.error,
        })
      } else {
      fullResults.set(s.id, r)
      const v = { text: r.rating?.status || "不显著", cls: "st-insig" }
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
        composite: r.rating?.strength ?? 0,
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

.verdict-chip { font-size: 11px; padding: 2px 10px; border-radius: var(--radius-pill); white-space: nowrap; }
.verdict-chip.st-good { background: var(--color-green-soft); color: var(--color-green); }
.verdict-chip.st-candidate { background: var(--brand-soft); color: var(--brand); }
.verdict-chip.st-insig { background: var(--warn-soft); color: var(--warn-text); }
.verdict-chip.st-coverage { background: var(--bg-2); color: var(--text-3); }
.verdict-chip.st-compute { background: var(--color-red-soft); color: var(--color-red); }

.rating-head { display: flex; align-items: center; gap: 16px; }
.rating-head-lines { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.rating-title { font-size: 15px; font-weight: 600; color: var(--text); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.dir-chip { font-size: 11px; padding: 1px 8px; border-radius: var(--radius-pill); font-weight: 500; }
.dir-reverse { background: var(--warn-soft); color: var(--warn-text); }
.dir-positive { background: var(--color-green-soft); color: var(--color-green); }
.dir-neutral { background: var(--bg-2); color: var(--text-3); }
.status-chip { font-size: 11px; padding: 1px 8px; border-radius: var(--radius-pill); font-weight: 500; }
.status-chip.st-good { background: var(--color-green-soft); color: var(--color-green); }
.status-chip.st-candidate { background: var(--brand-soft); color: var(--brand); }
.status-chip.st-insig { background: var(--warn-soft); color: var(--warn-text); }
.status-chip.st-coverage { background: var(--bg-2); color: var(--text-3); }
.status-chip.st-compute { background: var(--color-red-soft); color: var(--color-red); }
.rating-line { display: grid; grid-template-columns: 84px 1fr; gap: 8px; font-size: 12px; }
.rl-k { color: var(--text-3); }
.rl-v { color: var(--text); min-width: 0; }
.rl-flip { color: var(--brand); font-size: 12px; margin-left: 10px; }
.metrics-block { margin-top: 12px; display: flex; flex-direction: column; gap: 5px;
  padding: 10px 12px; background: var(--bg-2); border-radius: var(--radius); }
.metric-line { display: grid; grid-template-columns: 70px 110px 1fr; align-items: center; gap: 8px; font-size: 12px; }
.metric-line .rl-v { font-variant-numeric: tabular-nums; }
.stars { color: var(--warn-text); font-size: 11px; letter-spacing: 1px; margin-left: 6px; }
.rl-extra { display: inline-flex; gap: 8px; align-items: center; }
.dims-block { margin-top: 14px; }
.dims-title { font-size: 12px; color: var(--text-3); margin-bottom: 8px; }
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
