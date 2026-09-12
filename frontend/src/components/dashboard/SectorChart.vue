<template>
  <AppCard title="板块涨跌" compact>
    <BaseChart :option="option" :height="height" />
  </AppCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useChartTokens, baseTooltip } from '@/composables/useEcharts'
import type { SectorData } from '@/types'
import AppCard from '@/components/ui/AppCard.vue'
import BaseChart from '@/components/charts/BaseChart.vue'

const props = withDefaults(defineProps<{ sectors: SectorData[]; height?: number }>(), { height: 240 })
const tokens = useChartTokens()

const option = computed<EChartsOption | null>(() => {
  if (!props.sectors?.length) return null
  const t = tokens.value
  const sorted = [...props.sectors].sort((a, b) => b.change - a.change).slice(0, 10)
  const asc = [...sorted].reverse()
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: t.font, color: t.text },
    grid: { left: 80, right: 24, top: 8, bottom: 16 },
    xAxis: { type: 'value',
      splitLine: { lineStyle: { color: t.line, type: 'dashed' } },
      axisLabel: { color: t.text3, fontSize: 10 },
      axisLine: { show: false }, axisTick: { show: false } },
    yAxis: { type: 'category', data: asc.map(s => s.name),
      axisLabel: { color: t.text, fontSize: 12 },
      axisLine: { show: false }, axisTick: { show: false } },
    series: [{
      type: 'bar',
      data: asc.map(s => ({
        value: s.change,
        itemStyle: { color: s.change >= 0 ? t.up : t.down, borderRadius: [0, 3, 3, 0] },
      })),
      barWidth: 12,
    }],
    tooltip: { trigger: 'axis', ...baseTooltip(t) },
  }
})
</script>
