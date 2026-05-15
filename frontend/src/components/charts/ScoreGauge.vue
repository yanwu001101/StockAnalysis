<template>
  <div class="score-gauge">
    <div class="gauge-ring" :style="ringStyle">
      <div class="gauge-inner">
        <span class="gauge-value" :style="{ color: scoreColor }">{{ score }}</span>
        <span class="gauge-label">{{ label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  score: number
  label?: string
  size?: number
}>(), {
  label: '综合分',
  size: 100,
})

const scoreColor = computed(() => {
  if (props.score >= 80) return '#2AE8A4'
  if (props.score >= 60) return '#FFC312'
  return '#FF4757'
})

const ringStyle = computed(() => {
  const pct = Math.min(100, Math.max(0, props.score))
  const deg = (pct / 100) * 360
  return {
    width: `${props.size}px`,
    height: `${props.size}px`,
    background: `conic-gradient(${scoreColor.value} ${deg}deg, rgba(0,212,255,0.08) ${deg}deg)`,
  }
})
</script>

<style scoped>
.score-gauge {
  display: inline-flex;
}
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
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.gauge-value {
  font-size: 24px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.gauge-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}
</style>
