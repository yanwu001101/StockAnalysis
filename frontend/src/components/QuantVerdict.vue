/**
 * QuantVerdict — pure presentational.
 *
 * ECharts gauge for the 0-100 score, the plain-language reasons, and a
 * collapsible raw-metrics panel that shows the metric status next to every
 * number so an "uncomputable" value is never mistaken for a real 0.
 */
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts/core'
import { GaugeChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import type { MetricStatusMap, QuantVerdictPayload } from '@/types/quant'

echarts.use([GaugeChart, CanvasRenderer])

const props = defineProps<{
  payload: QuantVerdictPayload
  /** 专业指标模式：只渲染原始指标表，隐藏仪表盘与人话结论 */
  rawOnly?: boolean
}>()

const gaugeEl = ref<HTMLDivElement | null>(null)
const chart = shallowRef<echarts.ECharts | null>(null)

const VERDICT_COLORS: Record<string, string> = {
  'text-green': '#3FB950',
  'text-yellow': '#D29922',
  'text-red': '#F85149',
}

const SIGNAL_LABELS: Record<QuantVerdictPayload['humanVerdict']['signal'], string> = {
  BUY: '买入倾向',
  HOLD: '观望',
  SELL: '卖出倾向',
}

const METRIC_LABELS: Record<keyof QuantVerdictPayload['rawMetrics'], string> = {
  sharpeRatio: '夏普比率',
  maxDrawdown: '最大回撤',
  winRate: '胜率',
  totalReturn: '总收益率',
  alpha: '阿尔法（年化）',
  beta: '贝塔',
}

function formatMetric(key: keyof QuantVerdictPayload['rawMetrics'], value: number): string {
  switch (key) {
    case 'winRate':
      return `${(value * 100).toFixed(1)}%`
    case 'maxDrawdown':
    case 'totalReturn':
    case 'alpha':
      return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
    default:
      return value.toFixed(2)
  }
}

const gaugeOption = computed<EChartsOption>(() => {
  const { score, colorClass, signal } = props.payload.humanVerdict
  const color = VERDICT_COLORS[colorClass] ?? '#D29922'
  return {
    animation: false,
    series: [
      {
        type: 'gauge',
        startAngle: 210,
        endAngle: -30,
        min: 0,
        max: 100,
        radius: '92%',
        center: ['50%', '58%'],
        progress: { show: true, width: 10, itemStyle: { color } },
        axisLine: { lineStyle: { width: 10, color: [[1, '#2A323D']] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        pointer: { show: false },
        anchor: { show: false },
        title: { show: false },
        detail: {
          valueAnimation: false,
          offsetCenter: [0, '-2%'],
          fontSize: 40,
          fontFamily: 'JetBrains Mono, monospace',
          color: '#E6EDF3',
          formatter: '{value}',
        },
        data: [{ value: score, name: signal }],
      },
    ],
  }
})

function render(): void {
  if (chart.value === null && gaugeEl.value !== null) {
    chart.value = echarts.init(gaugeEl.value, undefined, { renderer: 'canvas' })
  }
  chart.value?.setOption(gaugeOption.value)
}

watch(gaugeOption, render, { deep: true })
onMounted(() => {
  render()
  window.addEventListener('resize', render)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', render)
  chart.value?.dispose()
  chart.value = null
})

function statusLabel(status: MetricStatusMap[keyof MetricStatusMap]): string {
  switch (status) {
    case 'VALID':
      return '有效'
    case 'INSUFFICIENT_DATA':
      return '数据不足'
    case 'FAILED':
      return '计算失败'
  }
}
</script>

<template>
  <section class="panel" aria-label="量化结论">
    <div v-if="!rawOnly" class="verdict-head">
      <div ref="gaugeEl" class="gauge" role="img" aria-label="综合评分仪表盘" />
      <div class="verdict-side">
        <div class="signal-row">
          <span class="signal" :class="payload.humanVerdict.colorClass">
            {{ SIGNAL_LABELS[payload.humanVerdict.signal] }}
          </span>
          <span class="symbol num">{{ payload.symbol }}</span>
        </div>
        <ul class="reasons">
          <li v-for="(reason, index) in payload.humanVerdict.reasons" :key="index">
            {{ reason }}
          </li>
        </ul>
      </div>
    </div>

    <details class="raw-metrics">
      <summary>原始指标（专业视图）</summary>
      <table>
        <thead>
          <tr>
            <th>指标</th>
            <th>数值</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(label, key) in METRIC_LABELS" :key="key">
            <td>{{ label }}</td>
            <td class="num">{{ formatMetric(key, payload.rawMetrics[key]) }}</td>
            <td>
              <span
                class="status"
                :class="payload.metricStatus[key] === 'VALID' ? 'ok' : 'warn'"
              >
                {{ statusLabel(payload.metricStatus[key]) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </details>

    <ul v-if="payload.warnings.length > 0" class="warnings" aria-label="数据警告">
      <li v-for="(warning, index) in payload.warnings" :key="index">⚠ {{ warning }}</li>
    </ul>
  </section>
</template>

<style scoped>
.panel {
  background: var(--bg-panel);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-4) var(--space-6);
}

.verdict-head {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: var(--space-6);
  align-items: center;
}

.gauge {
  width: 260px;
  height: 200px;
}

.verdict-side {
  min-width: 0;
}

.signal-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}

.signal {
  font-size: 22px;
  font-weight: 700;
}

.symbol {
  color: var(--text-secondary);
  font-size: 13px;
}

.reasons {
  margin: var(--space-3) 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: var(--space-2);
}

.reasons li {
  font-size: 13px;
  color: var(--text-primary);
  padding-left: var(--space-3);
  border-left: 2px solid var(--border-subtle);
}

.raw-metrics {
  margin-top: var(--space-4);
  border-top: 1px solid var(--border-subtle);
  padding-top: var(--space-3);
}

.raw-metrics summary {
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  user-select: none;
}

.raw-metrics table {
  width: 100%;
  margin-top: var(--space-3);
  border-collapse: collapse;
  font-size: 13px;
}

.raw-metrics th,
.raw-metrics td {
  text-align: left;
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--border-subtle);
}

.raw-metrics th {
  color: var(--text-muted);
  font-weight: 500;
}

.status {
  font-size: 12px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
}

.status.ok {
  color: var(--verdict-green);
  border: 1px solid var(--verdict-green);
}

.status.warn {
  color: var(--verdict-yellow);
  border: 1px solid var(--verdict-yellow);
}

.warnings {
  margin: var(--space-3) 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: var(--space-1);
}

.warnings li {
  font-size: 12px;
  color: var(--verdict-yellow);
}
</style>
