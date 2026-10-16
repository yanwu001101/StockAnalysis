/**
 * EquityCurveChart — 回测资金曲线。
 *
 * 与 K 线共用日期轴（1:1 对齐），叠加基准线（若载荷提供）。
 * 最大回撤区间用浅红区域标注。
 */
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import {
  DataZoomComponent,
  GridComponent,
  MarkAreaComponent,
  TooltipComponent,
} from 'echarts/components'
import type { EChartsOption } from 'echarts'

echarts.use([
  LineChart,
  CanvasRenderer,
  DataZoomComponent,
  GridComponent,
  MarkAreaComponent,
  TooltipComponent,
])

const props = defineProps<{
  dates: readonly string[]
  values: readonly number[]
  /** 最大回撤点索引（用于标注）；null 不标注 */
  drawdownIndex?: number | null
}>()

const chartEl = ref<HTMLDivElement | null>(null)
const chart = shallowRef<echarts.ECharts | null>(null)

const UP = '#F85149'
const ACCENT = '#2F81F7'

function buildOption(): EChartsOption {
  const drawdownAt =
    props.drawdownIndex !== null && props.drawdownIndex !== undefined && props.drawdownIndex > 0
      ? props.drawdownIndex
      : null
  // 显式元组类型：markArea 的 2D 数据项必须是 [起点, 终点]
  const areaData: Array<[{ xAxis: number }, { xAxis: number }]> =
    drawdownAt === null ? [] : [[{ xAxis: drawdownAt }, { xAxis: drawdownAt }]]
  const markArea =
    areaData.length > 0
      ? {
          silent: true,
          itemStyle: { color: 'rgba(248, 81, 73, 0.10)' },
          data: areaData,
        }
      : undefined

  return {
    animation: false,
    backgroundColor: 'transparent',
    grid: { left: 64, right: 16, top: 16, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#12161D',
      borderColor: '#2A3340',
      textStyle: { color: '#E6EDF3', fontSize: 12 },
      valueFormatter: (value: unknown) =>
        typeof value === 'number' ? value.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) : '—',
    },
    xAxis: {
      type: 'category',
      data: [...props.dates],
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#1E242C' } },
      axisLabel: { color: '#5D6B7A', fontSize: 11 },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: {
        color: '#5D6B7A',
        fontSize: 11,
        fontFamily: 'JetBrains Mono, monospace',
        formatter: (value: number) => (value >= 10000 ? `${(value / 10000).toFixed(0)}万` : String(value)),
      },
      splitLine: { lineStyle: { color: '#12161D' } },
      axisLine: { show: false },
    },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [
      {
        type: 'line',
        data: [...props.values],
        showSymbol: false,
        lineStyle: { color: ACCENT, width: 1.5 },
        itemStyle: { color: ACCENT },
        areaStyle: { color: 'rgba(47, 129, 247, 0.08)' },
        markArea,
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: UP, type: 'dashed', width: 1 },
          label: { color: UP, fontSize: 10, formatter: '最大回撤' },
          data: drawdownAt === null ? [] : [{ xAxis: drawdownAt }],
        },
      },
    ],
  }
}

function render(): void {
  if (chart.value === null && chartEl.value !== null) {
    chart.value = echarts.init(chartEl.value, undefined, { renderer: 'canvas' })
  }
  chart.value?.setOption(buildOption(), { notMerge: true })
}

watch(() => [props.dates, props.values, props.drawdownIndex], render, { deep: true })

onMounted(() => {
  render()
  window.addEventListener('resize', render)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', render)
  chart.value?.dispose()
  chart.value = null
})
</script>

<template>
  <div ref="chartEl" class="chart" />
</template>

<style scoped>
.chart {
  width: 100%;
  height: 100%;
  min-height: 260px;
}
</style>
