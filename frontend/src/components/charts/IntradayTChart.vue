<template>
  <div ref="chartRef" class="intraday-t-chart" :style="{ height: height + 'px' }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { TSignal } from '@/api/t'

const props = withDefaults(defineProps<{ signal: TSignal | null; height?: number }>(), {
  height: 300,
})

const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

const UP = '#FF4757'    // A 股红涨
const DOWN = '#2AE8A4'  // 绿跌

function buildOption() {
  const s = props.signal
  if (!s || !s.trend || !s.trend.length) return {}
  const trend = s.trend
  const times = trend.map(d => d.t)
  const prices = trend.map(d => d.price)
  const avgs = trend.map(d => d.avg)
  const vols = trend.map(d => d.vol)
  const prev = (s.prev_close ?? prices[0]) as number
  const lineColor = s.price != null && s.price >= prev ? UP : DOWN

  // y 轴范围:纳入价格/均价/昨收/买卖区/支撑压力/成本
  const extra: number[] = [prev]
  if (s.buy_zone) extra.push(s.buy_zone[0], s.buy_zone[1])
  if (s.sell_zone) extra.push(s.sell_zone[0], s.sell_zone[1])
  extra.push(...(s.supports || []), ...(s.resists || []))
  if (s.position?.avg_cost) extra.push(s.position.avg_cost)
  const allv = ([...prices, ...avgs, ...extra]).filter(v => v != null && isFinite(v as number)) as number[]
  const ymin = Math.min(...allv)
  const ymax = Math.max(...allv)
  const pad = (ymax - ymin) * 0.08 || ymax * 0.01

  // 买卖区色带:低吸区红、高抛区绿(A 股习惯)
  const areas: any[] = []
  if (s.buy_zone) areas.push([{ yAxis: s.buy_zone[0], itemStyle: { color: 'rgba(255,71,87,0.10)' } }, { yAxis: s.buy_zone[1] }])
  if (s.sell_zone) areas.push([{ yAxis: s.sell_zone[0], itemStyle: { color: 'rgba(42,232,164,0.10)' } }, { yAxis: s.sell_zone[1] }])

  // 关键横线:昨收/成本/支撑/压力
  const lines: any[] = [
    { yAxis: prev, lineStyle: { color: '#8892A4', type: 'dashed', width: 1 },
      label: { formatter: '昨收', color: '#8892A4', fontSize: 10, position: 'insideEndTop' } },
  ]
  if (s.position?.avg_cost) {
    lines.push({ yAxis: s.position.avg_cost, lineStyle: { color: '#A78BFA', type: 'dashed', width: 1.2 },
      label: { formatter: '成本 ' + s.position.avg_cost, color: '#A78BFA', fontSize: 10, position: 'insideEndBottom' } })
  }
  const sup = s.supports?.[0]
  const res = s.resists?.[0]
  if (sup) lines.push({ yAxis: sup, lineStyle: { color: 'rgba(255,71,87,0.45)', type: 'dotted', width: 1 },
    label: { formatter: '支撑', color: '#FF4757', fontSize: 10, position: 'insideStartBottom' } })
  if (res) lines.push({ yAxis: res, lineStyle: { color: 'rgba(42,232,164,0.45)', type: 'dotted', width: 1 },
    label: { formatter: '压力', color: '#2AE8A4', fontSize: 10, position: 'insideStartTop' } })

  return {
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(15,32,53,0.95)', borderColor: 'rgba(0,212,255,0.2)',
      textStyle: { color: '#E8EDF3', fontSize: 12 },
    },
    legend: { data: ['分时', '均价'], top: 2, textStyle: { color: '#8892A4', fontSize: 11 }, inactiveColor: '#5A6577' },
    grid: [
      { left: 54, right: 16, top: 28, height: '60%' },
      { left: 54, right: 16, top: '76%', height: '16%' },
    ],
    xAxis: [
      { type: 'category', data: times, gridIndex: 0, boundaryGap: false,
        axisLabel: { show: false }, axisLine: { lineStyle: { color: '#2A3A4A' } } },
      { type: 'category', data: times, gridIndex: 1, boundaryGap: false,
        axisLabel: { color: '#8892A4', fontSize: 10, interval: Math.floor(times.length / 6) || 1 },
        axisLine: { lineStyle: { color: '#2A3A4A' } } },
    ],
    yAxis: [
      { gridIndex: 0, scale: true, min: +(ymin - pad).toFixed(2), max: +(ymax + pad).toFixed(2),
        splitLine: { lineStyle: { color: 'rgba(42,58,74,0.5)' } }, axisLabel: { color: '#8892A4', fontSize: 10 } },
      { gridIndex: 1, splitLine: { show: false }, axisLabel: { show: false } },
    ],
    series: [
      {
        name: '分时', type: 'line', data: prices, xAxisIndex: 0, yAxisIndex: 0,
        symbol: 'none', lineStyle: { width: 1.5, color: lineColor },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: lineColor + '33' }, { offset: 1, color: lineColor + '05' },
          ]),
        },
        markArea: areas.length ? { silent: true, data: areas } : undefined,
        markLine: { silent: true, symbol: 'none', data: lines },
      },
      { name: '均价', type: 'line', data: avgs, xAxisIndex: 0, yAxisIndex: 0,
        smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#FFC312' } },
      { name: '量', type: 'bar', data: vols.map((v, i) => ({
          value: v, itemStyle: { color: prices[i] >= prev ? 'rgba(255,71,87,0.5)' : 'rgba(42,232,164,0.5)' },
        })), xAxisIndex: 1, yAxisIndex: 1 },
    ],
  }
}

function render() {
  if (chart) chart.setOption(buildOption(), true)
}

onMounted(() => {
  nextTick(() => {
    if (chartRef.value) {
      chart = echarts.init(chartRef.value)
      render()
      window.addEventListener('resize', resize)
    }
  })
})

function resize() {
  chart?.resize()
}

onUnmounted(() => {
  chart?.dispose()
  window.removeEventListener('resize', resize)
})

watch(() => props.signal, render, { deep: true })
</script>

<style scoped>
.intraday-t-chart {
  width: 100%;
  margin: 4px 0 12px;
}
</style>
