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
      <AppCard title="因子综合评价">
        <!-- 标题行：状态 emoji + 方向 -->
        <div class="rating-head">
          <div class="score-block" :class="'grade-' + (rating?.grade || 'D')">
            <div class="score-label">经济效果</div>
            <div class="score-num">{{ rating?.strength ?? '—' }}<span class="score-sub">/100 · {{ rating?.grade || '—' }} 级</span></div>
          </div>
          <div class="score-block" :class="(rating?.confidence ?? 0) >= 70 ? 'conf-good' : 'conf-warn'">
            <div class="score-label">统计可信度</div>
            <div class="score-num">{{ rating?.confidence ?? '—' }}<span class="score-sub">/100 · {{ confidenceMeta.text }}</span></div>
          </div>
          <div class="rating-head-lines">
            <div class="rating-title">
              <span class="status-emoji">{{ statusMeta.emoji }}</span>
              {{ result.strategy_id }}
              <span class="status-chip" :class="statusMeta.cls">{{ statusMeta.emoji }} {{ statusMeta.text }}</span>
              <span v-if="directionMeta.arrow !== '→'" class="dir-chip" :class="directionMeta.cls">
                {{ directionMeta.label }} {{ directionMeta.arrow }}
              </span>
            </div>
            <div class="rating-line">
              <span class="rl-k">因子方向</span>
              <span class="rl-v">{{ directionMeta.label }} {{ directionMeta.arrow }}</span>
            </div>
            <div class="rating-line">
              <span class="rl-k">样本信息</span>
              <span class="rl-v">有效调仓期 {{ sampleInfo.periods }} · 平均截面 {{ sampleInfo.avg_cross_section }} 只 · 观测 {{ sampleInfo.observations }}</span>
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
          <div class="dims-title" style="margin-top: 10px;">稳健性与交易可行性</div>
          <div class="rating-dims">
            <div class="dim" v-for="d in extraBars" :key="d.key">
              <span class="dim-label">{{ d.label }}</span>
              <div class="dim-bar"><div class="dim-fill" :style="{ width: d.value + '%', background: d.color }" /></div>
              <span class="dim-val">{{ d.value }}</span>
            </div>
          </div>
        </div>

        <!-- 指标行：方向校正后主值 + 原始值 + 强度条 + 文字评级（不用星级） -->
        <div class="metrics-block">
          <div class="metric-line" v-for="m in metricRows" :key="m.label">
            <span class="rl-k">{{ m.label }}</span>
            <span class="rl-v num" :class="m.cls">{{ m.value }}<span v-if="m.raw" class="rl-raw">（原始 {{ m.raw }}）</span></span>
            <span class="rl-extra">
              <span class="mini-bar"><span class="mini-fill" :style="{ width: m.bar + '%' }" /></span>
              <span class="rl-grade">{{ m.gradeText }}</span>
            </span>
          </div>
        </div>

        <div class="flag-row" v-if="rating?.flags?.length">
          <span v-for="f in rating.flags" :key="f" class="flag-chip">{{ f }}</span>
        </div>
        <div class="rating-meta">
          <!-- 净多空数学：毛(方向校正) − 摩擦成本 = 净。成本与方向无关，不能简单取负号 -->
          <span>
            多空年化（方向校正后）<b>{{ fmtPct(adjGross) }}</b>
            − 摩擦 {{ fmtPct(costAnn) }}（{{ ((rating?.cost_per_turnover || 0) * 100).toFixed(2) }}%/次换手 × 年换手 {{ result.turnover_annualized ?? '—' }}x）
            → 净 <b>{{ fmtPct(adjNet) }}</b>
            <span class="rl-raw">（原始方向：毛 {{ fmtPct(result.top_minus_bottom_annualized) }} / 净 {{ fmtPct(rating?.net_spread_ann) }}）</span>
          </span>
          <span v-if="result.ic_neutral_summary">行业中性 IC {{ fmtAdj(result.ic_neutral_summary.mean, 4) }}（原始 {{ result.ic_neutral_summary.mean.toFixed(4) }}）</span>
          <span v-if="result.regime">牛市 IC {{ fmtAdj(result.regime.bull.ic_mean, 3) }} / 熊市 IC {{ fmtAdj(result.regime.bear.ic_mean, 3) }}（已按方向校正）</span>
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

      <AppCard title="衰减分析（探索性）" sub="得分对未来 +N 日收益的预测力衰减" compact>
        <div v-if="decaySampleWarn" class="warn-line">⚠ 当前有效期数 {{ decaySampleN }} 期，无法可靠判断最佳持有周期，以下结果仅供参考</div>
        <StockTable :rows="decayRows" :columns="decayColumns" :stock="false" :clickable="false" dense row-key="horizon" />
      </AppCard>
    </div>

    <!-- 全策略体检结果 -->
    <div class="result-area sweep-area" v-if="sweep.summaries.length">
      <AppCard title="体检结果" sub="按 |ICIR| 从高到低 · 点击「查看」载入单策略详情">
        <template #actions>
          <span class="sweep-meta">排序</span>
          <SegmentTabs v-model="sweepSortKey" :options="sweepSortOptions" small />
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

