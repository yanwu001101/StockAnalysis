<template>
  <AppCard title="市场涨跌榜" compact>
    <template #actions>
      <SegmentTabs v-model="active" :options="options" small />
    </template>
    <RankList :rows="current" :limit="10" />
  </AppCard>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SegmentOption } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import RankList from '@/components/stock/RankList.vue'

const props = defineProps<{ gainers: any[]; losers: any[]; mostActive: any[] }>()

type Kind = 'gainers' | 'losers' | 'active'
const active = ref<Kind>('gainers')
const options: SegmentOption<Kind>[] = [
  { label: '涨幅', value: 'gainers' }, { label: '跌幅', value: 'losers' }, { label: '活跃', value: 'active' },
]
const current = computed(() =>
  active.value === 'gainers' ? props.gainers : active.value === 'losers' ? props.losers : props.mostActive)
</script>
