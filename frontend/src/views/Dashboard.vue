<template>
  <div class="page-container dashboard">
    <PageHeader title="今日盘面" sub="综合评分、北向资金与板块轮动一览" />

    <IndexStrip :indices="indices" />

    <StatGrid :items="summaryCards" :cols="isMobile ? 2 : 4" variant="card" :size="isMobile ? 'md' : 'lg'" :loading="marketStore.loading" class="stats" />

    <section class="main-grid">
      <AppCard title="高分股票" sub="综合评分排名前列">
        <template #actions>
          <el-button link size="small" @click="$router.push('/screener')">查看全部 →</el-button>
        </template>
        <StockTable
          :rows="topStocks"
          :columns="topColumns"
          rank
          default-sort="compositeScore"
          :loading="marketStore.loading"
          :error="loadError"
          :empty="loadError ? '无法连接后端服务，请检查网络后重试' : '暂无高分股票 · 等待评分任务完成'"
          @retry="loadAll"
        >
          <template #cell-compositeScoreV2="{ row }">
            <ScorePill v-if="row.compositeScoreV2 !== undefined" :score="row.compositeScoreV2" />
            <span v-else class="dim-load">···</span>
          </template>
          <template #cell-strategyStats="{ row }">
            <StrategyStatsPill :stats="row.strategyStats" />
          </template>
        </StockTable>
      </AppCard>

      <aside class="side-stack">
        <MarketRankCard :gainers="marketStore.gainers" :losers="marketStore.losers" :most-active="marketStore.mostActive" :loading="marketStore.loading" />
        <SectorChart :sectors="marketStore.sectors" :loading="marketStore.loading" />
        <!-- 北向 2024-08 起无每日净买入披露，常为替代口径的陈旧数据 → 移至最后 -->
        <NorthboundChart :data="marketStore.northboundFlow" :loading="marketStore.loading" />
      </aside>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useMarketStore } from '@/stores/market'
import { useRefreshable } from '@/composables/useRefreshable'
import { useDevice } from '@/composables/useDevice'
import { getStockStrategies } from '@/api/stock'
import type { StockColumn, StatItem } from '@/types/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppCard from '@/components/ui/AppCard.vue'
import StatGrid from '@/components/ui/StatGrid.vue'
import StockTable from '@/components/stock/StockTable.vue'
import ScorePill from '@/components/stock/ScorePill.vue'
import StrategyStatsPill from '@/components/stock/StrategyStatsPill.vue'
import IndexStrip from '@/components/dashboard/IndexStrip.vue'
import MarketRankCard from '@/components/dashboard/MarketRankCard.vue'
import NorthboundChart from '@/components/dashboard/NorthboundChart.vue'
import SectorChart from '@/components/dashboard/SectorChart.vue'

const marketStore = useMarketStore()
const { isMobile } = useDevice()

const topStocks = computed(() => marketStore.topStocks || [])
const indices = computed(() => marketStore.indices || [])
const loadError = ref(false)
async function loadAll() {
  try {
    await marketStore.fetchAll()
    loadError.value = false
  } catch {
    // interceptor 已提示；页面内用错误空态替代"暂无数据"，避免误导
    loadError.value = true
  }
}

const topColumns: StockColumn[] = [
  { key: 'price', label: '最新价', type: 'price' },
  { key: 'changePercent', label: '涨跌幅', type: 'change' },
  { key: 'compositeScore', label: '评分', type: 'score', align: 'center', sortable: true },
  { key: 'compositeScoreV2', label: '综合策略分', type: 'score', align: 'center', sortable: true, tooltip: '22 个策略加权综合分（v2）' },
  { key: 'strategyStats', label: '策略评分', align: 'center', tooltip: '看多策略数 / 有效策略数 · 触发数', mobile: 'secondary' },
  { key: 'signal', label: '信号', type: 'signal', align: 'center' },
]

// 高分股票表格里的 v2 综合分与策略统计按需补拉，6 路并发。
async function preloadStrategyDetails() {
  const concurrency = 6
  const list = topStocks.value
  let idx = 0
  const worker = async () => {
    while (idx < list.length) {
      const i = idx++
      const row: any = list[i]
      if (row.compositeScoreV2 !== undefined) continue
      try {
        const d: any = await getStockStrategies(row.code)
        row.compositeScoreV2 = Math.round(d.total ?? d.composite_score ?? 0)
        row.strategyStats = d.aggregate || null
      } catch {
        row.strategyStats = null
      }
    }
  }
  await Promise.all(Array(concurrency).fill(0).map(() => worker()))
}

watch(() => marketStore.topStocks, (v) => {
  if (v?.length) preloadStrategyDetails()
}, { immediate: true })

const summaryCards = computed<StatItem[]>(() => {
  const s: any = marketStore.summary
  return [
    { label: '上涨家数', foot: `下跌 ${s?.downCount ?? '—'}`, value: s?.upCount ?? '—', cls: 'price-up' },
    { label: '涨停家数', foot: `跌停 ${s?.downLimit ?? '—'}`, value: s?.upLimit ?? '—', cls: 'price-up' },
    { label: '平均涨跌', foot: '全市场算术平均',
      value: s ? ((s.avgChange >= 0 ? '+' : '') + s.avgChange + '%') : '—',
      cls: s && s.avgChange >= 0 ? 'price-up' : 'price-down' },
    { label: '领涨板块', foot: '日涨幅第一', value: s?.hotSectors?.[0]?.name ?? '—' },
  ]
})

useRefreshable('今日盘面', loadAll)
</script>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 16px; }
.dashboard > :deep(.page-header) { margin-bottom: 0; }
.main-grid {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 16px;
  align-items: start;
}
.side-stack { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.dim-load { color: var(--text-4); font-size: 13px; letter-spacing: 1px; }
@media (max-width: 1100px) {
  .main-grid { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .dashboard { gap: 12px; }
  .main-grid, .side-stack { gap: 12px; }
}
</style>
