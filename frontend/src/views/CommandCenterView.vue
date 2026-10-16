/**
 * CommandCenterView — /command-center 驾驶舱。
 *
 * 三列工作区：左侧宏观数据卡片（基准指数 + 涨跌家数），中部 AI 智能体
 * 状态面板（任务数/成功率），右侧 AI 预警抽屉（异动股票列表，点击直达分析）。
 */
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import PanelFrame from '@/components/PanelFrame.vue'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import { useAnalysisStore } from '@/stores/useAnalysisStore'

const router = useRouter()
const workspace = useWorkspaceStore()
const analysis = useAnalysisStore()
const { stats, overview, alerts, statsError, overviewError } = storeToRefs(workspace)

const successRatePct = computed<string>(() =>
  stats.value === null ? '—' : `${(stats.value.successRate * 100).toFixed(1)}%`,
)

const breadthRatio = computed<string>(() => {
  if (overview.value === null || !overview.value.breadthAvailable) return '—'
  const up = overview.value.advancing ?? 0
  const down = overview.value.declining ?? 0
  const total = up + down
  if (total === 0) return '—'
  return `${((up / total) * 100).toFixed(1)}%`
})

async function openAnalysis(symbol: string): Promise<void> {
  await router.push(`/analysis/${symbol}`)
  await analysis.submit(symbol)
}

function severityClass(severity: 'info' | 'warning' | 'critical'): string {
  if (severity === 'critical') return 'text-red'
  if (severity === 'warning') return 'text-yellow'
  return 'flat'
}

function severityLabel(severity: 'info' | 'warning' | 'critical'): string {
  if (severity === 'critical') return '强烈'
  if (severity === 'warning') return '注意'
  return '提示'
}
</script>

<template>
  <div class="cockpit">
    <!-- 左列：宏观数据 -->
    <div class="col col-left">
      <PanelFrame id="cockpit-macro" title="宏观数据" :meta="overview?.benchmarkName ?? ''">
        <div v-if="overview" class="macro-grid">
          <div class="macro-card">
            <span class="macro-label">基准指数</span>
            <span class="macro-value num">{{ overview.lastClose?.toFixed(2) ?? '—' }}</span>
            <span
              v-if="overview.changePct !== null"
              class="macro-delta num"
              :class="overview.changePct > 0 ? 'up' : overview.changePct < 0 ? 'down' : 'flat'"
            >
              {{ overview.changePct > 0 ? '+' : '' }}{{ (overview.changePct * 100).toFixed(2) }}%
            </span>
            <span v-else class="macro-delta flat">数据不可用</span>
          </div>
          <div class="macro-card">
            <span class="macro-label">市场温度（上涨占比）</span>
            <span class="macro-value num">{{ breadthRatio }}</span>
            <span class="macro-sub num">
              <template v-if="overview.breadthAvailable">
                涨 {{ overview.advancing ?? 0 }} / 跌 {{ overview.declining ?? 0 }}
              </template>
              <template v-else>涨跌家数不可用</template>
            </span>
          </div>
          <div class="macro-card">
            <span class="macro-label">数据截止</span>
            <span class="macro-value num">{{ overview.asOf || '—' }}</span>
            <span class="macro-sub">AkShare · 前复权日线</span>
          </div>
        </div>
        <p v-else-if="overviewError" class="state-error">行情概览获取失败：{{ overviewError }}</p>
        <p v-else class="state-loading">正在加载宏观数据…</p>
      </PanelFrame>

      <PanelFrame id="cockpit-quick" title="快速分析">
        <div class="quick-list">
          <button
            v-for="entry in workspace.watchlist"
            :key="entry.symbol"
            class="quick-item"
            type="button"
            @click="openAnalysis(entry.symbol)"
          >
            <span class="num">{{ entry.symbol }}</span>
            <span v-if="entry.lastScore !== null" class="quick-score num">
              {{ entry.lastScore }}
            </span>
            <span v-else class="quick-score flat">未分析</span>
          </button>
          <p v-if="workspace.watchlist.length === 0" class="state-empty">
            自选为空。按 Ctrl/⌘+K 输入「加入自选 600519」开始建立雷达。
          </p>
        </div>
      </PanelFrame>
    </div>

    <!-- 中列：智能体状态 -->
    <div class="col col-mid">
      <PanelFrame id="cockpit-agents" title="AI 智能体状态" :meta="stats ? `任务 ${stats.total}` : ''">
        <div v-if="stats" class="agent-stats">
          <div class="stat-card">
            <span class="stat-label">今日任务</span>
            <span class="stat-value num">{{ stats.total }}</span>
          </div>
          <div class="stat-card">
            <span class="stat-label">进行中</span>
            <span class="stat-value num" :class="stats.running > 0 ? 'up' : 'flat'">{{ stats.running }}</span>
          </div>
          <div class="stat-card">
            <span class="stat-label">已完成</span>
            <span class="stat-value num down">{{ stats.completed }}</span>
          </div>
          <div class="stat-card">
            <span class="stat-label">失败</span>
            <span class="stat-value num" :class="stats.failed > 0 ? 'text-red' : 'flat'">{{ stats.failed }}</span>
          </div>
          <div class="stat-card wide">
            <span class="stat-label">成功率</span>
            <span class="stat-value num">{{ successRatePct }}</span>
            <div class="stat-track">
              <div class="stat-fill" :style="{ width: `${(stats.successRate * 100).toFixed(1)}%` }" />
            </div>
          </div>
        </div>
        <p v-else-if="statsError" class="state-error">统计获取失败：{{ statsError }}</p>
        <p v-else class="state-loading">正在加载智能体状态…</p>
      </PanelFrame>

      <PanelFrame id="cockpit-pipeline" title="流水线拓扑">
        <ol class="pipeline">
          <li>数据摄取（AkShare · 前复权）</li>
          <li>基本面分析师（ROE/PE/PB/负债率）</li>
          <li>舆情分析师（关键词极性）</li>
          <li>技术分析师（MACD/RSI/布林）</li>
          <li>多空辩论（1-3 轮）</li>
          <li>风控经理（三档仓位）</li>
          <li>确定性回测（A 股成本模型）</li>
          <li>人话翻译（策略模式）</li>
        </ol>
      </PanelFrame>
    </div>

    <!-- 右列：预警抽屉 -->
    <div class="col col-right">
      <PanelFrame id="cockpit-alerts" title="AI 预警" :meta="`${alerts.length} 条`">
        <div class="alert-list">
          <article v-for="alert in alerts" :key="alert.id" class="alert-item">
            <header>
              <button class="alert-symbol num" type="button" @click="openAnalysis(alert.symbol)">
                {{ alert.symbol }}
              </button>
              <span class="alert-sev" :class="severityClass(alert.severity)">
                {{ severityLabel(alert.severity) }}
              </span>
              <time class="num">{{ new Date(alert.timestamp).toLocaleTimeString('zh-CN', { hour12: false }) }}</time>
            </header>
            <p>{{ alert.message }}</p>
          </article>
          <p v-if="alerts.length === 0" class="state-empty">
            暂无预警。对自选股完成一次分析后，AI 评分变动会在这里实时推送。
          </p>
        </div>
      </PanelFrame>
    </div>
  </div>
