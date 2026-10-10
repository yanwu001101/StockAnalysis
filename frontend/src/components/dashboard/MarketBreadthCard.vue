<template>
  <AppCard title="市场宽度" :sub="sub" compact>
    <div class="breadth-stats">
      <div class="bs-item">
        <span class="bs-k">涨停 / 触板</span>
        <b class="num bs-up">{{ b.limitUp }}<span class="bs-dim"> / {{ b.touchedUp }}</span></b>
      </div>
      <div class="bs-item">
        <span class="bs-k">炸板率</span>
        <b class="num" :class="brokenTone">{{ b.brokenRate == null ? '—' : b.brokenRate.toFixed(1) + '%' }}</b>
      </div>
      <div class="bs-item">
        <span class="bs-k">跌停 / 打开</span>
        <b class="num bs-down">{{ b.limitDown }}<span class="bs-dim"> / {{ b.brokenDown }}</span></b>
      </div>
      <div class="bs-item">
        <span class="bs-k">涨超5% / 跌超5%</span>
        <b class="num">{{ b.upOver5 }}<span class="bs-dim"> / </span><span class="bs-down">{{ b.downOver5 }}</span></b>
      </div>
      <div class="bs-item">
        <span class="bs-k">两市成交</span>
        <b class="num">{{ b.totalAmountYi == null ? '—' : fmtAmt(b.totalAmountYi) }}</b>
      </div>
      <div class="bs-item">
        <span class="bs-k">前5%资金集中度</span>
        <b class="num">{{ b.top5pctAmountShare == null ? '—' : b.top5pctAmountShare.toFixed(1) + '%' }}</b>
      </div>
    </div>
    <BaseChart :option="option" :height="height" :loading="loading" placeholder="暂无涨跌分布数据" />
    <p class="breadth-foot">{{ foot }}</p>
  </AppCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useChartTokens, baseTooltip } from '@/composables/useEcharts'
import AppCard from '@/components/ui/AppCard.vue'
import BaseChart from '@/components/charts/BaseChart.vue'
import type { MarketBreadth } from '@/types'

const props = withDefaults(defineProps<{ breadth?: MarketBreadth | null; loading?: boolean; height?: number }>(),
  { breadth: null, loading: false, height: 190 })

const tokens = useChartTokens()
const EMPTY: MarketBreadth = {
  sampled: 0, excluded: 0, up: 0, down: 0, flat: 0, limitUp: 0, limitDown: 0,
  touchedUp: 0, touchedDown: 0, brokenUp: 0, brokenDown: 0,
  brokenRate: null, brokenRateDown: null, upOver5: 0, downOver5: 0,
  medianChange: null, totalAmountYi: null, top5pctAmountShare: null, histogram: [],
}
const b = computed(() => props.breadth || EMPTY)

const brokenTone = computed(() => {
  const r = b.value.brokenRate
  if (r == null) return ''
  return r >= 35 ? 'bs-down' : r >= 20 ? 'bs-warn' : 'bs-up'
})

function fmtAmt(yi: number) {
  return yi >= 10000 ? (yi / 10000).toFixed(2) + '万亿' : Math.round(yi).toLocaleString() + '亿'
}

const sub = computed(() => b.value.medianChange == null
  ? '涨跌分布 · 涨停梯队 · 资金集中度'
  : `涨跌中位 ${b.value.medianChange > 0 ? '+' : ''}${b.value.medianChange.toFixed(2)}% · 涨停梯队与资金集中度`)

const foot = computed(() => b.value.sampled
  ? `样本 ${b.value.sampled.toLocaleString()} 只当日有成交个股;${b.value.excluded ? `已剔除 ${b.value.excluded} 只停牌/无成交` : '无停牌剔除'}。炸板率=触板未封住/触板。`
  : '宽度指标需要全市场行情快照,当前不可用。')

const option = computed<EChartsOption | null>(() => {
  const bins = b.value.histogram || []
  if (!bins.length) return null
  const t = tokens.value
  // 分箱标签左负右正,颜色按该箱涨跌中枢取红绿
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: t.font, color: t.text3 },
    grid: { left: 36, right: 10, top: 10, bottom: 30 },
    xAxis: {
      type: 'category', data: bins.map(x => x.label),
      axisLabel: { color: t.text4, fontSize: 9, rotate: 40, interval: 0 },
      axisLine: { lineStyle: { color: t.line } }, axisTick: { show: false },
    },
    yAxis: {
      type: 'value', name: '家数', nameTextStyle: { color: t.text4, fontSize: 10 },
      splitLine: { lineStyle: { color: t.line, type: 'dashed' } },
      axisLabel: { color: t.text3, fontSize: 10 }, axisLine: { show: false }, axisTick: { show: false },
    },
    series: [{
      type: 'bar', data: bins.map(x => ({
        value: x.count,
        itemStyle: { color: binColor(x.label, t.up, t.down), borderRadius: [2, 2, 0, 0] },
      })), barWidth: '72%',
    }],
    tooltip: { trigger: 'axis', ...baseTooltip(t), valueFormatter: (v: any) => `${v} 只` },
    animation: false,
  }
})

function binColor(label: string, up: string, down: string) {
  const nums = label.match(/-?\d+/g)?.map(Number) || []
  const mid = nums.length >= 2 ? (nums[0] + nums[1]) / 2 : (nums[0] ?? 0)
  return mid > 0 ? up : mid < 0 ? down : '#9AA2AB'
}
</script>

<style scoped>
.breadth-stats {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px 12px;
  margin-bottom: 6px;
}
.bs-item { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.bs-k { font-size: 11px; color: var(--text-4); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bs-item b { font-size: 15px; font-weight: 650; }
.bs-dim { color: var(--text-4); font-weight: 400; font-size: 12px; }
.bs-up { color: var(--up); }
.bs-down { color: var(--down); }
.bs-warn { color: var(--warn-text); }
.breadth-foot { margin: 4px 0 0; font-size: 11px; line-height: 1.5; color: var(--text-4); }
@media (max-width: 768px) { .breadth-stats { grid-template-columns: repeat(2, 1fr); } }
</style>
