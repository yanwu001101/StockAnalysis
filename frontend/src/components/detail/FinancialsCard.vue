<template>
  <AppCard title="财务与估值" :sub="sub" :loading="loading">
    <template #actions>
      <SegmentTabs v-model="metric" :options="metricOptions" small />
    </template>

    <div v-if="hasQuarters" class="fin-body">
      <!-- 估值分位 -->
      <section v-if="valItems.length" class="val-grid">
        <div class="val-item" v-for="v in valItems" :key="v.label">
          <div class="val-head">
            <span class="val-label">{{ v.label }}</span>
            <span class="val-num">{{ v.value }}</span>
          </div>
          <div class="pctile-track">
            <div class="pctile-fill" :class="{ 'pctile-none': v.pctile == null }"
              :style="{ width: (v.pctile ?? 100) + '%' }"></div>
            <div v-if="v.pctile != null" class="pctile-marker" :style="{ left: v.pctile + '%' }"></div>
          </div>
          <span class="val-foot">{{ v.foot }}</span>
        </div>
      </section>

      <!-- 趋势图 -->
      <BaseChart :option="option" :height="isMobile ? 260 : 300" :loading="loading"
        :placeholder="`暂无${metricLabel}数据`" />
      <p class="fin-foot">
        共 {{ quarters.length }} 个报告期（{{ quarters[0]?.reportDate }} ~ {{ quarters[quarters.length - 1]?.reportDate }}）
        · ROE 与 YoY 为报告期累计口径
        <template v-if="hasIndustry"> · 虚线 = 同期行业中位数</template>
        <template v-else> · 无行业对照（行业缺失或行业成员无同期数据）</template>
      </p>
    </div>

    <el-empty v-else-if="!loading" description="暂无财务数据" :image-size="80" />
  </AppCard>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { useChartTokens, baseTooltip } from '@/composables/useEcharts'
import { useDevice } from '@/composables/useDevice'
import type { FinancialsData, FinQuarter } from '@/api/stock'
import type { SegmentOption } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import BaseChart from '@/components/charts/BaseChart.vue'

const props = defineProps<{ data: FinancialsData | null; loading: boolean }>()
const tokens = useChartTokens()
const { isMobile } = useDevice()

type Metric = 'revenue' | 'profit' | 'roe'
const metric = ref<Metric>('revenue')
const metricOptions: SegmentOption<Metric>[] = [
  { label: '营收', value: 'revenue' },
  { label: '净利润', value: 'profit' },
  { label: 'ROE', value: 'roe' },
]
const metricLabel = computed(() =>
  metric.value === 'revenue' ? '营收' : metric.value === 'profit' ? '净利润' : 'ROE')

const quarters = computed<FinQuarter[]>(() => props.data?.quarters || [])
const valuation = computed(() => props.data?.valuation || null)
const hasQuarters = computed(() => quarters.value.length > 0)
const hasIndustry = computed(() => quarters.value.some(q => q.indRoe != null || q.indRevenueYoy != null))

const sub = computed(() => {
  const ind = props.data?.industry
  const n = quarters.value.length
  if (!n) return ind ? `行业 ${ind}` : undefined
  return `行业 ${ind || '—'} · ${n} 个报告期`
})

const fmtRatio = (v: number | null | undefined) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : '—'
const fmtPct = (v: number | null | undefined) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) + '%' : '—'

const valItems = computed(() => {
  const val = valuation.value
  if (!val) return []
  const out: { label: string; value: string; pctile: number | null | undefined; foot: string }[] = [
    { label: 'PE (TTM)', value: fmtRatio(val.pe), pctile: val.pePctile,
      foot: `行业内分位 ${val.pePctile != null ? val.pePctile.toFixed(0) + '%' : '—'}（越低越便宜）` },
    { label: 'PB', value: fmtRatio(val.pb), pctile: val.pbPctile,
      foot: `行业内分位 ${val.pbPctile != null ? val.pbPctile.toFixed(0) + '%' : '—'}（越低越便宜）` },
    { label: 'ROE（最新报告期）', value: fmtPct(val.roe ?? null), pctile: val.roePctile,
      foot: `行业内分位 ${val.roePctile != null ? val.roePctile.toFixed(0) + '%' : '—'}（越高越强）` },
  ]
  return out
})

function qLabel(d: string | null): string {
  const s = String(d || '')
  if (s.length < 10) return s
  const q = Math.floor(Number(s.slice(5, 7)) / 3) + 1
  return `${s.slice(2, 4)}Q${q}`
}
const yi = (v: number | null) => (v == null ? null : v / 1e8)

