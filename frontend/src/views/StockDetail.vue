<template>
  <div class="page-container stock-detail" :class="{ mobile: isMobile }">
    <StockHeader :info="stockInfo" :code="code" :score="compositeScore" :loading="detailLoading" class="detail-header" @predict="goPredict" />

    <SegmentTabs v-model="tab" :options="tabOptions" block class="detail-tabs" />

    <!-- 主数据加载失败：明确报错 + 重试，不与"暂无数据"混淆 -->
    <EmptyState
      v-if="pageError"
      variant="error"
      title="个股数据加载失败"
      description="无法获取该股票的行情与策略数据，请检查后端服务后重试"
      @retry="loadData"
    />

    <template v-else>
      <!-- 做 T -->
      <TSignalCard v-if="tab === 't'" ref="tCardRef" :signal="tSignal" :code="code" @recalc="onRecalc" />

      <!-- 概览（K线 + 核心指标）/ K线 -->
      <section v-if="overviewVisible || klineVisible" class="content-grid" :class="{ 'overview-only': overviewVisible && !klineVisible }">
        <AppCard v-if="klineVisible" title="K线图">
          <template #actions>
            <SegmentTabs v-model="klinePeriod" :options="periodOptions" small />
            <SegmentTabs v-model="klineAdjust" :options="adjustOptions" small />
          </template>
          <KLineChart :data="klineData" :height="isMobile ? 380 : 480" :loading="loadingKline" />
        </AppCard>

        <div v-if="overviewVisible" class="side-panel">
          <CoreMetricsCard :info="stockInfo" />
          <StrategyScoresCard :scores="strategyScores" :loading="strategiesLoading" />
        </div>
      </section>

      <!-- 预测：涨跌概率 ⇄ 专业预测 -->
      <PredictionCard v-if="tab === 'predict'" ref="predictRef" :prediction="prediction" :code="code" :initial-mode="predictMode" />

      <!-- 财务与估值：季度趋势 + 行业分位 -->
      <FinancialsCard v-if="tab === 'financials'" :data="finData" :loading="finLoading" />

      <!-- F10 -->
      <F10Card v-if="tab === 'f10'" :data="f10Data" :loading="f10Loading" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getStockDetail, getStockKLine, getStockStrategies, getStockF10, getStockPrediction, getStockFinancials, type FinancialsData } from '@/api/stock'
import { getTSignal, type TSignal, type TPositionInput } from '@/api/t'
import { useUserStore } from '@/stores/user'
import { useSettingsStore, type KlineAdjust } from '@/stores/settings'
import { useRefreshable } from '@/composables/useRefreshable'
import { useDevice } from '@/composables/useDevice'
import { useRouteTab } from '@/composables/useRouteTab'
import type { KLineData, PredictionResult } from '@/types'
import type { SegmentOption } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import KLineChart from '@/components/charts/KLineChart.vue'
import StockHeader from '@/components/detail/StockHeader.vue'
import TSignalCard from '@/components/detail/TSignalCard.vue'
import CoreMetricsCard from '@/components/detail/CoreMetricsCard.vue'
import StrategyScoresCard from '@/components/detail/StrategyScoresCard.vue'
import PredictionCard from '@/components/detail/PredictionCard.vue'
import F10Card from '@/components/detail/F10Card.vue'
import FinancialsCard from '@/components/detail/FinancialsCard.vue'

const route = useRoute()
const userStore = useUserStore()
const settings = useSettingsStore()
const { isMobile } = useDevice()

// 桌面与手机统一按 tab 浏览：概览在桌面并排展示 K线 + 核心指标，K线 tab 单独放大。
// ?tab=predict 由旧的 /pro-signal 路由重定向而来。
type Tab = 'overview' | 'kline' | 't' | 'predict' | 'financials' | 'f10'
const tab = useRouteTab<Tab>('overview', ['overview', 'kline', 't', 'predict', 'financials', 'f10'] as const)
const tabOptions: SegmentOption<Tab>[] = [
  { label: '概览', value: 'overview' },
  { label: 'K线', value: 'kline' },
  { label: '做T', value: 't' },
  { label: '预测', value: 'predict' },
  { label: '财务', value: 'financials' },
  { label: 'F10', value: 'f10' },
]
const overviewVisible = computed(() => tab.value === 'overview')
const klineVisible = computed(() => tab.value === 'kline' || (tab.value === 'overview' && !isMobile.value))

const predictMode = computed<'prob' | 'pro'>(() => (tab.value === 'predict' ? 'pro' : 'prob'))
const predictRef = ref<InstanceType<typeof PredictionCard>>()
const tCardRef = ref<InstanceType<typeof TSignalCard>>()
// 做T持仓输入:用户填总持仓/可卖/成本后按 T+1 规则重算精确股数
const tPos = ref<TPositionInput | undefined>()

function goPredict() {
  tab.value = 'predict'
  predictRef.value?.setMode('pro')
}

