<template>
  <div ref="chartRef" class="intraday-t-chart" :style="{ height: height + 'px' }"></div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import type { TSignal } from '@/api/t'
import { useEcharts, useChartTokens, baseTooltip, hexToRgba } from '@/composables/useEcharts'

const props = withDefaults(defineProps<{ signal: TSignal | null; height?: number }>(), {
  height: 300,
})

const chartRef = ref<HTMLElement>()
const tokens = useChartTokens()

function buildOption(): EChartsOption | null {
  const s = props.signal
  if (!s || !s.trend || !s.trend.length) return null
  const t = tokens.value
  const COST = t.series[2]   // 成本线：与涨跌色区分开的第三色（主题化）
  const trend = s.trend
  const times = trend.map(d => d.t)
  const prices = trend.map(d => d.price)
  const avgs = trend.map(d => d.avg)
  const vols = trend.map(d => d.vol)
  const prev = (s.prev_close ?? prices[0]) as number
  const lineColor = s.price != null && s.price >= prev ? t.up : t.down

  // y 轴范围:纳入价格/均价/昨收/买卖区/支撑压力/成本
  const extra: number[] = [prev]
  if (s.buy_zone) extra.push(s.buy_zone[0], s.buy_zone[1])
  if (s.sell_zone) extra.push(s.sell_zone[0], s.sell_zone[1])
  extra.push(...(s.supports || []), ...(s.resists || []))
  extra.push(...(s.plan?.invalid_levels || []))
  if (s.position?.avg_cost) extra.push(s.position.avg_cost)
  const allv = ([...prices, ...avgs, ...extra]).filter(v => v != null && isFinite(v as number)) as number[]
  const ymin = Math.min(...allv)
  const ymax = Math.max(...allv)
  const pad = (ymax - ymin) * 0.08 || ymax * 0.01

  // 买卖区色带:接回/低吸区红(买)、卖出区绿(A 股习惯),带名称标注
  const areas: any[] = []
  const buyLabel = s.plan?.mode === 'buy_first' ? '低吸区' : '接回区'
  const sellLabel = s.plan?.mode === 'sell_first' ? '卖出区' : '卖出区'
  if (s.buy_zone) areas.push([
    { yAxis: s.buy_zone[0], itemStyle: { color: hexToRgba(t.up, 0.12) },
      label: { formatter: buyLabel, color: t.up, fontSize: 10, position: 'insideBottomRight' } },
    { yAxis: s.buy_zone[1] },
  ])
  if (s.sell_zone) areas.push([
    { yAxis: s.sell_zone[0], itemStyle: { color: hexToRgba(t.down, 0.12) },
      label: { formatter: sellLabel, color: t.down, fontSize: 10, position: 'insideTopRight' } },
    { yAxis: s.sell_zone[1] },
  ])

  // 关键横线:昨收/成本/支撑/压力/计划失效位(带箭头)
  const lines: any[] = [
    { yAxis: prev, lineStyle: { color: t.text3, type: 'dashed', width: 1 },
      label: { formatter: '昨收', color: t.text3, fontSize: 10, position: 'insideEndTop' } },
  ]
  if (s.position?.avg_cost) {
    lines.push({ yAxis: s.position.avg_cost, lineStyle: { color: COST, type: 'dashed', width: 1.2 },
      label: { formatter: '成本 ' + s.position.avg_cost, color: COST, fontSize: 10, position: 'insideEndBottom' } })
  }
  const sup = s.supports?.[0]
  const res = s.resists?.[0]
  if (sup) lines.push({ yAxis: sup, lineStyle: { color: hexToRgba(t.up, 0.45), type: 'dotted', width: 1 },
    label: { formatter: '支撑 ' + sup, color: t.up, fontSize: 10, position: 'insideStartBottom' } })
  if (res) lines.push({ yAxis: res, lineStyle: { color: hexToRgba(t.down, 0.45), type: 'dotted', width: 1 },
    label: { formatter: '压力 ' + res, color: t.down, fontSize: 10, position: 'insideStartTop' } })
  // 计划失效位:突破/跌破即放弃计划——虚线+箭头,一眼可见
  for (const lv of s.plan?.invalid_levels || []) {
    const isUp = lv > (s.price ?? lv)
    lines.push({
      yAxis: lv,
      symbol: ['none', 'arrow'],
      symbolSize: 7,
      lineStyle: { color: t.warn, type: 'dashed', width: 1.4 },
      label: { formatter: `计划失效 ${lv}`, color: t.warn, fontSize: 10, position: isUp ? 'insideEndTop' : 'insideEndBottom' },
    })
  }

  return {
    backgroundColor: 'transparent',
    animation: false,
    textStyle: { fontFamily: t.font },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, ...baseTooltip(t), confine: true },
    legend: { data: ['分时', '均价'], top: 2, textStyle: { color: t.text3, fontSize: 11 }, inactiveColor: t.text4 },
    grid: [
      { left: 54, right: 16, top: 28, height: '60%' },
      { left: 54, right: 16, top: '76%', height: '16%' },
    ],
    xAxis: [
      { type: 'category', data: times, gridIndex: 0, boundaryGap: false,
        axisLabel: { show: false }, axisLine: { lineStyle: { color: t.line } } },
      { type: 'category', data: times, gridIndex: 1, boundaryGap: false,
        axisLabel: { color: t.text3, fontSize: 10, interval: Math.floor(times.length / 6) || 1 },
        axisLine: { lineStyle: { color: t.line } } },
    ],
    yAxis: [
      { gridIndex: 0, scale: true, min: +(ymin - pad).toFixed(2), max: +(ymax + pad).toFixed(2),
        splitLine: { lineStyle: { color: t.line, type: 'dashed' } }, axisLabel: { color: t.text3, fontSize: 10 } },
      { gridIndex: 1, splitLine: { show: false }, axisLabel: { show: false } },
    ],
    series: [
      {
        name: '分时', type: 'line', data: prices, xAxisIndex: 0, yAxisIndex: 0,
        symbol: 'none', lineStyle: { width: 1.5, color: lineColor },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: hexToRgba(lineColor, 0.2) }, { offset: 1, color: hexToRgba(lineColor, 0.02) },
          ]),
        },
        markArea: areas.length ? { silent: true, data: areas } : undefined,
        markLine: { silent: true, symbol: 'none', data: lines },
      },
      { name: '均价', type: 'line', data: avgs, xAxisIndex: 0, yAxisIndex: 0,
        smooth: true, symbol: 'none', lineStyle: { width: 1, color: t.warn } },
      { name: '量', type: 'bar', data: vols.map((v, i) => ({
          value: v, itemStyle: { color: prices[i] >= prev ? hexToRgba(t.up, 0.5) : hexToRgba(t.down, 0.5) },
        })), xAxisIndex: 1, yAxisIndex: 1 },
    ],
  }
}

useEcharts(chartRef, buildOption, () => [props.signal, tokens.value])
</script>

<style scoped>
.intraday-t-chart {
  width: 100%;
  margin: 4px 0 12px;
}
</style>
