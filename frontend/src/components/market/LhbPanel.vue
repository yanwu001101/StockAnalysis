<template>
  <AppCard :loading="loading && !!rows.length">
    <template #title><SegmentTabs v-model="view" :options="viewOptions" small /></template>
    <template #actions>
      <span class="win-label">近</span>
      <SegmentTabs v-model="windowDays" :options="windowOptions" small />
    </template>

    <StockTable
      v-if="view === 'recent'"
      :rows="recent"
      :columns="recentColumns"
      :loading="loading"
      :error="loadError"
      :empty="loadError ? '龙虎榜数据加载失败，请重试' : '暂无数据'"
      dense
      row-key="code"
      @retry="load"
    >
      <template #cell-seatType="{ row }">
        <span class="tag" :class="seatCls(row.seatType)">{{ row.seatType || '—' }}</span>
      </template>
    </StockTable>

    <StockTable v-else-if="view === 'institution'" :rows="instRank" :columns="instColumns" :loading="loading" :error="loadError" :empty="loadError ? '龙虎榜数据加载失败，请重试' : '暂无数据'" rank @retry="load" />
    <StockTable v-else :rows="stockRank" :columns="stockColumns" :loading="loading" :error="loadError" :empty="loadError ? '龙虎榜数据加载失败，请重试' : '暂无数据'" rank @retry="load" />
  </AppCard>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { getLhbRecent, getLhbInstitutionRank, getLhbStockRank, type LhbRow, type LhbAggRow } from '@/api/lhb'
import { useRefreshable } from '@/composables/useRefreshable'
import type { StockColumn, SegmentOption } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import StockTable from '@/components/stock/StockTable.vue'

type View = 'recent' | 'institution' | 'stock'
const view = ref<View>('recent')
const viewOptions: SegmentOption<View>[] = [
  { label: '明细', value: 'recent' }, { label: '净买榜', value: 'institution' }, { label: '上榜频次', value: 'stock' },
]
const windowDays = ref(30)
const windowOptions: SegmentOption<number>[] = [
  { label: '7天', value: 7 }, { label: '14天', value: 14 }, { label: '30天', value: 30 }, { label: '60天', value: 60 },
]
const recent = ref<LhbRow[]>([])
const instRank = ref<LhbAggRow[]>([])
const stockRank = ref<LhbAggRow[]>([])
const loading = ref(false)
const loadError = ref(false)

const rows = computed<any[]>(() => {
  if (view.value === 'recent') return recent.value
  if (view.value === 'institution') return instRank.value
  return stockRank.value
})

const recentColumns: StockColumn[] = [
  { key: 'tradeDate', label: '日期', mobile: 'secondary' },
  { key: 'reason', label: '上榜原因', mobile: 'secondary' },
  { key: 'seatType', label: '席位类型', align: 'center', mobile: 'secondary' },
  { key: 'seatName', label: '席位', mobile: 'secondary' },
  { key: 'buyAmount', label: '买入额', type: 'amount', colored: false, mobile: 'hidden' },
  { key: 'sellAmount', label: '卖出额', type: 'amount', colored: false, mobile: 'hidden' },
  { key: 'netAmount', label: '净额', type: 'amount', mobile: 'primary' },
]
const instColumns: StockColumn[] = [
  { key: 'appearances', label: '机构上榜次数', type: 'num', digits: 0, align: 'center' },
  { key: 'netSum', label: '累计净买', type: 'amount', mobile: 'primary' },
  { key: 'buySum', label: '累计买入', type: 'amount', colored: false },
  { key: 'lastSeen', label: '最近上榜' },
]
const stockColumns: StockColumn[] = [
  { key: 'appearances', label: '上榜天数', type: 'num', digits: 0, align: 'center' },
  { key: 'netSum', label: '累计净额', type: 'amount', mobile: 'primary' },
  { key: 'reasons', label: '上榜原因' },
  { key: 'lastSeen', label: '最近上榜' },
]

function seatCls(t: string) {
  if (!t) return ''
  if (t.includes('机构')) return 'tag-inst'
  if (t.includes('游资') || t.includes('营业部')) return 'tag-retail'
  return ''
}

async function load() {
  loading.value = true
  try {
    if (view.value === 'recent') {
      recent.value = await getLhbRecent(windowDays.value)
    } else if (view.value === 'institution') {
      instRank.value = await getLhbInstitutionRank(windowDays.value)
    } else {
      stockRank.value = await getLhbStockRank(windowDays.value)
    }
    loadError.value = false
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

watch([windowDays, view], load)
useRefreshable('龙虎榜', load)
</script>

<style scoped>
.win-label { font-size: 12px; color: var(--text-3); }
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  background: var(--surface-2);
  color: var(--text-3);
  white-space: nowrap;
}
.tag-inst { background: var(--brand-soft); color: var(--brand); font-weight: 600; }
.tag-retail { background: var(--warn-soft); color: var(--warn-text); }
</style>