</template>

<style scoped>
.cockpit {
  display: grid;
  grid-template-columns: 1fr 1.2fr 1fr;
  gap: var(--space-3);
  height: 100%;
  min-height: 0;
}

.col {
  display: grid;
  gap: var(--space-3);
  grid-template-rows: auto 1fr;
  min-height: 0;
}

.macro-grid {
  display: grid;
  gap: var(--space-2);
}

.macro-card {
  display: grid;
  gap: 2px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
}

.macro-label {
  font-size: 11px;
  color: var(--text-muted);
}

.macro-value {
  font-size: 20px;
  font-weight: 700;
}

.macro-delta {
  font-size: 12px;
}

.macro-sub {
  font-size: 11px;
  color: var(--text-muted);
}

.quick-list {
  display: grid;
  gap: var(--space-2);
}

.quick-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
}

.quick-item:hover {
  border-color: var(--border-strong);
  background: var(--bg-hover);
}

.quick-score {
  font-size: 12px;
}

.agent-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-2);
}

.stat-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  display: grid;
  gap: 2px;
}

.stat-card.wide {
  grid-column: span 2;
}

.stat-label {
  font-size: 11px;
  color: var(--text-muted);
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
}

.stat-track {
  height: 4px;
  background: var(--border-subtle);
  border-radius: 2px;
  overflow: hidden;
  margin-top: var(--space-1);
}

.stat-fill {
  height: 100%;
  background: var(--verdict-green);
  transition: width 300ms ease;
}

.pipeline {
  margin: 0;
  padding-left: var(--space-4);
  display: grid;
  gap: var(--space-1);
  font-size: 12px;
  color: var(--text-secondary);
}

.alert-list {
  display: grid;
  gap: var(--space-2);
  max-height: 100%;
  overflow-y: auto;
}

.alert-item {
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
}

.alert-item header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-1);
}

.alert-symbol {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  padding: 0;
}

.alert-symbol:hover {
  text-decoration: underline;
}

.alert-sev {
  font-size: 10px;
  border: 1px solid currentColor;
  border-radius: 3px;
  padding: 0 4px;
}

.alert-item time {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted);
}

.alert-item p {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.state-loading,
.state-error,
.state-empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.state-error {
  color: var(--verdict-red);
}
</style>
