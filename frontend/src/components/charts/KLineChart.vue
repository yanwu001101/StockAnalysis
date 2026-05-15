<template>
  <div ref="chartRef" class="kline-chart" :style="{ height: height + 'px' }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { KLineData } from '@/types'

const props = withDefaults(defineProps<{
  data: KLineData[]
  height?: number
  showMacd?: boolean
  showVolume?: boolean
}>(), {
  height: 500,
  showMacd: true,
  showVolume: true,
})

const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

function buildOption() {
  if (!props.data?.length) return {}

  const dates = props.data.map(d => d.date)
  const ohlc = props.data.map(d => [d.open, d.close, d.low, d.high])
  const volumes = props.data.map(d => d.volume)
  const closes = props.data.map(d => d.close)

  // Calculate MAs
  const ma5 = calcMA(closes, 5)
  const ma10 = calcMA(closes, 10)
  const ma20 = calcMA(closes, 20)
  const ma60 = calcMA(closes, 60)

  // Calculate MACD
  const { dif, dea, macdHist } = calcMACD(closes)

  const grids: any[] = [
    { left: 60, right: 40, top: 60, height: props.showVolume ? '40%' : '60%' },
  ]
  const xAxes: any[] = [
    { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#2A3A4A' } } },
  ]
  const yAxes: any[] = [
    { gridIndex: 0, scale: true, splitLine: { lineStyle: { color: 'rgba(42,58,74,0.5)' } }, axisLabel: { color: '#8892A4' } },
  ]

  let gridIndex = 1
  const series: any[] = [
    {
      name: 'K线',
      type: 'candlestick',
      data: ohlc,
      xAxisIndex: 0,
      yAxisIndex: 0,
      itemStyle: {
        color: '#FF4757',
        color0: '#2AE8A4',
        borderColor: '#FF4757',
        borderColor0: '#2AE8A4',
      },
    },
    { name: 'MA5', type: 'line', data: ma5, xAxisIndex: 0, yAxisIndex: 0, smooth: true, lineStyle: { width: 1 }, symbol: 'none', itemStyle: { color: '#FFC312' } },
    { name: 'MA10', type: 'line', data: ma10, xAxisIndex: 0, yAxisIndex: 0, smooth: true, lineStyle: { width: 1 }, symbol: 'none', itemStyle: { color: '#00D4FF' } },
    { name: 'MA20', type: 'line', data: ma20, xAxisIndex: 0, yAxisIndex: 0, smooth: true, lineStyle: { width: 1 }, symbol: 'none', itemStyle: { color: '#A78BFA' } },
    { name: 'MA60', type: 'line', data: ma60, xAxisIndex: 0, yAxisIndex: 0, smooth: true, lineStyle: { width: 1 }, symbol: 'none', itemStyle: { color: '#FF6B81' } },
  ]

  if (props.showVolume) {
    grids.push({ left: 60, right: 40, top: '58%', height: '10%' })
    xAxes.push({ type: 'category', data: dates, gridIndex: gridIndex, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#2A3A4A' } } })
    yAxes.push({ gridIndex: gridIndex, scale: true, splitLine: { show: false }, axisLabel: { show: false } })
    series.push({
      name: '成交量',
      type: 'bar',
      data: volumes.map((v, i) => ({
        value: v,
        itemStyle: { color: props.data[i].close >= props.data[i].open ? 'rgba(255,71,87,0.5)' : 'rgba(42,232,164,0.5)' },
      })),
      xAxisIndex: gridIndex,
      yAxisIndex: gridIndex,
    })
    gridIndex++
  }

  if (props.showMacd) {
    grids.push({ left: 60, right: 40, top: props.showVolume ? '73%' : '65%', height: '12%' })
    xAxes.push({ type: 'category', data: dates, gridIndex: gridIndex, axisLabel: { color: '#8892A4', fontSize: 10 }, axisLine: { lineStyle: { color: '#2A3A4A' } } })
    yAxes.push({ gridIndex: gridIndex, scale: true, splitLine: { show: false }, axisLabel: { show: false } })
    series.push(
      { name: 'DIF', type: 'line', data: dif, xAxisIndex: gridIndex, yAxisIndex: gridIndex, lineStyle: { width: 1 }, symbol: 'none', itemStyle: { color: '#00D4FF' } },
      { name: 'DEA', type: 'line', data: dea, xAxisIndex: gridIndex, yAxisIndex: gridIndex, lineStyle: { width: 1 }, symbol: 'none', itemStyle: { color: '#FFC312' } },
      {
        name: 'MACD',
        type: 'bar',
        data: macdHist.map(v => ({ value: v, itemStyle: { color: v >= 0 ? '#FF4757' : '#2AE8A4' } })),
        xAxisIndex: gridIndex,
        yAxisIndex: gridIndex,
      },
    )
  }

  return {
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(15,32,53,0.95)',
      borderColor: 'rgba(0,212,255,0.2)',
      textStyle: { color: '#E8EDF3', fontSize: 12 },
    },
    legend: {
      data: ['MA5', 'MA10', 'MA20', 'MA60'],
      top: 10,
      textStyle: { color: '#8892A4', fontSize: 11 },
      inactiveColor: '#5A6577',
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: xAxes.map((_, i) => i), start: 60, end: 100 },
      { type: 'slider', xAxisIndex: xAxes.map((_, i) => i), bottom: 5, height: 20, borderColor: 'transparent', backgroundColor: 'rgba(0,212,255,0.05)', fillerColor: 'rgba(0,212,255,0.1)', handleStyle: { color: '#00D4FF' }, textStyle: { color: '#8892A4' } },
    ],
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    series,
  }
}

function calcMA(data: number[], period: number): (number | null)[] {
  const result: (number | null)[] = []
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) { result.push(null); continue }
    let sum = 0
    for (let j = 0; j < period; j++) sum += data[i - j]
    result.push(+(sum / period).toFixed(2))
  }
  return result
}

function calcMACD(closes: number[], fast = 12, slow = 26, signal = 9) {
  const emaFast = calcEMA(closes, fast)
  const emaSlow = calcEMA(closes, slow)
  const dif = emaFast.map((v, i) => +(v - emaSlow[i]).toFixed(4))
  const dea = calcEMA(dif, signal).map(v => +v.toFixed(4))
  const macdHist = dif.map((v, i) => +((v - dea[i]) * 2).toFixed(4))
  return { dif, dea, macdHist }
}

function calcEMA(data: number[], period: number): number[] {
  const k = 2 / (period + 1)
  const result = [data[0]]
  for (let i = 1; i < data.length; i++) {
    result.push(data[i] * k + result[i - 1] * (1 - k))
  }
  return result.map(v => +v.toFixed(4))
}

onMounted(() => {
  nextTick(() => {
    if (chartRef.value) {
      chart = echarts.init(chartRef.value)
      chart.setOption(buildOption())
      window.addEventListener('resize', () => chart?.resize())
    }
  })
})

onUnmounted(() => {
  chart?.dispose()
  window.removeEventListener('resize', () => chart?.resize())
})

watch(() => props.data, () => {
  chart?.setOption(buildOption(), true)
}, { deep: true })
</script>

<style scoped>
.kline-chart {
  width: 100%;
  background: var(--bg-card);
  border-radius: var(--border-radius);
  border: 1px solid var(--glass-border);
}
</style>