// keep-alive 缓存本页后，切到别的页面 route.params.code 会变成 undefined；
// 只在本页路由激活时同步代码，离开时保留最后一次的值，子组件 props 不会收到 undefined。
const code = ref(String(route.params.code || ''))
watch(() => route.params.code, (c) => { if (route.name === 'StockDetail' && c) code.value = String(c) })
const stockInfo = ref<any>({})
const klineData = ref<KLineData[]>([])
const klinePeriod = ref<'daily' | 'weekly'>('daily')
const klineAdjust = ref<KlineAdjust>(settings.klineAdjust)
const periodOptions: SegmentOption<'daily' | 'weekly'>[] = [{ label: '日K', value: 'daily' }, { label: '周K', value: 'weekly' }]
const adjustOptions: SegmentOption<KlineAdjust>[] = [
  { label: '前复权', value: 'qfq' }, { label: '后复权', value: 'hfq' }, { label: '不复权', value: 'none' },
]
const compositeScore = ref(0)
const strategyScores = ref<Record<string, number>>({})
const prediction = ref<PredictionResult | null>(null)
const tSignal = ref<TSignal | null>(null)
const pageError = ref(false)
// 加载态：首屏骨架（头部/K线），避免整块空白
const detailLoading = ref(false)
const loadingKline = ref(false)
const strategiesLoading = ref(false)

// F10 state
const f10Data = ref<any>(null)
const f10Loading = ref(false)

// 财务与估值（快接口）：首次切到财务 tab 才加载，切换股票后重取
const finData = ref<FinancialsData | null>(null)
const finLoading = ref(false)
let finLoadedFor = ''

async function loadFinancials() {
  const c = code.value
  if (!c || finLoadedFor === c) return
  finLoadedFor = c
  finData.value = null
  finLoading.value = true
  try {
    finData.value = await getStockFinancials(c)
  } catch {
    finData.value = null
    finLoadedFor = ''   // 失败后允许再次进入 tab 时重试
  } finally {
    finLoading.value = false
  }
}

watch(tab, (t) => { if (t === 'financials') loadFinancials() }, { immediate: true })

let abortCtrl: AbortController | null = null

async function loadData() {
  const c = code.value
  if (!c) return
  abortCtrl?.abort()
  abortCtrl = new AbortController()
  const signal = abortCtrl.signal
  const firstLoad = !stockInfo.value?.code
  detailLoading.value = firstLoad
  loadingKline.value = !klineData.value.length
  strategiesLoading.value = true
  try {
    // 渐进渲染：四个请求各自到达即各自上屏——头部（名称/价格）0.2s 级就绪，
    // 不再被最慢的策略评分（冷缓存可达数十秒）拖住整页骨架。
    const tasks = [
      getStockDetail(c, signal)
        .then(d => { stockInfo.value = d })
        .catch(() => { pageError.value = true })   // 详情失败视为页面级失败，提供重试
        .finally(() => { detailLoading.value = false }),
      getStockKLine(c, klinePeriod.value, 250, signal, klineAdjust.value)
        .then(k => { klineData.value = k })
        .finally(() => { loadingKline.value = false }),
      getStockStrategies(c, signal)
        .then(s => {
          const r = s as any
          compositeScore.value = r.total || 0
          const map: Record<string, number> = {}
          Object.entries(r.strategies || {}).forEach(([k, v]: [string, any]) => { map[k] = v.score || 0 })
          strategyScores.value = map
        })
        .catch(() => { compositeScore.value = 0 })
        .finally(() => { strategiesLoading.value = false }),
      getStockPrediction(c, signal)
        .then(p => { prediction.value = p })
        .catch(() => { prediction.value = null }),
    ]
    await Promise.allSettled(tasks)
  } catch {} 
  // F10 loads in parallel (slower akshare path).
  loadF10()
  loadTSignal(tPos.value)
}

async function loadTSignal(pos?: TPositionInput) {
  const c = code.value
  if (!c) return
  try {
    tSignal.value = await getTSignal(c, pos)
  } catch {
    tSignal.value = null
  }
}

function onRecalc(pos: TPositionInput | undefined) {
  tPos.value = pos
  loadTSignal(pos)
}

async function loadF10() {
  const c = code.value
  if (!c) return
  f10Loading.value = true
  try {
    f10Data.value = await getStockF10(c, abortCtrl?.signal)
  } catch {} finally {
    f10Loading.value = false
  }
}

watch(() => code.value, () => { if (code.value) loadData() })

// Re-fetch only the K-line when the user changes period or adjustment. Debounce
// so rapid clicks (日/周/前/后/不) don't fire three overlapping requests.
let klineTimer: number | undefined
watch([klinePeriod, klineAdjust], () => {
  if (!code.value) return
  if (klineTimer) window.clearTimeout(klineTimer)
  klineTimer = window.setTimeout(() => {
    loadingKline.value = true
    getStockKLine(code.value, klinePeriod.value, 250, abortCtrl?.signal, klineAdjust.value)
      .then(d => (klineData.value = d))
      .catch(() => {})
      .finally(() => { loadingKline.value = false })
  }, 200)
})

useRefreshable('个股详情', loadData)
onMounted(() => {
  // Pull the user's watchlists so the header button reflects "已自选" state
  if (userStore.isLoggedIn) userStore.fetchWatchlists().catch(() => {})
})
onBeforeUnmount(() => abortCtrl?.abort())
</script>

<style scoped>
.stock-detail { display: flex; flex-direction: column; gap: 16px; }
.stock-detail.mobile { gap: 12px; }
.content-grid {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  align-items: start;
}
.side-panel { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.stock-detail.mobile .content-grid { grid-template-columns: 1fr; gap: 12px; }
.stock-detail.mobile .side-panel { gap: 12px; }
.stock-detail.mobile .detail-header {
  position: sticky;
  top: 0;
  z-index: 5;
}
.detail-tabs { flex-shrink: 0; }
.content-grid.overview-only { grid-template-columns: 1fr; }
@media (max-width: 1200px) { .content-grid { grid-template-columns: 1fr; } }
</style>
