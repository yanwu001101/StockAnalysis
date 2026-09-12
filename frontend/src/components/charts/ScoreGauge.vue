<template>
  <div class="score-gauge">
    <div class="gauge-ring" :style="ringStyle">
      <div class="gauge-inner">
        <span class="gauge-value num" :style="{ color: scoreColor }">{{ Math.round(score) }}</span>
        <span class="gauge-label">{{ label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { scoreLevel } from '@/utils/score'

const props = withDefaults(defineProps<{
  score: number
  label?: string
  size?: number
}>(), {
  label: '综合分',
  size: 100,
})

// 高分用品牌色，中分用警示色（文字级），低分固定用红 — 全部跟随主题变量
const scoreColor = computed(() => {
  const lv = scoreLevel(props.score)
  return lv === 'high' ? 'var(--brand)' : lv === 'mid' ? 'var(--warn-text)' : 'var(--color-red)'
})

const ringStyle = computed(() => {
  const pct = Math.min(100, Math.max(0, props.score))
  const deg = (pct / 100) * 360
  return {
    width: `${props.size}px`,
    height: `${props.size}px`,
    background: `conic-gradient(${scoreColor.value} ${deg}deg, var(--line) ${deg}deg)`,
  }
})
</script>

<style scoped>
.score-gauge { display: inline-flex; }
.gauge-ring {
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px;
}
.gauge-inner {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: var(--surface);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.gauge-value { font-size: 24px; font-weight: 700; line-height: 1; }
.gauge-label { font-size: 11px; color: var(--text-3); margin-top: 4px; }
</style>
