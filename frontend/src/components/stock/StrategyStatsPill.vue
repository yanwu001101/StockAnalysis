<template>
  <span v-if="stats" class="strat-pill" :class="stratLevel(stats)">
    {{ stats.bullish }}/{{ stats.effective }}
    <span class="strat-trig">· {{ stats.triggered }}</span>
  </span>
  <span v-else-if="stats === undefined" class="strat-loading">···</span>
  <span v-else class="strat-na">—</span>
</template>

<script setup lang="ts">
import { stratLevel, type StrategyStats } from '@/utils/score'

// undefined = 还在加载，null = 无数据
defineProps<{ stats?: StrategyStats | null }>()
</script>

<style scoped>
.strat-pill {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 700;
  padding: 2px 9px;
  border-radius: var(--radius-pill);
  font-variant-numeric: tabular-nums;
  line-height: 1.4;
  white-space: nowrap;
}
.strat-pill.high { background: var(--up-soft); color: var(--up); }
.strat-pill.mid { background: var(--warn-soft); color: var(--warn-text); }
.strat-pill.low { background: var(--surface-2); color: var(--text-3); }
.strat-trig { font-size: 10px; font-weight: 600; opacity: 0.75; }
.strat-loading { color: var(--text-4); letter-spacing: 1px; }
.strat-na { color: var(--text-4); }
</style>