function fmtPct(v: number | undefined | null, d = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`
}

const rating = computed(() => result.value?.rating)
const isReverse = computed(() => rating.value?.direction === 'reverse')
const dirSign = computed(() => (isReverse.value ? -1 : 1))
/** 方向校正后的多空毛收益（反向因子翻正） */
const adjGross = computed(() => (result.value?.top_minus_bottom_annualized ?? 0) * dirSign.value)
/** 摩擦成本与方向无关：净(反向) = 毛(反向) − 成本，而不是 −净 */
const costAnn = computed(() => (result.value?.turnover_annualized ?? 0) * (rating.value?.cost_per_turnover ?? 0))
const adjNet = computed(() => adjGross.value - costAnn.value)

function fmtAdj(v: number | null | undefined, d = 4): string {
  if (v == null) return '—'
  return (v * dirSign.value >= 0 ? '+' : '') + (v * dirSign.value).toFixed(d)
}

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
  const d = rating.value?.direction || 'neutral'
  if (d === 'reverse') return { label: '反向因子', arrow: '↓', cls: 'dir-reverse' }
  if (d === 'positive') return { label: '正向因子', arrow: '↑', cls: 'dir-positive' }
  return { label: '方向中性', arrow: '→', cls: 'dir-neutral' }
})
const confidenceMeta = computed(() => {
  const c = rating.value?.confidence ?? 0
  if (c >= 70) return { text: '证据充分' }
  if (c >= 40) return { text: '尚不显著' }
  return { text: '证据不足' }
})

// 状态五态：🟢有效 🟡候选 🟠不显著（有数据） ⚪覆盖不足 🔴计算失败（无数据）
const sampleInfo = computed(() => result.value?.sample_info || { periods: 0, avg_cross_section: 0, observations: 0 })
const robustness = computed(() => result.value?.rating?.robustness)
const tradability = computed(() => result.value?.rating?.tradability)
const extraBars = computed(() => {
  const out: { key: string; label: string; value: number; color: string }[] = []
  const rob = robustness.value
  if (rob != null) out.push({ key: "rob", label: "稳健性", value: Math.round(rob), color: "var(--chart-4)" })
  const tr = tradability.value
  if (tr != null) out.push({ key: "tra", label: "交易可行性", value: Math.round(tr), color: tr >= 60 ? "var(--chart-1)" : "var(--warn)" })
  return out
})


const statusMeta = computed(() => {
  const r = result.value
  if (r?.error_kind === 'coverage') return { emoji: '⚪', text: '覆盖不足', cls: 'st-coverage' }
  if (r?.error_kind === 'compute') return { emoji: '🔴', text: '计算失败', cls: 'st-compute' }
  const st = rating.value?.status || '不显著'
  if (st === '有效') return { emoji: '🟢', text: '有效', cls: 'st-good' }
  if (st === '候选') return { emoji: '🟡', text: '候选', cls: 'st-candidate' }
  return { emoji: '🟠', text: '不显著', cls: 'st-insig' }
})

interface MetricRow {
  label: string
  /** 方向校正后的主数值（反向因子显示翻正口径） */
  value: string
  /** 原始方向的数值（反向时显示在括号里） */
  raw?: string
  cls?: string
  /** 强度条 0-100 */
  bar: number
  gradeText: string
}
const clamp01 = (x: number) => Math.max(0, Math.min(1, x))
function strengthLabel(ratio: number): string {
  if (ratio >= 0.8) return '强'
  if (ratio >= 0.6) return '较强'
  if (ratio >= 0.4) return '中等'
  if (ratio >= 0.2) return '中等偏弱'
  return '弱'
}

const metricRows = computed<MetricRow[]>(() => {
  const r = result.value
  const s = r?.ic_summary
  if (!s || !r) return []
  const sign = dirSign.value
  const rev = isReverse.value
  const adj = (v: number, d = 4) => v * sign
  const fmt = (v: number, d = 4) => adj(v, d).toFixed(d)
  const mono = r.layer_monotonicity ?? 0
  const spread = r.top_minus_bottom_annualized ?? 0
  const posAdj = clamp01(rev ? 1 - s.positive_ratio : s.positive_ratio)
  const absT = Math.abs(s.t_stat)
  const rows: MetricRow[] = [
    {
      label: 'RankIC', value: fmt(s.mean), raw: s.mean.toFixed(4),
      cls: s.mean * sign >= 0 ? 'price-up' : 'price-down',
      bar: clamp01(Math.abs(s.mean) / 0.05) * 100, gradeText: strengthLabel(clamp01(Math.abs(s.mean) / 0.05)),
    },
    {
      label: 'ICIR', value: fmt(s.icir, 3), raw: s.icir.toFixed(3),
      bar: clamp01(Math.abs(s.icir) / 0.5) * 100, gradeText: strengthLabel(clamp01(Math.abs(s.icir) / 0.5)),
    },
    {
      label: 'IC > 0', value: `${Math.round(posAdj * 100)}%`, raw: `${Math.round(s.positive_ratio * 100)}%`,
      bar: posAdj * 100, gradeText: strengthLabel(posAdj),
    },
    {
      label: 't 值', value: fmt(s.t_stat, 2), raw: s.t_stat.toFixed(2),
      cls: absT >= 2 ? 'price-up' : undefined,
      bar: clamp01(absT / 2.5) * 100,
      gradeText: absT >= 2 ? '统计显著'
        : absT >= 1.5 ? '⚠ 接近显著，未达常用 5% 阈值'
        : '⚠ 尚不显著',
    },
    {
      label: '分层单调性', value: fmt(mono, 2), raw: mono.toFixed(2),
      bar: clamp01(Math.abs(mono)) * 100, gradeText: strengthLabel(clamp01(Math.abs(mono))),
    },
    {
      label: '多空年化', value: fmtPct(spread * sign), raw: fmtPct(spread),
      cls: spread * sign >= 0 ? 'price-up' : 'price-down',
      bar: clamp01(Math.abs(spread) / 0.20) * 100, gradeText: strengthLabel(clamp01(Math.abs(spread) / 0.20)),
    },
  ]
  return rows
})

const verdictCls = computed(() => statusMeta.value.cls)
const verdictIcon = computed(() =>
  verdictCls.value === 'st-good' ? CircleCheckFilled : verdictCls.value === 'st-insig' || verdictCls.value === 'st-candidate' ? WarningFilled : CircleCloseFilled
)
const verdictText = computed(() => {
  const r = result.value
  if (!r) return ''
  if (r.error) return r.error
  const st = rating.value?.status || '不显著'
  const g = rating.value?.grade || 'D'
  const net = fmtPct(adjNet.value)
  if (isReverse.value) {
    if (st === '有效') return `统计显著的反向因子 — 可作排除名单/反向信号使用，方向校正后净多空 ${net}`
    if (st === '候选') return `反向因子候选 — 经济效果较强（${g} 级），方向稳定，但统计证据不足；不宜直接作为独立信号，建议扩大样本并做稳健性检验`
    return '方向偏反向但不显著 — 暂不参与权重配置，保持观察'
  }
  if (st === '有效') return `统计显著 — 排序能力得到验证，方向校正后净多空 ${net}，可配置较高权重`
  if (st === '候选') return `较强候选价值（实力 ${g} 级）— 但当前样本统计证据不足；建议扩大样本（拉长窗口或提高调仓频率）后再加权`
  return '有数据但统计证据不足 — 暂不加权，拉长时间窗口后再判断'
})

const icItems = computed<StatItem[]>(() => {
  const r = result.value
  if (!r) return []
  return [
    { label: 'RankIC 均值', value: (r.ic_summary.mean * dirSign.value).toFixed(4), cls: r.ic_summary.mean * dirSign.value >= 0 ? 'price-up' : 'price-down' },
    { label: 'ICIR', value: (r.ic_summary.icir * dirSign.value).toFixed(3), cls: 'brand-text' },
    { label: 'IC > 0 占比', value: `${Math.round((isReverse.value ? 1 - r.ic_summary.positive_ratio : r.ic_summary.positive_ratio) * 100)}%` },
    { label: 't 统计量', value: (r.ic_summary.t_stat * dirSign.value).toFixed(2) },
  ]
})

const decayColumns: StockColumn[] = [
  { key: 'horizon', label: '前瞻窗口', format: (r: any) => `+${r.horizon} 日`, mobile: 'title' },
  { key: 'ic_mean', label: 'RankIC 均值', type: 'num', digits: 4, mobile: 'primary' },
  { key: 'icir', label: 'ICIR', type: 'num', digits: 3 },
  { key: 'n', label: '期数', type: 'num', digits: 0, mobile: 'secondary' },
]
const decayRows = computed(() => {
  const sign = dirSign.value
  return (result.value?.decay ?? []).map(d => ({
    horizon: d.horizon,
    ic_mean: d.ic_mean * sign,
    icir: d.icir * sign,
    n: d.n,
  }))
})
const decaySampleN = computed(() => Math.max(0, ...(result.value?.decay ?? []).map(d => d.n)))
const decaySampleWarn = computed(() => (result.value?.decay?.length ?? 0) > 0 && decaySampleN.value < 20)

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
// 计算失败/覆盖不足的行：指标一律 null（显示 —），绝不落 0 —— 避免"没算出来"被当成"因子无效"
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
  grade?: string | null
  composite?: number | null
  confidence?: number | null
  error?: string
}

const SWEEP_KEY = 'factorlab_sweep_v3'
const fullResults = new Map<string, FactorLabResult>()
const sweep = reactive({
  running: false,
  stopped: false,
  current: '',
  done: 0,
  total: 0,
  summaries: [] as SweepRow[],
})

type SweepSortKey = "|ICIR|" | "|RankIC|" | "多空年化" | "经济效果" | "统计可信度"
const sweepSortKey = ref<SweepSortKey>("|ICIR|")
const sweepSortOptions: SegmentOption<SweepSortKey>[] = [
  { label: "|ICIR|", value: "|ICIR|" },
  { label: "|RankIC|", value: "|RankIC|" },
  { label: "多空年化", value: "多空年化" },
  { label: "经济效果", value: "经济效果" },
  { label: "统计可信度", value: "统计可信度" },
]
const sweepSortValue = (r: SweepRow): number => {
  switch (sweepSortKey.value) {
    case "|RankIC|": return Math.abs(r.ic_mean ?? 0)
    case "多空年化": return Math.abs(r.spread ?? 0)
    case "经济效果": return r.composite ?? 0
    case "统计可信度": return r.confidence ?? 0
    default: return Math.abs(r.icir ?? 0)
  }
}
const sweepRowsSorted = computed(() =>
  [...sweep.summaries].sort((a, b) => sweepSortValue(b) - sweepSortValue(a))
)

function sweepVerdictChip(r: FactorLabResult): { text: string; cls: string } {
  const emoji = r.rating?.status === '有效' ? '🟢' : r.rating?.status === '候选' ? '🟡' : '🟠'
  return { text: `${emoji} ${r.rating?.status || '不显著'}`, cls: 'st-insig' }
}

const sweepColumns: StockColumn[] = [
  { key: 'name', label: '策略', mobile: 'title' },
  { key: 'ic_mean', label: 'RankIC', type: 'num', digits: 4, mobile: 'primary' },
  { key: 'icir', label: 'ICIR', type: 'num', digits: 3 },
  { key: 'positive_ratio', label: 'IC>0', align: 'center', mobile: 'secondary',
    format: (r: any) => (r.positive_ratio == null ? '—' : `${Math.round(r.positive_ratio * 100)}%`) },
  { key: 'spread', label: '多空年化', type: 'num', digits: 4, mobile: 'secondary' },
  { key: 't_stat', label: 't 值', type: 'num', digits: 2, mobile: 'hidden' },
  { key: 'grade', label: '经济效果', align: 'center', mobile: 'secondary',
    format: (r: any) => (r.grade == null ? '—' : `${r.grade} · ${r.composite}`) },
  { key: 'verdict', label: '状态', align: 'center', mobile: 'primary' },
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
    row.ic_mean = r.ic_summary.mean
    row.icir = r.ic_summary.icir
    row.positive_ratio = r.ic_summary.positive_ratio
    row.t_stat = r.ic_summary.t_stat
    row.spread = r.top_minus_bottom_annualized
    row.n = r.ic_summary.n
    row.verdict = sweepVerdictChip(r)
    row.grade = r.rating?.grade
    row.confidence = r.rating?.confidence ?? null
    row.composite = r.rating?.strength ?? null
    row.error = undefined
    result.value = r
    saveSweep()
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch {
    row.error = '重试失败'
  } finally {
    sweep.current = ''
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

  const callOnce = (id: string) => runFactorLab({
    strategyId: id,
    startDate: config.startDate,
    endDate: config.endDate,
    rebalance: config.rebalance,
    layers: config.layers,
    maxCodes: 300,
  })

  for (const s of list) {
    if (sweep.stopped) break
    sweep.current = s.name
    let r: FactorLabResult | null = null
    let netErr: string | undefined
    // 瞬时失败（服务重启/网络抖动）自动重试一次，避免把可恢复错误永久记成"计算失败"
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        r = await callOnce(s.id)
        netErr = undefined
        break
      } catch (e) {
        netErr = attempt === 0 ? '瞬时失败已重试' : '分析失败'
        if (attempt === 0) await new Promise(res => setTimeout(res, 1500))
      }
    }

    if (r && !r.error) {
      fullResults.set(s.id, r)
      sweep.summaries.push({
        strategyId: s.id,
        name: s.name,
        ic_mean: r.ic_summary.mean,
        icir: r.ic_summary.icir,
        positive_ratio: r.ic_summary.positive_ratio,
        t_stat: r.ic_summary.t_stat,
        spread: r.top_minus_bottom_annualized,
        n: r.ic_summary.n,
        verdict: sweepVerdictChip(r),
        grade: r.rating?.grade ?? null,
        composite: r.rating?.strength ?? null,
        confidence: r.rating?.confidence ?? null,
      })
    } else {
      const covered = r?.error_kind === 'coverage' || (!!r?.error && r.error.includes('截面不足'))
      sweep.summaries.push({
        strategyId: s.id,
        name: s.name,
        ic_mean: null, icir: null, positive_ratio: null, t_stat: null, spread: null, n: null,
        verdict: {
          text: covered ? '⚪ 覆盖不足' : netErr ? '🔴 计算失败' : '🔴 计算失败',
          cls: covered ? 'st-coverage' : 'st-compute',
        },
        error: r?.error || netErr || '未知原因',
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
  const sign = dirSign.value
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
        value: r.ic * sign,
        itemStyle: { color: r.ic * sign >= 0 ? t.up : t.down },
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
.warn-line { font-size: 12px; color: var(--warn-text); margin-bottom: 8px; }

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
.status-chip { font-size: 11px; padding: 1px 8px; border-radius: var(--radius-pill); font-weight: 500; }
.status-chip.st-good { background: var(--color-green-soft); color: var(--color-green); }
.status-chip.st-candidate { background: var(--brand-soft); color: var(--brand); }
.status-chip.st-insig { background: var(--warn-soft); color: var(--warn-text); }
.status-chip.st-coverage { background: var(--bg-2); color: var(--text-3); }
.status-chip.st-compute { background: var(--color-red-soft); color: var(--color-red); }
.rating-line { display: grid; grid-template-columns: 84px 1fr; gap: 8px; font-size: 12px; }
.rl-k { color: var(--text-3); }
.rl-v { color: var(--text); min-width: 0; }
.rl-raw { color: var(--text-4); font-size: 11px; }
.metrics-block { margin-top: 12px; display: flex; flex-direction: column; gap: 5px;
  padding: 10px 12px; background: var(--bg-2); border-radius: var(--radius); }
.metric-line { display: grid; grid-template-columns: 76px 170px 1fr; align-items: center; gap: 8px; font-size: 12px; }
.metric-line .rl-v { font-variant-numeric: tabular-nums; }
.rl-extra { display: inline-flex; gap: 8px; align-items: center; }
.mini-bar { display: inline-block; width: 90px; height: 6px; border-radius: 3px; background: var(--bg-2); overflow: hidden; }
.mini-fill { display: inline-block; height: 100%; border-radius: 3px; background: var(--brand); }
.rl-grade { font-size: 11px; color: var(--text-3); white-space: nowrap; }
.dims-block { margin-top: 14px; }
.dims-title { font-size: 12px; color: var(--text-3); margin-bottom: 8px; }
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
.dim { display: grid; grid-template-columns: 76px 1fr 34px; align-items: center; gap: 10px; }
.dim-label { font-size: 12px; color: var(--text-3); }
.dim-bar { height: 8px; border-radius: 4px; background: var(--bg-2); overflow: hidden; }
.dim-fill { height: 100%; border-radius: 4px; background: var(--brand); }
.dim-val { font-size: 12px; color: var(--text-2); text-align: right; font-variant-numeric: tabular-nums; }
.flag-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.flag-chip { font-size: 11px; padding: 3px 10px; border-radius: var(--radius-pill);
  background: var(--warn-soft); color: var(--warn-text); }
.rating-meta { display: flex; flex-direction: column; gap: 4px; margin-top: 12px;
  font-size: 12px; color: var(--text-3); }
.rating-meta b { color: var(--text); }

.verdict { display: flex; align-items: center; gap: 12px; padding: 4px 2px; margin-top: 12px; }
.verdict.st-good { color: var(--color-green); }
.verdict.st-candidate, .verdict.st-insig { color: var(--warn-text); }
.verdict.st-compute, .verdict.st-coverage { color: var(--text-3); }
.verdict-main { font-size: 14px; font-weight: 600; color: var(--text); line-height: 1.5; }
@media (max-width: 1000px) { .factor-lab { grid-template-columns: 1fr; } }
</style>
