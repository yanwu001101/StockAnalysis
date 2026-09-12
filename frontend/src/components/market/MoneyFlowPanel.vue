<template>
  <AppCard :loading="loading && !!rows.length">
    <template #actions>
      <template v-if="kind === 'main'">
        <span class="win-label">方向</span>
        <SegmentTabs v-model="direction" :options="directionOptions" small />
      </template>
      <span class="win-label">统计窗口</span>
      <SegmentTabs v-model="windowDays" :options="windowOptions" small />
    </template>
    <StockTable
      :rows="rows" :columns="columns" :loading="loading" rank
      :error="loadError"
      :empty="loadError ? '资金数据加载失败，请重试' : '暂无数据'"
      :clickable="kind !== 'sector'" :stock="kind !== 'sector'"
      @retry="load"
    />
  </AppCard>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { getMainRank, getNorthboundRank, getSectorFlow,
         type MainFlowRow, type NbFlowRow, type SectorRow } from '@/api/moneyflow'
import { useRefreshable } from '@/composables/useRefreshable'
import type { StockColumn, SegmentOption } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import StockTable from '@/components/stock/StockTable.vue'

export type FlowKind = 'main' | 'nb' | 'sector'
export type FlowDirection = 'inflow' | 'outflow'

const props = defineProps<{ kind: FlowKind; initialDirection?: FlowDirection }>()

const direction = ref<FlowDirection>(props.initialDirection ?? 'inflow')
const directionOptions: SegmentOption<FlowDirection>[] = [
  { label: '净流入', value: 'inflow' },
  { label: '净流出', value: 'outflow' },
]

const windowDays = ref(5)
const windowOptions: SegmentOption<number>[] = [
  { label: '3日', value: 3 }, { label: '5日', value: 5 }, { label: '10日', value: 10 }, { label: '20日', value: 20 },
]
const mainRows = ref<MainFlowRow[]>([])
const nbRows = ref<NbFlowRow[]>([])
const sectorRows = ref<SectorRow[]>([])
const loading = ref(false)
const loadError = ref(false)

const rows = computed<any[]>(() => {
  if (props.kind === 'nb') return nbRows.value
  if (props.kind === 'sector') return sectorRows.value
  return mainRows.value
})

const MAIN_COLUMNS: StockColumn[] = [
  { key: 'price', label: '最新价', type: 'price' },
  { key: 'changePercent', label: '涨跌幅', type: 'change' },
  { key: 'mainNetSum', label: '主力净额', type: 'amount' },
  { key: 'superLargeSum', label: '超大单', type: 'amount' },
  { key: 'largeSum', label: '大单', type: 'amount' },
]
const NB_COLUMNS: StockColumn[] = [
  { key: 'price', label: '最新价', type: 'price', by: 'sharesDiff' },
  { key: 'sharesDiff', label: '北向加仓', type: 'num', digits: 1, colored: true, suffix: '万股', format: r => r.sharesDiff / 10000, mobile: 'primary' },
  { key: 'currentShares', label: '当前持股(万股)', type: 'num', digits: 0, format: r => r.currentShares / 10000 },
  { key: 'currentRatio', label: '占比', type: 'percent', digits: 2 },
]
const SECTOR_COLUMNS: StockColumn[] = [
  { key: 'name', label: '板块', mobile: 'title' },
  { key: 'count', label: '家数', type: 'num', digits: 0, align: 'center' },
  { key: 'avgChange', label: '平均涨跌', type: 'change', mobile: 'primary' },
  { key: 'amount', label: '成交额(亿)', type: 'num', digits: 2 },
]
const columns = computed(() => props.kind === 'nb' ? NB_COLUMNS : props.kind === 'sector' ? SECTOR_COLUMNS : MAIN_COLUMNS)

async function load() {
  loading.value = true
  try {
    if (props.kind === 'main') {
      mainRows.value = await getMainRank(windowDays.value, 30, direction.value)
    } else if (props.kind === 'nb') {
      nbRows.value = await getNorthboundRank(windowDays.value, 30)
    } else {
      sectorRows.value = await getSectorFlow()
    }
    loadError.value = false
  } catch {
    // interceptor 已提示；表格内保留重试入口，避免误显示为"暂无数据"
    loadError.value = true
  } finally {
    loading.value = false
  }
}

watch([windowDays, () => props.kind, direction], load)
useRefreshable('资金流向', load)
</script>

<style scoped>
.win-label { font-size: 12px; color: var(--text-3); }
</style>
