<template>
  <div class="kline-wrap" :style="{ height: height + 'px' }">
    <div v-if="loading" class="chart-loading">
      <div class="skeleton-block" style="flex: 1; height: 100%;"></div>
    </div>
    <div v-else-if="!data?.length" class="chart-overlay">
      <span>暂无K线数据</span>
    </div>
    <div v-show="!loading && !!data?.length" ref="chartRef" class="kline-chart" :style="{ height: height + 'px' }"></div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { EChartsOption } from 'echarts'
import type { KLineData } from '@/types'
import { useEcharts, useChartTokens, baseTooltip, hexToRgba } from '@/composables/useEcharts'

const props = withDefaults(defineProps<{
  data: KLineData[]
  height?: number
  showMacd?: boolean
  showVolume?: boolean
  loading?: boolean
}>(), {
  height: 500,
  showMacd: true,
  showVolume: true,
  loading: false,
})

const chartRef = ref<HTMLElement>()
const tokens = useChartTokens()

function buildOption(): EChartsOption | null {
  if (!props.data?.length) return null
  const t = tokens.value
  const MA_COLORS = t.ma
  const compact = (chartRef.value?.clientWidth || 800) < 560
  const left = compact ? 44 : 60
  const right = compact ? 12 : 40

  const dates = props.data.map(d => d.date)
  const ohlc = props.data.map(d => [d.open, d.close, d.low, d.high])
  const volumes = props.data.map(d => d.volume)
  const closes = props.data.map(d => d.close)

  const ma5 = calcMA(closes, 5)
  const ma10 = calcMA(closes, 10)
  const ma20 = calcMA(closes, 20)
  const ma60 = calcMA(closes, 60)
  const { dif, dea, macdHist } = calcMACD(closes)

  const grids: any[] = [
    { left, right, top: 40, height: props.showVolume ? '42%' : '62%' },
  ]
  const xAxes: any[] = [
    { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: t.line } } },
  ]
  const yAxes: any[] = [
    { gridIndex: 0, scale: true, splitLine: { lineStyle: { color: t.line, type: 'dashed' } }, axisLabel: { color: t.text3, fontSize: 10 } },
  ]

  let gridIndex = 1
  const series: any[] = [
    {
      name: 'K线',
      type: 'candlestick',
      data: ohlc,
      xAxisIndex: 0,
      yAxisIndex: 0,
      itemStyle: { color: t.up, color0: t.down, borderColor: t.up, borderColor0: t.down },
    },
    ...[['MA5', ma5], ['MA10', ma10], ['MA20', ma20], ['MA60', ma60]].map(([name, data], i) => ({
      name, type: 'line', data, xAxisIndex: 0, yAxisIndex: 0, smooth: true,
      lineStyle: { width: 1 }, symbol: 'none', itemStyle: { color: MA_COLORS[i] },
    })),
  ]

  if (props.showVolume) {
    grids.push({ left, right, top: '60%', height: '10%' })
    xAxes.push({ type: 'category', data: dates, gridIndex, axisLabel: { show: false }, axisLine: { lineStyle: { color: t.line } } })
    yAxes.push({ gridIndex, scale: true, splitLine: { show: false }, axisLabel: { show: false } })
    series.push({
      name: '成交量',
      type: 'bar',
      data: volumes.map((v, i) => ({
        value: v,
        itemStyle: { color: props.data[i].close >= props.data[i].open ? hexToRgba(t.up, 0.5) : hexToRgba(t.down, 0.5) },
      })),
      xAxisIndex: gridIndex,
      yAxisIndex: gridIndex,
    })
    gridIndex++
  }

  if (props.showMacd) {
    grids.push({ left, right, top: props.showVolume ? '74%' : '66%', height: '12%' })
    xAxes.push({ type: 'category', data: dates, gridIndex, axisLabel: { color: t.text3, fontSize: 10 }, axisLine: { lineStyle: { color: t.line } } })
    yAxes.push({ gridIndex, scale: true, splitLine: { show: false }, axisLabel: { show: false } })
    series.push(
      { name: 'DIF', type: 'line', data: dif, xAxisIndex: gridIndex, yAxisIndex: gridIndex, lineStyle: { width: 1 }, symbol: 'none', itemStyle: { color: MA_COLORS[1] } },
      { name: 'DEA', type: 'line', data: dea, xAxisIndex: gridIndex, yAxisIndex: gridIndex, lineStyle: { width: 1 }, symbol: 'none', itemStyle: { color: MA_COLORS[0] } },
      {
        name: 'MACD',
        type: 'bar',
        data: macdHist.map(v => ({ value: v, itemStyle: { color: v >= 0 ? t.up : t.down } })),
        xAxisIndex: gridIndex,
        yAxisIndex: gridIndex,
      },
    )
  }

  return {
    backgroundColor: 'transparent',
    animation: false,
    textStyle: { fontFamily: t.font },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', label: { backgroundColor: t.text3 } },
      ...baseTooltip(t),
      confine: true,
    },
    legend: {
      data: ['MA5', 'MA10', 'MA20', 'MA60'],
      top: 6,
      textStyle: { color: t.text3, fontSize: 11 },
      inactiveColor: t.text4,
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: xAxes.map((_, i) => i), start: compact ? 70 : 60, end: 100 },
      { type: 'slider', xAxisIndex: xAxes.map((_, i) => i), bottom: 4, height: 18,
        borderColor: 'transparent', backgroundColor: t.surface2, fillerColor: hexToRgba(t.brand, 0.15),
        handleStyle: { color: t.brand }, textStyle: { color: t.text3 }, dataBackground: { lineStyle: { color: t.line }, areaStyle: { color: t.line } } },
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

useEcharts(chartRef, buildOption, () => [props.data, tokens.value, props.showMacd, props.showVolume])
</script>

<style scoped>
.kline-wrap { position: relative; width: 100%; min-width: 0; }
.kline-chart { width: 100%; }
.chart-loading { position: absolute; inset: 0; display: flex; }
</style>
