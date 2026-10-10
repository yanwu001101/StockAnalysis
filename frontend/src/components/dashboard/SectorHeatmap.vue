<template>
  <AppCard title="行业热力图" :sub="sub" compact>
    <BaseChart :option="option" :height="height" :loading="loading" placeholder="暂无行业行情数据" />
    <p class="heat-foot">面积={{ sizeLabel }}，颜色=平均涨跌幅（红涨绿跌，色越深变动越大）。</p>
  </AppCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useChartTokens, baseTooltip } from '@/composables/useEcharts'
import AppCard from '@/components/ui/AppCard.vue'
import BaseChart from '@/components/charts/BaseChart.vue'
import type { SectorData } from '@/types'

const props = withDefaults(defineProps<{ sectors: SectorData[]; loading?: boolean; height?: number }>(),
  { loading: false, height: 300 })

const tokens = useChartTokens()

const rows = computed(() => (props.sectors || []).filter(s => s && s.name && Number.isFinite(s.change)))
const hasAmount = computed(() => rows.value.some(s => (s.amountYi ?? 0) > 0))
const sizeLabel = computed(() => hasAmount.value ? '行业成交额' : '行业成分股数（成交额暂不可用）')

const sub = computed(() => rows.value.length
  ? `${rows.value.length} 个行业 · 涨 ${rows.value.filter(s => s.change > 0).length} / 跌 ${rows.value.filter(s => s.change < 0).length}`
  : '面积=成交额，颜色=涨跌幅')

// 涨跌幅 → 红(涨)/绿(跌) 强度分档。A 股口径红涨绿跌；档位用离散色而非连续渐变，
// 便于肉眼比较相邻板块强弱。
function tone(change: number, up: string, down: string) {
  const a = Math.abs(change)
  const alpha = a >= 4 ? 1 : a >= 2 ? 0.82 : a >= 1 ? 0.62 : a >= 0.3 ? 0.42 : 0.26
  const base = change >= 0 ? up : down
  return hexAlpha(base, alpha)
}

function hexAlpha(hex: string, alpha: number) {
  const h = hex.replace('#', '')
  if (h.length !== 6) return hex
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16)
  // 与卡片底色混合，模拟低饱和填充，避免小格过艳
  const bg = [248, 249, 251]
  const mix = (c: number, i: number) => Math.round(c * alpha + bg[i] * (1 - alpha))
  return `rgb(${mix(r, 0)},${mix(g, 1)},${mix(b, 2)})`
}

const option = computed<EChartsOption | null>(() => {
  if (!rows.value.length) return null
  const t = tokens.value
  const data = rows.value.map(s => ({
    name: s.name,
    value: hasAmount.value ? Math.max(s.amountYi ?? 0, 0.1) : Math.max(s.count ?? 1, 1),
    itemStyle: { color: tone(s.change, t.up, t.down) },
    _s: s,
  }))
  return {
    backgroundColor: 'transparent',
    tooltip: {
      ...baseTooltip(t),
      formatter: (p: any) => {
        const s: SectorData = p.data?._s
        if (!s) return ''
        const parts = [
          `<b>${s.name}</b>`,
          `平均涨跌 <span style="color:${s.change >= 0 ? t.up : t.down}">${s.change > 0 ? '+' : ''}${s.change.toFixed(2)}%</span>`,
          `成分 ${s.count ?? '—'} 只 · 成交 ${s.amountYi == null ? '—' : s.amountYi.toFixed(1) + ' 亿'}`,
          s.leader ? `领涨 ${s.leader} <span style="color:${t.up}">+${(s.leaderChange ?? 0).toFixed(2)}%</span>` : '',
        ].filter(Boolean)
        return parts.join('<br/>')
      },
    },
    series: [{
      type: 'treemap',
      roam: false,
      nodeClick: false,
      breadcrumb: { show: false },
      levels: [{
        itemStyle: { borderRadius: 3, gapWidth: 2, borderColor: t.surface, borderWidth: 1 },
      }],
      label: {
        show: true, formatter: '{b}', fontSize: 11, color: t.text, overflow: 'truncate',
      },
      emphasis: { label: { fontWeight: 600 } },
      squareRatio: 0.72,
      data,
    }],
    animation: false,
  }
})
</script>

<style scoped>
.heat-foot { margin: 4px 0 0; font-size: 11px; line-height: 1.5; color: var(--text-4); }
</style>