const option = computed<EChartsOption | null>(() => {
  const qs = quarters.value
  if (!qs.length) return null
  const t = tokens.value
  const labels = qs.map(q => qLabel(q.reportDate))

  if (metric.value === 'roe') {
    return {
      backgroundColor: 'transparent',
      textStyle: { fontFamily: t.font, color: t.text },
      grid: { left: 44, right: 16, top: 30, bottom: 24 },
      legend: { top: 0, right: 0, textStyle: { color: t.text3, fontSize: 11 }, itemWidth: 14 },
      xAxis: { type: 'category', data: labels,
        axisLabel: { color: t.text3, fontSize: 10 },
        axisLine: { lineStyle: { color: t.line } }, axisTick: { show: false } },
      yAxis: { type: 'value',
        splitLine: { lineStyle: { color: t.line, type: 'dashed' } },
        axisLabel: { color: t.text3, fontSize: 10, formatter: '{value}%' },
        axisLine: { show: false }, axisTick: { show: false } },
      series: [
        { name: 'ROE(累计)', type: 'line', data: qs.map(q => q.roe),
          lineStyle: { width: 2, color: t.brand }, itemStyle: { color: t.brand },
          symbolSize: 5, connectNulls: true },
        { name: '行业中位', type: 'line', data: qs.map(q => q.indRoe),
          lineStyle: { width: 1.5, type: 'dashed', color: t.text4 }, itemStyle: { color: t.text4 },
          symbol: 'none', connectNulls: true },
      ],
      tooltip: { trigger: 'axis', ...baseTooltip(t),
        valueFormatter: (v: any) => (v == null ? '—' : `${Number(v).toFixed(2)}%`) },
    }
  }

  const isRev = metric.value === 'revenue'
  const barName = isRev ? '营收(亿)' : '净利润(亿)'
  const yoyName = isRev ? '营收YoY' : '净利YoY'
  const indName = isRev ? '行业中位YoY' : '行业中位YoY'
  const barData = qs.map(q => {
    const v = yi(isRev ? q.revenue : q.netProfit)
    return v == null ? null : { value: v,
      itemStyle: { color: v >= 0 ? t.up : t.down, borderRadius: [3, 3, 0, 0], opacity: 0.75 } }
  })
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: t.font, color: t.text },
    grid: { left: 52, right: 46, top: 30, bottom: 24 },
    legend: { top: 0, right: 0, textStyle: { color: t.text3, fontSize: 11 }, itemWidth: 14 },
    xAxis: { type: 'category', data: labels,
      axisLabel: { color: t.text3, fontSize: 10 },
      axisLine: { lineStyle: { color: t.line } }, axisTick: { show: false } },
    yAxis: [
      { type: 'value',
        splitLine: { lineStyle: { color: t.line, type: 'dashed' } },
        axisLabel: { color: t.text3, fontSize: 10 }, axisLine: { show: false }, axisTick: { show: false } },
      { type: 'value',
        splitLine: { show: false },
        axisLabel: { color: t.text3, fontSize: 10, formatter: '{value}%' },
        axisLine: { show: false }, axisTick: { show: false } },
    ],
    series: [
      { name: barName, type: 'bar', data: barData, barWidth: '42%' },
      { name: yoyName, type: 'line', yAxisIndex: 1, data: qs.map(q => isRev ? q.revenueYoy : q.netProfitYoy),
        lineStyle: { width: 2, color: t.series[1] }, itemStyle: { color: t.series[1] }, symbolSize: 4 },
      { name: indName, type: 'line', yAxisIndex: 1, data: qs.map(q => isRev ? q.indRevenueYoy : q.indNetProfitYoy),
        lineStyle: { width: 1.5, type: 'dashed', color: t.text4 }, itemStyle: { color: t.text4 }, symbol: 'none' },
    ],
    tooltip: { trigger: 'axis', ...baseTooltip(t) },
  }
})
</script>

<style scoped>
.fin-body { display: flex; flex-direction: column; gap: 14px; }
.val-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.val-item {
  display: flex; flex-direction: column; gap: 6px;
  background: var(--surface-2);
  border-radius: var(--radius);
  padding: 10px 12px;
}
.val-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.val-label { font-size: 12px; color: var(--text-3); }
.val-num { font-size: 16px; font-weight: 700; color: var(--text); }
.val-foot { font-size: 11px; color: var(--text-3); }
.pctile-track {
  position: relative; height: 6px; border-radius: 3px;
  background: var(--bg-2);
}
.pctile-fill {
  height: 100%; border-radius: 3px;
  background: var(--brand-soft);
}
.pctile-none { opacity: 0.4; }
.pctile-marker {
  position: absolute; top: -3px; width: 2px; height: 12px;
  border-radius: 1px; background: var(--brand);
  transform: translateX(-1px);
}
.fin-foot { margin: 0; font-size: 11px; line-height: 1.6; color: var(--text-3); }
@media (max-width: 768px) {
  .val-grid { grid-template-columns: 1fr; gap: 8px; }
}
</style>
