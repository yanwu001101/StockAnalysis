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
            按得分分 {{ config.layers }} 层，检验排序能力。分层为等权纸面组合，不计成本。
          </p>
        </el-form>
      </AppCard>
    </div>

    <div class="result-area" v-if="result">
      <AppCard title="检验结论">
        <div class="verdict" :class="verdictCls">
          <el-icon :size="20"><component :is="verdictIcon" /></el-icon>
          <div class="verdict-text">
            <div class="verdict-main">{{ verdictText }}</div>
            <div class="verdict-sub">
              RankIC 均值 {{ fmtPct(result.ic_summary.mean) }} · ICIR {{ result.ic_summary.icir }} ·
              样本 {{ result.ic_summary.n }} 期 · 覆盖 {{ result.codes_analyzed }} 只 ·
              多空年化差 {{ fmtPct(result.top_minus_bottom_annualized) }}
            </div>
          </div>
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

    <EmptyState v-if="!loading && !result && !isMobile" title="选择策略开始检验"
        description="检验策略得分对未来收益的排序能力：IC、分层净值与衰减分析"
        class="empty-hint" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
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

// 方向判定：反转类策略（负 IC）同样有效，看 |ICIR| 与分层单调性
const absIcir = computed(() => Math.abs(result.value?.ic_summary.icir ?? 0))
const verdictCls = computed(() => (absIcir.value >= 0.3 ? 'good' : absIcir.value >= 0.1 ? 'mid' : 'bad'))
const verdictIcon = computed(() =>
  absIcir.value >= 0.3 ? CircleCheckFilled : absIcir.value >= 0.1 ? WarningFilled : CircleCloseFilled
)
const verdictText = computed(() => {
  const s = result.value?.ic_summary
  if (!s) return ''
  const significant = Math.abs(s.t_stat) >= 2
  if (absIcir.value >= 0.3 && significant) return '因子有效 — 排序能力较强且统计显著，可给更高权重'
  if (absIcir.value >= 0.1) {
    return significant
      ? '因子弱有效 — 有一定排序能力，建议低权重'
      : '方向有迹象但统计不显著（|t| < 2）— 建议拉长时间窗口再判断，暂不加权'
  }
  return '因子无效 — 得分与未来收益几乎无关，建议关闭或重做'
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
    result.value = await runFactorLab({
      strategyId: config.strategyId,
      startDate: config.startDate,
      endDate: config.endDate,
      rebalance: config.rebalance,
      layers: config.layers,
      maxCodes: 300,
    })
    ElMessage.success('因子检验完成')
  } catch {
    ElMessage.error('因子检验失败')
  } finally {
    loading.value = false
  }
}

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

.verdict { display: flex; align-items: center; gap: 12px; padding: 4px 2px; }
.verdict.good { color: var(--color-green); }
.verdict.mid { color: var(--warn-text); }
.verdict.bad { color: var(--color-red); }
.verdict-text { min-width: 0; }
.verdict-main { font-size: 15px; font-weight: 600; color: var(--text); }
.verdict-sub { font-size: 12px; color: var(--text-3); margin-top: 2px; }
@media (max-width: 1000px) { .factor-lab { grid-template-columns: 1fr; } }
</style>
