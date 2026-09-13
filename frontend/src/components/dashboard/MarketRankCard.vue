<template>
  <AppCard title="市场涨跌榜" compact>
    <template #actions>
      <SegmentTabs v-model="active" :options="options" small />
    </template>
    <div v-if="loading" class="rank-loading">
      <div v-for="i in 8" :key="i" class="rank-sk">
        <span class="skeleton-bar" style="width: 18px;"></span>
        <span class="skeleton-bar" style="flex: 1;"></span>
        <span class="skeleton-bar" style="width: 56px;"></span>
      </div>
    </div>
    <RankList v-else :rows="current" :limit="10" />
  </AppCard>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SegmentOption } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import RankList from '@/components/stock/RankList.vue'

const props = withDefaults(defineProps<{ gainers: any[]; losers: any[]; mostActive: any[]; loading?: boolean }>(), { loading: false })

type Kind = 'gainers' | 'losers' | 'active'
const active = ref<Kind>('gainers')
const options: SegmentOption<Kind>[] = [
  { label: '涨幅', value: 'gainers' }, { label: '跌幅', value: 'losers' }, { label: '活跃', value: 'active' },
]
const current = computed(() =>
  active.value === 'gainers' ? props.gainers : active.value === 'losers' ? props.losers : props.mostActive)
</script>

<style scoped>
.rank-loading { display: flex; flex-direction: column; gap: 12px; padding: 6px 0; }
.rank-sk { display: flex; gap: 10px; align-items: center; }
</style>

