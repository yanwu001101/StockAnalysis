<template>
  <span class="score-pill" :class="[level, size]">{{ text }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { scoreLevel } from '@/utils/score'

const props = withDefaults(defineProps<{
  score: number | null | undefined
  size?: 'sm' | 'md'
}>(), { size: 'md' })

const level = computed(() => scoreLevel(props.score))
const text = computed(() => (props.score == null || !Number.isFinite(props.score) ? '—' : Math.round(props.score)))
</script>

<style scoped>
.score-pill {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  padding: 2px 9px;
  border-radius: var(--radius-pill);
  font-variant-numeric: tabular-nums;
  line-height: 1.5;
}
.score-pill.sm { font-size: 11px; padding: 1px 7px; }
.score-pill.high { background: var(--brand-soft); color: var(--brand); }
.score-pill.mid  { background: var(--warn-soft); color: var(--warn-text); }
.score-pill.low  { background: var(--up-soft); color: var(--up); }
</style>
