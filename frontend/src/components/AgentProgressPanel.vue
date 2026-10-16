/**
 * AgentProgressPanel — pure presentational.
 *
 * Receives the four agent cards (already keyed by the store) and renders
 * them with semantic HTML + CSS Modules: a breathing status light, a flat
 * progress bar and a rolling "streaming thoughts" log. No Element Plus cards.
 */
<script setup lang="ts">
import { useCssModule } from 'vue'
import type { AgentCardState } from '@/stores/useAnalysisStore'

defineProps<{
  agents: readonly AgentCardState[]
  /** bare 模式：去掉自带的面板外框（已被 PanelFrame 包裹时使用） */
  bare?: boolean
}>()

const css = useCssModule()

/** Resolve one or more CSS-module class names (dashed keys are exported as-is). */
function cls(...names: string[]): string {
  return names
    .map((name) => css[name] ?? '')
    .filter((value) => value.length > 0)
    .join(' ')
}

function statusLabel(status: AgentCardState['status']): string {
  switch (status) {
    case 'PENDING':
      return '等待中'
    case 'RUNNING':
      return '进行中'
    case 'COMPLETED':
      return '已完成'
    case 'FAILED':
      return '失败'
  }
}
</script>

<template>
  <section :class="cls(bare ? 'bare' : 'panel')" aria-label="智能体进度">
    <h2 :class="cls('panel-title')">智能体工作流</h2>
    <ol v-if="agents.length > 0" :class="cls('agent-list')">
      <li
        v-for="agent in agents"
        :key="agent.agentId"
        :class="cls('agent-card', `is-${agent.status.toLowerCase()}`)"
        :data-agent="agent.agentId"
      >
        <div :class="cls('agent-head')">
          <span
            :class="cls('breathing-light')"
            :aria-label="statusLabel(agent.status)"
            role="img"
          />
          <span :class="cls('agent-name')">{{ agent.agentName }}</span>
          <span :class="cls('agent-status', 'num')">{{ statusLabel(agent.status) }}</span>
          <span :class="cls('agent-progress', 'num')">{{ Math.round(agent.progress * 100) }}%</span>
        </div>
        <div
          :class="cls('progress-track')"
          role="progressbar"
          :aria-valuenow="Math.round(agent.progress * 100)"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <div :class="cls('progress-fill')" :style="{ width: `${agent.progress * 100}%` }" />
        </div>
        <p v-if="agent.message" :class="cls('agent-message')">{{ agent.message }}</p>
        <ul v-if="agent.thoughts.length > 1" :class="cls('thoughts')" aria-label="流式思考">
          <li v-for="(thought, index) in agent.thoughts.slice(0, -1)" :key="index">
            {{ thought }}
          </li>
        </ul>
      </li>
    </ol>
    <p v-else :class="cls('empty')">提交一只股票代码后，四个智能体将并行展开工作。</p>
  </section>
</template>

<style module>
.panel {
  background: var(--bg-panel);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-4) var(--space-6);
}

.panel-title {
  margin: 0 0 var(--space-4);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.08em;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.agent-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--space-3);
}

.agent-card {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: var(--space-3) var(--space-4);
  background: var(--bg-elevated);
}

.agent-head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.agent-name {
  font-weight: 500;
}

.agent-status {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-secondary);
}

.agent-progress {
  font-size: 12px;
  color: var(--text-secondary);
  min-width: 44px;
  text-align: right;
}

.breathing-light {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
  flex: none;
}

.is-running .breathing-light {
  background: #2f81f7;
  animation: breathe 1.6s ease-in-out infinite;
}

.is-completed .breathing-light {
  background: var(--verdict-green);
}

.is-failed .breathing-light {
  background: var(--verdict-red);
}

.is-pending .breathing-light {
  background: var(--text-muted);
}

@keyframes breathe {
  0%,
  100% {
    opacity: 0.25;
  }
  50% {
    opacity: 1;
  }
}

.progress-track {
  margin-top: var(--space-2);
  height: 3px;
  background: var(--border-subtle);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #2f81f7;
  transition: width 240ms ease;
}

.is-completed .progress-fill {
  background: var(--verdict-green);
}

.is-failed .progress-fill {
  background: var(--verdict-red);
}

.agent-message {
  margin: var(--space-2) 0 0;
  font-size: 13px;
  color: var(--text-primary);
}

.thoughts {
  list-style: none;
  margin: var(--space-2) 0 0;
  padding: 0 0 0 var(--space-4);
  border-left: 1px solid var(--border-subtle);
  display: grid;
  gap: 2px;
  max-height: 96px;
  overflow-y: auto;
}

.thoughts li {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.empty {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
