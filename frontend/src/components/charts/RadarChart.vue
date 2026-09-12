<template>
  <div ref="chartRef" class="radar-chart" :style="{ height: height + 'px' }"></div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { useEcharts, useChartTokens, hexToRgba } from '@/composables/useEcharts'

const props = withDefaults(defineProps<{
  indicators: { name: string; max: number }[]
  values: number[]
  label?: string
  color?: string
  height?: number
}>(), {
  height: 420,
})

const chartRef = ref<HTMLElement>()
const tokens = useChartTokens()

function buildOption(): EChartsOption {
  const t = tokens.value
  const color = props.color || t.brand
  // 轴数一多（如 22 个策略）标签必然互相重叠；名称由旁边的评分列表承载，
  // 雷达只保留轮廓形状。
  const crowded = props.indicators.length > 12
  const indicatorsWithBreak = props.indicators.map(it => ({
    ...it,
    name: crowded ? '' : it.name.length > 6 ? it.name.replace(/(.{6})/, '$1\n') : it.name,
  }))
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: t.font },
    radar: {
      indicator: indicatorsWithBreak,
      shape: 'polygon',
      center: ['50%', '54%'],
      radius: crowded ? '72%' : '66%',
      axisNameGap: 8,
      axisName: { color: t.text3, fontSize: 11, lineHeight: 14, padding: [2, 2] },
      splitArea: { areaStyle: { color: [t.surface, t.surface2] } },
      splitLine: { lineStyle: { color: t.line } },
      axisLine: { lineStyle: { color: t.lineStrong } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: props.values,
        name: props.label || '',
        areaStyle: { color: hexToRgba(color, 0.15) },
        lineStyle: { color, width: 2 },
        itemStyle: { color },
        symbol: 'circle',
        symbolSize: 5,
      }],
    }],
  }
}

useEcharts(chartRef, buildOption, () => [props.values, props.indicators, tokens.value])
</script>

<style scoped>
.radar-chart { width: 100%; }
</style>
