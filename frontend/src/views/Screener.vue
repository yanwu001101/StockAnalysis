<template>
  <div class="page-container screener-page">
    <PageHeader title="选股" :sub="tabSub">
      <SegmentTabs v-model="tab" :options="tabOptions" />
    </PageHeader>
    <SegmentTabs v-if="isMobile" v-model="tab" :options="tabOptions" class="mobile-tabs" />

    <keep-alive>
      <component :is="tabComponent" :key="tab" />
    </keep-alive>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRouteTab } from '@/composables/useRouteTab'
import { useDevice } from '@/composables/useDevice'
import type { SegmentOption } from '@/types/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import ScoreScreener from '@/components/screener/ScoreScreener.vue'

// 评分 / 条件 / 表达式 / 策略实验室（权重+回测+因子检验）；重的 tab 按需加载。
const ConditionScreener = defineAsyncComponent(() => import('@/components/screener/ConditionScreener.vue'))
const ExpressionScreener = defineAsyncComponent(() => import('@/components/screener/ExpressionScreener.vue'))
const StrategyWeights = defineAsyncComponent(() => import('@/components/screener/StrategyWeights.vue'))
const BacktestPanel = defineAsyncComponent(() => import('@/components/screener/BacktestPanel.vue'))
const FactorLabPanel = defineAsyncComponent(() => import('@/components/screener/FactorLabPanel.vue'))
const FactorMinePanel = defineAsyncComponent(() => import('@/components/screener/FactorMinePanel.vue'))
const PaperPanel = defineAsyncComponent(() => import('@/components/screener/PaperPanel.vue'))

const { isMobile } = useDevice()
const route = useRoute()
const router = useRouter()

// 旧链接 ?tab=lab（及更早的 ?tab=weights/backtest）整体迁往一级「研究」页
const rawTab = Array.isArray(route.query.tab) ? route.query.tab[0] : route.query.tab
if (rawTab === 'lab' || rawTab === 'weights' || rawTab === 'backtest') {
  const { tab: _t, ...rest } = route.query
  const sub = rawTab === 'lab'
    ? (Array.isArray(route.query.sub) ? route.query.sub[0] : route.query.sub) || 'weights'
    : rawTab
  router.replace({ path: '/lab', query: { ...rest, sub } })
}

type Tab = 'score' | 'condition' | 'expression'
const TABS = ['score', 'condition', 'expression'] as const
const tab = useRouteTab<Tab>('score', TABS)

const tabOptions: SegmentOption<Tab>[] = [
  { label: '评分选股', value: 'score' },
  { label: '条件选股', value: 'condition' },
  { label: '表达式', value: 'expression' },
]

const SUBS: Record<Tab, string> = {
  score: '设定财务与技术参数，按综合评分输出候选名单',
  condition: '表单式条件构造器 · 财务/技术/资金多维 AND / OR 组合',
  expression: 'Python-like 表达式 + 安全 AST eval · 支持 MA/MACD/RSI/HHV/CROSS_UP 与基本面字段',
}
const tabSub = computed(() => SUBS[tab.value])

const tabComponent = computed(() => ({
  score: ScoreScreener,
  condition: ConditionScreener,
  expression: ExpressionScreener,
}[tab.value]))
</script>

<style scoped>
.mobile-tabs { margin-bottom: 12px; }
.lab-tabs { margin-bottom: 12px; }
</style>
