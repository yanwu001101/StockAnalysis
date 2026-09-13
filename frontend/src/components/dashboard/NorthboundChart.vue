<template>
  <AppCard title="北向资金" :sub="sub" compact>
    <BaseChart :option="option" :height="height" :loading="loading" />
  </AppCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useChartTokens, baseTooltip } from '@/composables/useEcharts'
import AppCard from '@/components/ui/AppCard.vue'
import BaseChart from '@/components/charts/BaseChart.vue'

const props = withDefaults(defineProps<{ data: any[]; height?: number; loading?: boolean }>(), { height: 200, loading: false })
const tokens = useChartTokens()

// data-service 返回 netBuy / holdMarketCap（元）；旧接口字段是 netFlow。
// 2024-08 之后交易所不再公布北向每日净买入，netBuy 全为 0 时退化为持股市值日变动。
const netBuyOf = (d: any): number => Number(d?.netBuy ?? d?.netFlow ?? 0)

const series = computed(() => {
  const rows = props.data || []
  const hasNetBuy = rows.some(d => netBuyOf(d) !== 0)
  if (hasNetBuy) return { label: '净买入', values: rows.map(netBuyOf), rows }
  const values: number[] = []
  const kept: any[] = []
  for (let i = 1; i < rows.length; i++) {
    const prev = Number(rows[i - 1]?.holdMarketCap), cur = Number(rows[i]?.holdMarketCap)
    if (!Number.isFinite(prev) || !Number.isFinite(cur)) continue
    values.push(cur - prev)
    kept.push(rows[i])
  }
  return { label: '持股市值日变动', values, rows: kept }
})

const sub = computed(() => {
  const last = props.data?.[props.data.length - 1]
  const stale = last?.stale ? ` · 数据截至 ${last.date}` : ''
  return series.value.label === '净买入' ? `每日净买入${stale}` : `持股市值日变动（无净买入披露时的替代口径）${stale}`
})

const option = computed<EChartsOption | null>(() => {
  const { values, rows, label } = series.value
  if (!values.length) return null
  const t = tokens.value
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: t.font, color: t.text },
    grid: { left: 48, right: 12, top: 12, bottom: 24 },
    xAxis: { type: 'category', data: rows.map((d: any) => String(d.date || '').slice(5)),
      axisLabel: { color: t.text3, fontSize: 10 },
      axisLine: { lineStyle: { color: t.line } },
      axisTick: { show: false } },
    yAxis: { type: 'value',
      splitLine: { lineStyle: { color: t.line, type: 'dashed' } },
      axisLabel: { color: t.text3, fontSize: 10, formatter: (v: number) => (v / 1e8).toFixed(0) + '亿' },
      axisLine: { show: false }, axisTick: { show: false } },
    series: [{
      name: label,
      type: 'bar',
      data: values.map(v => ({ value: v, itemStyle: { color: v >= 0 ? t.up : t.down, borderRadius: [3, 3, 0, 0] } })),
      barWidth: '60%',
    }],
    tooltip: {
      trigger: 'axis',
      ...baseTooltip(t),
      valueFormatter: (v: any) => (v == null ? '—' : `${(Number(v) / 1e8).toFixed(2)} 亿`),
    },
  }
})
</script>
