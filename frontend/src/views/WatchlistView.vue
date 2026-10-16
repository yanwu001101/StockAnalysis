/**
 * WatchlistView — /watchlist 雷达监控。
 *
 * 上下分屏：上方自选股列表（AI 评分变动列），下方实时滚动的 AI 异动日志。
 */
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import PanelFrame from '@/components/PanelFrame.vue'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import { useAnalysisStore } from '@/stores/useAnalysisStore'
import { displaySymbol } from '@/utils/selectors'

const router = useRouter()
const workspace = useWorkspaceStore()
const analysis = useAnalysisStore()
const { watchlist, alerts } = storeToRefs(workspace)

const newSymbol = ref<string>('')

function add(): void {
  const digits = newSymbol.value.replace(/\D/g, '')
  if (digits.length < 6) return
  workspace.addToWatchlist(digits.padStart(6, '0').slice(-6))
  newSymbol.value = ''
}

async function analyze(symbol: string): Promise<void> {
  await router.push(`/analysis/${symbol}`)
  await analysis.submit(symbol)
}

function scoreClass(score: number | null): string {
  if (score === null) return 'flat'
  if (score >= 65) return 'text-green'
  if (score >= 35) return 'text-yellow'
  return 'text-red'
}

function signalLabel(signal: string | null): string {
  if (signal === 'BUY') return '买入倾向'
  if (signal === 'SELL') return '卖出倾向'
  if (signal === 'HOLD') return '观望'
  return '—'
}

function severityClass(severity: 'info' | 'warning' | 'critical'): string {
  if (severity === 'critical') return 'text-red'
  if (severity === 'warning') return 'text-yellow'
  return 'flat'
}
</script>

<template>
  <div class="radar">
    <PanelFrame id="radar-list" title="自选股" :meta="`${watchlist.length} 只`">
      <div class="watch-toolbar">
        <input
          v-model="newSymbol"
          class="num"
          type="text"
          placeholder="输入 6 位代码加入自选"
          maxlength="10"
          @keyup.enter="add"
        />
        <button class="add-btn" type="button" @click="add">加入</button>
      </div>
      <table v-if="watchlist.length > 0" class="watch-table">
        <thead>
          <tr>
            <th>代码</th>
            <th>展示代码</th>
            <th>AI 评分</th>
            <th>信号</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in watchlist" :key="entry.symbol">
            <td class="num">{{ entry.symbol }}</td>
            <td class="num muted">{{ displaySymbol(entry.symbol) }}</td>
            <td class="num score" :class="scoreClass(entry.lastScore)">
              {{ entry.lastScore ?? '—' }}
            </td>
            <td :class="scoreClass(entry.lastScore)">{{ signalLabel(entry.lastSignal) }}</td>
            <td class="num muted">
              {{ entry.updatedAt ? new Date(entry.updatedAt).toLocaleString('zh-CN', { hour12: false }) : '—' }}
            </td>
            <td class="ops">
              <button type="button" @click="analyze(entry.symbol)">分析</button>
              <button type="button" class="danger" @click="workspace.removeFromWatchlist(entry.symbol)">
                移除
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="state-empty">雷达为空。加入第一只自选股开始 AI 监控。</p>
    </PanelFrame>

    <PanelFrame id="radar-log" title="AI 异动日志" :meta="`${alerts.length} 条`">
      <div class="log-list">
        <article v-for="alert in alerts" :key="alert.id" class="log-item">
          <time class="num">{{ new Date(alert.timestamp).toLocaleTimeString('zh-CN', { hour12: false }) }}</time>
          <button class="log-symbol num" type="button" @click="analyze(alert.symbol)">
            {{ alert.symbol }}
          </button>
          <span class="log-sev" :class="severityClass(alert.severity)">
            {{ alert.severity === 'critical' ? '强烈' : alert.severity === 'warning' ? '注意' : '提示' }}
          </span>
          <p>{{ alert.message }}</p>
        </article>
        <p v-if="alerts.length === 0" class="state-empty">
          暂无异动。评分变动 ≥10 分或首次产出结论时会自动记录。
        </p>
      </div>
    </PanelFrame>
  </div>
</template>

<style scoped>
.radar {
  display: grid;
  grid-template-rows: 1.2fr 1fr;
  gap: var(--space-3);
  height: 100%;
  min-height: 0;
}

.watch-toolbar {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.watch-toolbar input {
  background: var(--bg-app);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  padding: var(--space-1) var(--space-2);
  outline: none;
  width: 220px;
}

.watch-toolbar input:focus {
  border-color: var(--accent);
}

.add-btn {
  background: var(--accent);
  border: none;
  border-radius: var(--radius-sm);
  color: #fff;
  font-size: 12px;
  padding: var(--space-1) var(--space-4);
  cursor: pointer;
}

.watch-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.watch-table th {
  text-align: left;
  font-weight: 500;
  color: var(--text-muted);
  font-size: 11px;
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--border-subtle);
}

.watch-table td {
  padding: var(--space-2);
  border-bottom: 1px solid var(--border-subtle);
}

.watch-table tbody tr:hover {
  background: var(--bg-hover);
}

.score {
  font-size: 15px;
  font-weight: 700;
}

.muted {
  color: var(--text-muted);
}

.ops {
  display: flex;
  gap: var(--space-2);
}

.ops button {
  background: none;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 11px;
  padding: 1px 8px;
  cursor: pointer;
}

.ops button:hover {
  color: var(--text-primary);
  border-color: var(--accent);
}

.ops button.danger:hover {
  color: var(--verdict-red);
  border-color: var(--verdict-red);
}

.log-list {
  display: grid;
  gap: var(--space-2);
  max-height: 100%;
  overflow-y: auto;
  align-content: start;
}

.log-item {
  display: grid;
  grid-template-columns: auto auto auto 1fr;
  gap: var(--space-2);
  align-items: baseline;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
}

.log-item time {
  font-size: 10px;
  color: var(--text-muted);
}

.log-symbol {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  padding: 0;
}

.log-symbol:hover {
  text-decoration: underline;
}

.log-sev {
  font-size: 10px;
  border: 1px solid currentColor;
  border-radius: 3px;
  padding: 0 4px;
}

.log-item p {
  margin: 0;
  grid-column: 1 / -1;
  font-size: 12px;
  color: var(--text-secondary);
}

.state-empty {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
