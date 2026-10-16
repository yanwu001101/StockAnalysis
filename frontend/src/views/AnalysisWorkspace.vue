/**
 * AnalysisWorkspace — /analysis/:symbol 智能分析工作台（系统核心）。
 *
 * 分屏网格：
 *   左列 25%：Agent Progress Panel（实时滚动 AI 思考碎片）+ 当日检视
 *   右上 75%：ECharts K 线（点击某一天 -> 左右面板联动）
 *   右下 75%：Tab —— 小白结论 / 多空辩论回放 / 专业指标
 *
 * 进入路由即用 URL 中的 symbol 发起分析；分析中/完成后各面板有明确状态。
 */
<script setup lang="ts">
defineOptions({ name: 'AnalysisWorkspace' })

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import PanelFrame from '@/components/PanelFrame.vue'
import AgentProgressPanel from '@/components/AgentProgressPanel.vue'
import QuantVerdict from '@/components/QuantVerdict.vue'
import CandleChart from '@/components/CandleChart.vue'
import DayInspector from '@/components/DayInspector.vue'
import DebateReplay from '@/components/DebateReplay.vue'
import { useAnalysisStore } from '@/stores/useAnalysisStore'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import { dayContext } from '@/utils/selectors'

const route = useRoute()
const analysis = useAnalysisStore()
const workspace = useWorkspaceStore()
const { symbol, agentList, verdict, errorMessage, selectedDate, submitting, connectionState } =
  storeToRefs(analysis)

const activeTab = ref<'verdict' | 'debate' | 'raw'>('verdict')

const routeSymbol = computed<string>(() => {
  const raw = String(route.params.symbol ?? '').replace(/\D/g, '')
  return raw.length >= 6 ? raw.padStart(6, '0').slice(-6) : ''
})

const dayCtx = computed(() => dayContext(verdict.value, selectedDate.value ?? ''))

const watched = computed<boolean>(() =>
  routeSymbol.value !== '' && workspace.isWatched(routeSymbol.value),
)

function onSelectDate(date: string): void {
  analysis.setSelectedDate(date)
}

/** 进入路由即发起分析（symbol 变化时重新分析） */
onMounted(() => {
  if (routeSymbol.value !== '') void analysis.submit(routeSymbol.value)
})

watch(routeSymbol, (next) => {
  if (next !== '' && next !== symbol.value) void analysis.submit(next)
})

const statusText = computed<string>(() => {
  if (submitting.value) return '正在提交…'
  if (verdict.value !== null) return '分析完成'
  if (symbol.value !== '') return '分析进行中…'
  return '等待提交'
})
</script>

<template>
  <div class="workspace">
    <!-- 顶部：当前标的与状态 -->
    <div class="ws-head">
      <div class="ws-title">
        <span class="ws-symbol num">{{ routeSymbol || '----' }}</span>
        <span class="ws-status" :class="verdict ? 'done' : 'running'">{{ statusText }}</span>
        <span class="ws-conn" :class="`conn-${connectionState.toLowerCase()}`">
          {{ connectionState }}
        </span>
      </div>
      <div class="ws-actions">
        <button
          class="ws-btn"
          type="button"
          :disabled="routeSymbol === ''"
          @click="workspace.addToWatchlist(routeSymbol)"
        >
          {{ watched ? '✓ 已在自选' : '＋ 加入自选' }}
        </button>
        <button
          class="ws-btn primary"
          type="button"
          :disabled="routeSymbol === '' || submitting"
          @click="analysis.submit(routeSymbol)"
        >
          重新分析
        </button>
      </div>
    </div>

    <div v-if="errorMessage" class="ws-error" role="alert">
      {{ errorMessage }}
      <button type="button" @click="errorMessage = ''">×</button>
    </div>

    <!-- 分屏网格 -->
    <div class="ws-grid">
      <!-- 左列 25% -->
      <div class="ws-left">
        <PanelFrame id="ws-agents" title="AI 智能体进度" :meta="`${agentList.length} 个`">
          <AgentProgressPanel :agents="agentList" bare />
        </PanelFrame>
        <PanelFrame id="ws-day" title="当日检视" :meta="selectedDate ?? ''">
          <DayInspector :context="dayCtx" :verdict="verdict" />
        </PanelFrame>
      </div>

      <!-- 右列 75% -->
      <div class="ws-right">
        <PanelFrame id="ws-chart" title="日 K 线 · 回测信号" :meta="routeSymbol">
          <CandleChart
            v-if="verdict && verdict.candles.length > 0"
            :symbol="routeSymbol"
            :candles="verdict.candles"
            :dates="verdict.dates"
            :markers="verdict.chartMarkers"
            :selected-date="selectedDate"
            @select="onSelectDate"
          />
          <p v-else class="state-loading">K 线数据将在分析完成后渲染（点击任意一天可联动左右面板）。</p>
        </PanelFrame>

        <PanelFrame id="ws-tabs" title="分析结论">
          <template #default>
            <nav class="tabs">
              <button :class="{ active: activeTab === 'verdict' }" type="button" @click="activeTab = 'verdict'">
                小白结论
              </button>
              <button :class="{ active: activeTab === 'debate' }" type="button" @click="activeTab = 'debate'">
                多空辩论回放
              </button>
              <button :class="{ active: activeTab === 'raw' }" type="button" @click="activeTab = 'raw'">
                专业指标
              </button>
            </nav>
            <div class="tab-body">
              <QuantVerdict v-if="activeTab === 'verdict' && verdict" :payload="verdict" />
              <DebateReplay v-else-if="activeTab === 'debate' && verdict" :debate="verdict.debate" />
              <QuantVerdict v-else-if="activeTab === 'raw' && verdict" :payload="verdict" raw-only />
              <p v-else-if="verdict === null" class="state-loading">分析完成后在此展示结论。</p>
              <p v-else class="state-loading">该视图暂无数据。</p>
            </div>
          </template>
        </PanelFrame>
      </div>
    </div>
  </div>
</template>

<style scoped>
.workspace {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  height: 100%;
  min-height: 0;
}

.ws-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex: none;
}

.ws-title {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}

.ws-symbol {
  font-size: 18px;
  font-weight: 700;
}

.ws-status {
  font-size: 11px;
  border-radius: 999px;
  padding: 1px 8px;
  border: 1px solid currentColor;
}

.ws-status.running {
  color: var(--accent);
}

.ws-status.done {
  color: var(--verdict-green);
}

.ws-conn {
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.ws-actions {
  display: flex;
  gap: var(--space-2);
}

.ws-btn {
  background: transparent;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 12px;
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
}

.ws-btn:hover:not(:disabled) {
  color: var(--text-primary);
  border-color: var(--accent);
}

.ws-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ws-btn.primary {
  color: var(--accent);
  border-color: var(--accent);
}

.ws-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(248, 81, 73, 0.08);
  border: 1px solid var(--verdict-red);
  border-radius: var(--radius-sm);
  font-size: 12px;
  padding: var(--space-2) var(--space-3);
  flex: none;
}

.ws-error button {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
}

.ws-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 25% 75%;
  gap: var(--space-3);
}

.ws-left,
.ws-right {
  display: grid;
  gap: var(--space-3);
  min-height: 0;
  min-width: 0;
}

.ws-left {
  grid-template-rows: 1fr 1fr;
}

.ws-right {
  grid-template-rows: 1.4fr 1fr;
}

.tabs {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-subtle);
}

.tabs button {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  font-size: 12px;
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
}

.tabs button.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.tab-body {
  min-height: 0;
}

.state-loading {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
