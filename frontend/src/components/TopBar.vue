/**
 * TopBar — 全局搜索 + AI 信息流滚动条 + 系统状态。
 *
 * 搜索框接受 6 位代码或交易所前缀代码，回车直接进入分析工作台并发起分析。
 * 信息流循环滚动最近异动；系统状态展示数据源与智能体健康度。
 */
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import { useAnalysisStore } from '@/stores/useAnalysisStore'

const router = useRouter()
const workspace = useWorkspaceStore()
const analysis = useAnalysisStore()
const { stats, overview, tickerItems } = storeToRefs(workspace)

const query = ref<string>('')

function normalize(input: string): string | null {
  const digits = input.replace(/\D/g, '')
  if (digits.length < 6) return null
  return digits.padStart(6, '0').slice(-6)
}

async function onSearch(): Promise<void> {
  const symbol = normalize(query.value)
  if (symbol === null) return
  await router.push(`/analysis/${symbol}`)
  await analysis.submit(symbol)
  query.value = ''
}

function healthLabel(): string {
  if (stats.value === null) return 'Agent 状态未知'
  if (stats.value.running > 0) return `Agent 忙碌 · ${stats.value.running} 个任务进行中`
  return 'Agent 空闲'
}
</script>

<template>
  <header class="topbar">
    <form class="search" @submit.prevent="onSearch">
      <svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" class="search-icon">
        <circle cx="9" cy="9" r="5.5" />
        <path d="M13.5 13.5L17 17" />
      </svg>
      <input
        v-model="query"
        type="text"
        placeholder="全局搜索：股票代码 / 名称（回车分析）"
        aria-label="全局搜索"
        autocomplete="off"
      />
      <kbd>↵</kbd>
    </form>

    <div v-if="tickerItems.length > 0" class="ticker" aria-label="AI 信息流">
      <div class="ticker-track">
        <span v-for="(item, index) in tickerItems" :key="`a-${index}`" class="ticker-item">{{ item }}</span>
        <span v-for="(item, index) in tickerItems" :key="`b-${index}`" class="ticker-item" aria-hidden="true">{{ item }}</span>
      </div>
    </div>
    <div v-else class="ticker ticker-idle">
      <span class="ticker-item">AI 信息流待命 —— 提交分析后异动将在此滚动</span>
    </div>

    <div class="status" :title="healthLabel()">
      <span class="status-chip">
        <i class="dot" :class="stats && stats.running > 0 ? 'busy' : 'idle'" />
        {{ healthLabel() }}
      </span>
      <span v-if="overview" class="status-chip num">
        基准 {{ overview.benchmarkName }}
        <span v-if="overview.changePct !== null" :class="overview.changePct > 0 ? 'up' : overview.changePct < 0 ? 'down' : 'flat'">
          {{ overview.changePct > 0 ? '+' : '' }}{{ (overview.changePct * 100).toFixed(2) }}%
        </span>
        <span v-else class="flat">--</span>
      </span>
      <span class="status-chip">AkShare</span>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  height: var(--topbar-height);
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-3);
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border-subtle);
}

.search {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 300px;
  flex: none;
  background: var(--bg-app);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 0 var(--space-2);
  height: 28px;
}

.search:focus-within {
  border-color: var(--accent);
}

.search-icon {
  color: var(--text-muted);
  flex: none;
}

.search input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 12px;
}

.search input::placeholder {
  color: var(--text-muted);
}

.search kbd {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  border: 1px solid var(--border-subtle);
  border-radius: 3px;
  padding: 0 4px;
}

.ticker {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  position: relative;
  height: 100%;
  display: flex;
  align-items: center;
  mask-image: linear-gradient(90deg, transparent, #000 24px, #000 calc(100% - 24px), transparent);
}

.ticker-track {
  display: flex;
  gap: var(--space-6);
  white-space: nowrap;
  animation: ticker-scroll 40s linear infinite;
}

.ticker:hover .ticker-track {
  animation-play-state: paused;
}

.ticker-item {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.ticker-idle .ticker-item {
  color: var(--text-muted);
}

.status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex: none;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: 11px;
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  padding: 1px 8px;
  white-space: nowrap;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.dot.idle {
  background: var(--verdict-green);
}

.dot.busy {
  background: var(--accent);
  animation: breathe 1.4s ease-in-out infinite;
}
</style>
