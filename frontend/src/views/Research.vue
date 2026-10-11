<template>
  <div class="page-container research-page">
    <PageHeader title="研究" :sub="tabSub">
      <SegmentTabs v-model="labTab" :options="labOptions" />
    </PageHeader>
    <SegmentTabs v-if="isMobile" v-model="labTab" :options="labOptions" class="mobile-tabs" />
    <keep-alive>
      <component :is="labComponent" :key="labTab" />
    </keep-alive>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useRouteTab } from '@/composables/useRouteTab'
import { useDevice } from '@/composables/useDevice'
import type { SegmentOption } from '@/types/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'

// 研究工作台：策略权重 / 回测 / 因子检验 / 因子挖掘 / 模拟盘
// （自选股的「选股」页拆出，研究功能成为一级入口，不再藏两层标签）
const StrategyWeights = defineAsyncComponent(() => import('@/components/screener/StrategyWeights.vue'))
const BacktestPanel = defineAsyncComponent(() => import('@/components/screener/BacktestPanel.vue'))
const FactorLabPanel = defineAsyncComponent(() => import('@/components/screener/FactorLabPanel.vue'))
const FactorMinePanel = defineAsyncComponent(() => import('@/components/screener/FactorMinePanel.vue'))
const PaperPanel = defineAsyncComponent(() => import('@/components/screener/PaperPanel.vue'))

type LabTab = 'weights' | 'backtest' | 'factor' | 'mining' | 'paper'
const labTab = useRouteTab<LabTab>('weights', ['weights', 'backtest', 'factor', 'mining', 'paper'] as const, 'sub')
const { isMobile } = useDevice()

const labOptions: SegmentOption<LabTab>[] = [
  { label: '策略权重', value: 'weights' },
  { label: '回测', value: 'backtest' },
  { label: '因子检验', value: 'factor' },
  { label: '因子挖掘', value: 'mining' },
  { label: '模拟盘', value: 'paper' },
]
const labComponent = computed(() => ({ weights: StrategyWeights, backtest: BacktestPanel, factor: FactorLabPanel, mining: FactorMinePanel, paper: PaperPanel }[labTab.value]))

const tabSub = computed(() => ({
  weights: '调整各策略权重与参数，定义综合评分口径',
  backtest: '基于历史数据验证策略/因子有效性 · 后台计算不阻塞',
  factor: 'IC / 分层回测 / 衰减分析 · 检验策略得分的排序能力',
  mining: '原子因子自动组合 → 快速筛选 → 完整验证 → 因子库',
  paper: '每日自动按综合评分调仓 · 模拟实盘跟踪',
}[labTab.value]))
</script>

<style scoped>
.mobile-tabs { margin-bottom: 12px; }
</style>
