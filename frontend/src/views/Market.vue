<template>
  <div class="page-container market-page">
    <PageHeader title="资金" :sub="tabSub">
      <SegmentTabs v-model="tab" :options="tabOptions" />
    </PageHeader>
    <SegmentTabs v-if="isMobile" v-model="tab" :options="tabOptions" class="mobile-tabs" />

    <keep-alive>
      <LhbPanel v-if="tab === 'lhb'" key="lhb" />
      <MoneyFlowPanel v-else key="flow" :kind="flowKind" :initial-direction="initialDirection" />
    </keep-alive>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useRouteTab } from '@/composables/useRouteTab'
import { useDevice } from '@/composables/useDevice'
import type { SegmentOption } from '@/types/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import MoneyFlowPanel from '@/components/market/MoneyFlowPanel.vue'
import LhbPanel from '@/components/market/LhbPanel.vue'

// 资金流向 + 龙虎榜合并：同一页面切换，四类资金榜共用一个面板实例。
// 主力净流入/净流出合并为一个 tab，方向在面板内切换。
type Tab = 'main' | 'nb' | 'sector' | 'lhb'
const TABS = ['main', 'nb', 'sector', 'lhb'] as const
const tab = useRouteTab<Tab>('main', TABS)
const { isMobile } = useDevice()
const route = useRoute()

// 旧链接 ?tab=main-in / main-out 归一到 main + 面板内方向
const initialDirection = route.query.tab === 'main-out' ? 'outflow' : 'inflow'
const flowKind = computed(() => (tab.value === 'lhb' ? 'main' : tab.value))

const tabOptions: SegmentOption<Tab>[] = [
  { label: '主力资金', value: 'main' },
  { label: '北向加仓', value: 'nb' },
  { label: '板块资金', value: 'sector' },
  { label: '龙虎榜', value: 'lhb' },
]

const SUBS: Record<Tab, string> = {
  main: '主力资金净流入 / 流出排行 · 超大单与大单拆分',
  nb: '北向资金加仓股数与持股占比',
  sector: '板块资金与平均涨跌',
  lhb: '机构席位 / 游资 / 上榜原因 · 数据来源东方财富',
}
const tabSub = computed(() => SUBS[tab.value])
</script>

<style scoped>
.mobile-tabs { margin-bottom: 12px; }
</style>
