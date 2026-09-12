<template>
  <AppCard title="核心指标">
    <StatGrid :items="items" :cols="2" variant="inline" size="sm" />
  </AppCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { StatItem } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import StatGrid from '@/components/ui/StatGrid.vue'

const props = defineProps<{ info: any }>()

const pct = (v: any) => (v == null ? '--' : `${v}%`)
const items = computed<StatItem[]>(() => {
  const s = props.info || {}
  return [
    { label: 'ROE', value: pct(s.roe) },
    { label: '负债率', value: pct(s.debtRatio) },
    { label: '现金流', value: s.cashFlowPerShare ?? '--' },
    { label: '营收增长', value: pct(s.revenueGrowth) },
    { label: '净利润增长', value: pct(s.profitGrowth) },
    { label: '毛利率', value: pct(s.grossMargin) },
    { label: 'PE', value: s.pe ?? '--' },
    { label: 'PB', value: s.pb ?? '--' },
  ]
})
</script>
