/**
 * CandleChart — ECharts candlestick with buy/sell markPoints and day linkage.
 *
 * Date alignment is exact by construction: the x-axis categories ARE
 * `dates`, and every marker is placed at the index of its own date string.
 * A marker whose date is missing from the axis is dropped, never shifted.
 *
 * Clicking a candle emits `select(date)` — the analysis workspace reacts by
 * updating the day inspector and the agent thoughts panel. The currently
 * selected day is drawn as a vertical markLine.
 *
 * Colours follow the A-share convention: 红涨绿跌 (up #F85149 / down #3FB950).
 */
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts/core'
import { CandlestickChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import {
  DataZoomComponent,
  GridComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
} from 'echarts/components'
import type { EChartsOption } from 'echarts'
import type { ChartMarker } from '@/types/quant'

echarts.use([
  CandlestickChart,
  CanvasRenderer,
  DataZoomComponent,
  GridComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
])

const props = defineProps<{
  symbol: string
  candles: readonly number[][]
  dates: readonly string[]
  markers: readonly ChartMarker[]
  /** 当前选中日（YYYY-MM-DD）；null 表示未选中 */
  selectedDate?: string | null
}>()

const emit = defineEmits<{
  (event: 'select', date: string): void
}>()

const chartEl = ref<HTMLDivElement | null>(null)
const chart = shallowRef<echarts.ECharts | null>(null)

const UP = '#F85149'
const DOWN = '#3FB950'
const ACCENT = '#2F81F7'

function buildOption(): EChartsOption {
  const dateIndex = new Map<string, number>()
  props.dates.forEach((date, index) => {
    if (!dateIndex.has(date)) dateIndex.set(date, index)
  })

  const markPoints = props.markers
    .map((marker) => {
      const index = dateIndex.get(marker.date)
      if (index === undefined) return null
      return {
        name: marker.action,
        coord: [index, marker.price],
        value: marker.action === 'BUY' ? '买' : '卖',
        itemStyle: { color: marker.action === 'BUY' ? UP : DOWN },
        reason: marker.reason,
      }
    })
    .filter((point): point is NonNullable<typeof point> => point !== null)

  const selectedIndex =
    props.selectedDate !== null && props.selectedDate !== undefined
      ? dateIndex.get(props.selectedDate)
      : undefined

  return {
    animation: false,
    backgroundColor: 'transparent',
    grid: { left: 56, right: 16, top: 24, bottom: 48 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: '#12161D',
      borderColor: '#2A3340',
      textStyle: { color: '#E6EDF3', fontSize: 12 },
      formatter: (params: unknown) => {
        const list = params as Array<{
          axisValue: string
          data: number[]
        }>
        const candle = list[0]
        if (!candle) return ''
        const [open, close, low, high] = candle.data
        const change = ((close - open) / open) * 100
        const color = close >= open ? UP : DOWN
        return [
          `<div style="font-family:'JetBrains Mono',monospace">${candle.axisValue}</div>`,
          `开 ${open.toFixed(2)}　收 ${close.toFixed(2)}`,
          `低 ${low.toFixed(2)}　高 ${high.toFixed(2)}`,
          `<span style="color:${color}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</span>`,
        ].join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: [...props.dates],
      boundaryGap: true,
      axisLine: { lineStyle: { color: '#1E242C' } },
      axisLabel: { color: '#5D6B7A', fontSize: 11 },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: '#5D6B7A', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' },
      splitLine: { lineStyle: { color: '#12161D' } },
      axisLine: { show: false },
    },
    dataZoom: [
      { type: 'inside', start: 60, end: 100 },
      {
        type: 'slider',
        height: 18,
        bottom: 8,
        borderColor: '#1E242C',
        textStyle: { color: '#5D6B7A', fontSize: 10 },
        fillerColor: 'rgba(47,129,247,0.12)',
      },
    ],
    series: [
      {
        type: 'candlestick',
        data: props.candles.map((candle) => [...candle]),
        itemStyle: {
          color: UP, // 阳线实体（收 >= 开）
          color0: DOWN, // 阴线实体
          borderColor: UP,
          borderColor0: DOWN,
        },
        markPoint:
          markPoints.length > 0
            ? {
                symbol: 'pin',
                symbolSize: 44,
                data: markPoints,
                label: {
                  color: '#0A0E14',
                  fontSize: 11,
                  fontWeight: 700,
                },
                tooltip: {
                  formatter: (param: unknown) => {
                    const point = param as { data: { reason: string } }
                    return point.data.reason
                  },
                },
              }
            : undefined,
        markLine:
          selectedIndex !== undefined
            ? {
                silent: true,
                symbol: 'none',
                lineStyle: { color: ACCENT, width: 1, type: 'dashed' },
                label: { show: false },
                data: [{ xAxis: selectedIndex }],
              }
            : undefined,
      },
    ],
  }
}

function render(): void {
  if (chart.value === null && chartEl.value !== null) {
    chart.value = echarts.init(chartEl.value, undefined, { renderer: 'canvas' })
    // 点击任意 K 线 -> 选中该交易日，驱动左右面板联动
    chart.value.on('click', (params: unknown) => {
      const event = params as { componentType?: string; dataIndex?: number }
      if (event.componentType !== 'series') return
      const index = event.dataIndex
      if (typeof index !== 'number' || index < 0 || index >= props.dates.length) return
      const date = props.dates[index]
      if (date !== undefined) emit('select', date)
    })
  }
  chart.value?.setOption(buildOption(), { notMerge: true })
}

watch(
  () => [props.candles, props.dates, props.markers, props.selectedDate],
  render,
  { deep: true },
)

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
  min-height: 320px;
}
</style>
