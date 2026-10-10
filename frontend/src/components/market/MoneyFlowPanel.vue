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
    <div v-if="staleNote" class="stale-note">{{ staleNote }}</div>
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

// 北向逐日披露 2024-08 起停,后端会退回最后可得窗口并标 stale。
// 不写出来会被读成「近 N 日加仓榜」,属过期数据伪装。
const staleNote = computed(() => {
  if (props.kind === 'nb') {
    const first = nbRows.value[0]
    if (!first?.stale) return ''
    const to = String(first.lastDate || '').slice(0, 10)
    return `交易所已停止北向逐日披露,下表为最后可得窗口 ${to ? `（截至 ${to}）` : ''},非近期数据`
  }
  if (props.kind === 'main') {
    const first = mainRows.value[0]
    if (first?.stale) {
      const to = String(first.asOf || '').slice(0, 10)
      return `资金流数据落后于最近交易日${to ? `（截至 ${to}）` : ''},当日盘后更新前请勿当作最新依据`
    }
    const thin = mainRows.value.filter(r => r.days < windowDays.value).length
    if (mainRows.value.length && thin === mainRows.value.length) {
      return `窗口设为 ${windowDays.value} 日,但当前个股资金流仅覆盖 ${mainRows.value[0].days} 天(历史回补中)`
    }
  }
  return ''
})

const MAIN_COLUMNS: StockColumn[] = [
  { key: 'price', label: '最新价', type: 'price' },
  { key: 'changePercent', label: '涨跌幅', type: 'change' },
  { key: 'mainNetSum', label: '主力净额', type: 'amount', tooltip: '窗口内累计净流入 = 超大单 + 大单(净额口径,单位随全局设置)' },
  { key: 'superLargeSum', label: '超大单', type: 'amount' },
  { key: 'largeSum', label: '大单', type: 'amount' },
  { key: 'days', label: '覆盖', type: 'num', digits: 0, align: 'center',
    tooltip: '窗口内有资金流数据的天数——少于窗口天数说明该股历史不全,累计值偏小',
    format: (r: MainFlowRow) => `${r.days}/${windowDays.value}`, mobile: 'hidden' },
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
.stale-note {
  font-size: 12px;
  line-height: 1.6;
  color: var(--warn-text);
  background: var(--warn-soft);
  border-radius: var(--radius);
  padding: 8px 12px;
  margin-bottom: 8px;
}
</style>
