<template>
  <div class="page-container my-page">
    <PageHeader title="自选" :sub="tabSub">
      <SegmentTabs v-model="tab" :options="tabOptions" />
    </PageHeader>
    <SegmentTabs v-if="isMobile" v-model="tab" :options="tabOptions" block class="mobile-tabs" />

    <keep-alive>
      <WatchlistPanel v-if="tab === 'watchlist'" key="watchlist" />
      <PortfolioPanel v-else-if="tab === 'portfolio'" key="portfolio" />
      <AiChatPanel v-else key="ai" />
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
import WatchlistPanel from '@/components/my/WatchlistPanel.vue'

const PortfolioPanel = defineAsyncComponent(() => import('@/components/my/PortfolioPanel.vue'))
const AiChatPanel = defineAsyncComponent(() => import('@/components/my/AiChatPanel.vue'))

type Tab = 'watchlist' | 'portfolio' | 'ai'
const tab = useRouteTab<Tab>('watchlist', ['watchlist', 'portfolio', 'ai'] as const)
const tabSub = computed(() => ({
  watchlist: '关注的股票分组管理，附日内做 T 提示',
  portfolio: '持仓录入、规则体检与 AI 增强分析',
  ai: '和专业金融顾问对话：行情看法、持仓思路、风控与配置建议（语音/文字）',
}[tab.value]))
const { isMobile } = useDevice()

const tabOptions: SegmentOption<Tab>[] = [
  { label: '自选股', value: 'watchlist' },
  { label: '持仓助手', value: 'portfolio' },
  { label: 'AI 顾问', value: 'ai' },
]
</script>

<style scoped>
.mobile-tabs { margin-bottom: 12px; }
</style>
