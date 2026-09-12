<template>
  <div class="stat-grid" :class="[variant, size]" :style="gridStyle">
    <div v-for="(it, i) in items" :key="it.key ?? i" class="stat-cell">
      <span class="stat-label">{{ it.label }}</span>
      <span class="stat-value num" :class="it.cls" :style="it.color ? { color: it.color } : undefined">{{ it.value ?? '—' }}</span>
      <span v-if="it.foot" class="stat-foot">{{ it.foot }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { StatItem } from '@/types/ui'

const props = withDefaults(defineProps<{
  items: StatItem[]
  /** 固定列数；不传则按 minWidth 自适应 */
  cols?: number
  minWidth?: number
  /** card：每格独立卡片；plain：嵌在父卡片内的浅底格子；inline：无底色两端对齐行 */
  variant?: 'card' | 'plain' | 'inline'
  size?: 'sm' | 'md' | 'lg'
}>(), { minWidth: 120, variant: 'plain', size: 'md' })

const gridStyle = computed(() => props.cols
  ? { gridTemplateColumns: `repeat(${props.cols}, minmax(0, 1fr))` }
  : { gridTemplateColumns: `repeat(auto-fit, minmax(${props.minWidth}px, 1fr))` })
</script>

<style scoped>
.stat-grid { display: grid; gap: 10px; }
.stat-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 12px 14px;
  border-radius: var(--radius);
}
.stat-grid.card .stat-cell { background: var(--surface); box-shadow: var(--shadow-card); border-radius: var(--radius-lg); padding: 16px 18px; }
.stat-grid.plain .stat-cell { background: var(--bg-2); }
.stat-grid.inline { gap: 0 24px; }
.stat-grid.inline .stat-cell {
  flex-direction: row;
  justify-content: space-between;
  align-items: baseline;
  padding: 7px 0;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
}
.stat-label { font-size: 12px; color: var(--text-3); }
.stat-value { font-size: 18px; font-weight: 600; color: var(--text); line-height: 1.2; letter-spacing: -0.01em; overflow-wrap: anywhere; }
.stat-grid.sm .stat-value { font-size: 15px; }
.stat-grid.lg .stat-value { font-size: 26px; }
.stat-foot { font-size: 12px; color: var(--text-4); }
@media (max-width: 768px) {
  .stat-grid.card .stat-cell { padding: 12px 14px; }
  .stat-grid.lg .stat-value { font-size: 22px; }
}
</style>
