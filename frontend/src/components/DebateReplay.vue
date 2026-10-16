/**
 * DebateReplay — 多空辩论回放。
 *
 * 按轮次渲染 Bull/Bear 的论据与信念强度（conviction 条形图）。
 * 纯展示组件，数据来自 verdict.debate。
 */
<script setup lang="ts">
import type { DebateDTO } from '@/types/quant'

defineProps<{
  debate: readonly DebateDTO[]
}>()

function convictionWidth(value: number): string {
  return `${Math.max(0, Math.min(1, value)) * 100}%`
}
</script>

<template>
  <div class="debate-replay">
    <template v-if="debate.length > 0">
      <div v-for="round in [...new Set(debate.map((d) => d.round))].sort((a, b) => a - b)" :key="round" class="round">
        <div class="round-head">第 {{ round }} 轮</div>
        <div class="round-sides">
          <article
            v-for="entry in debate.filter((d) => d.round === round)"
            :key="`${entry.round}-${entry.side}`"
            class="turn"
            :class="entry.side === 'BULL' ? 'bull' : 'bear'"
          >
            <header>
              <span class="side-tag">{{ entry.side === 'BULL' ? '多方研究员' : '空方研究员' }}</span>
              <span class="conviction">
                <i class="conviction-label">信念</i>
                <span class="conviction-track"><span class="conviction-fill" :style="{ width: convictionWidth(entry.conviction) }" /></span>
                <span class="num">{{ (entry.conviction * 100).toFixed(0) }}%</span>
              </span>
            </header>
            <p>{{ entry.argument }}</p>
          </article>
        </div>
      </div>
    </template>
    <p v-else class="empty">本次分析没有产生辩论记录（数据不足或辩论节点未执行）。</p>
  </div>
</template>

<style scoped>
.debate-replay {
  display: grid;
  gap: var(--space-4);
}

.round-head {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: var(--space-2);
}

.round-sides {
  display: grid;
  gap: var(--space-2);
}

.turn {
  border: 1px solid var(--border-subtle);
  border-left-width: 3px;
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-elevated);
}

.turn.bull {
  border-left-color: var(--color-up);
}

.turn.bear {
  border-left-color: var(--color-down);
}

.turn header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-1);
}

.side-tag {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
}

.conviction {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 10px;
  color: var(--text-muted);
}

.conviction-track {
  width: 72px;
  height: 4px;
  background: var(--border-subtle);
  border-radius: 2px;
  overflow: hidden;
}

.conviction-fill {
  display: block;
  height: 100%;
  background: var(--accent);
}

.turn p {
  margin: 0;
  font-size: 12px;
  color: var(--text-primary);
  line-height: 1.7;
}

.empty {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
