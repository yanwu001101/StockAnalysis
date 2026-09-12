<template>
  <div class="page-container screener-page">
    <PageHeader title="选股" :sub="tabSub">
      <SegmentTabs v-model="tab" :options="tabOptions" />
    </PageHeader>
    <SegmentTabs v-if="isMobile" v-model="tab" :options="tabOptions" class="mobile-tabs" />

    <!-- 策略实验室：权重调优 + 回测验证，一条工作流 -->
    <template v-if="tab === 'lab'">
      <SegmentTabs v-model="labTab" :options="labOptions" small class="lab-tabs" />
      <keep-alive>
        <component :is="labComponent" :key="labTab" />
      </keep-alive>
    </template>
    <keep-alive v-else>
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
const PaperPanel = defineAsyncComponent(() => import('@/components/screener/PaperPanel.vue'))

type Tab = 'score' | 'condition' | 'expression' | 'lab'
const TABS = ['score', 'condition', 'expression', 'lab'] as const
const tab = useRouteTab<Tab>('score', TABS)
const { isMobile } = useDevice()
const route = useRoute()
const router = useRouter()

// 旧链接 ?tab=weights / ?tab=backtest 归一到实验室的子 tab
const rawTab = Array.isArray(route.query.tab) ? route.query.tab[0] : route.query.tab
if (rawTab === 'weights' || rawTab === 'backtest') {
  router.replace({ query: { ...route.query, tab: 'lab', sub: rawTab } })
}

type LabTab = 'weights' | 'backtest' | 'factor' | 'paper'
const labTab = useRouteTab<LabTab>('weights', ['weights', 'backtest', 'factor', 'paper'] as const, 'sub')
const labOptions: SegmentOption<LabTab>[] = [
  { label: '策略权重', value: 'weights' },
  { label: '回测', value: 'backtest' },
  { label: '因子检验', value: 'factor' },
  { label: '模拟盘', value: 'paper' },
]
const labComponent = computed(() => ({ weights: StrategyWeights, backtest: BacktestPanel, factor: FactorLabPanel, paper: PaperPanel }[labTab.value]))

const tabOptions: SegmentOption<Tab>[] = [
  { label: '评分选股', value: 'score' },
  { label: '条件选股', value: 'condition' },
  { label: '表达式', value: 'expression' },
  { label: '策略实验室', value: 'lab' },
]

const SUBS: Record<Tab, string> = {
  score: '设定财务与技术参数，按综合评分输出候选名单',
  condition: '表单式条件构造器 · 财务/技术/资金多维 AND / OR 组合',
  expression: 'Python-like 表达式 + 安全 AST eval · 支持 MA/MACD/RSI/HHV/CROSS_UP 与基本面字段',
  lab: '调整策略权重并回测验证，定义你的专属评分口径',
}
const tabSub = computed(() => {
  if (tab.value === 'lab') {
    if (labTab.value === 'backtest') return '基于历史数据验证策略有效性'
    if (labTab.value === 'factor') return 'IC / 分层回测 / 衰减分析 · 检验策略得分的排序能力'
    if (labTab.value === 'paper') return '每日自动按综合评分调仓 · 模拟实盘跟踪'
    return '自定义各策略权重与参数，决定综合评分的口径'
  }
  return SUBS[tab.value]
})

const tabComponent = computed(() => ({
  score: ScoreScreener,
  condition: ConditionScreener,
  expression: ExpressionScreener,
  lab: null,
}[tab.value]))
</script>

<style scoped>
.mobile-tabs { margin-bottom: 12px; }
.lab-tabs { margin-bottom: 12px; }
</style>
