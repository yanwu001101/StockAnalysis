<template>
  <span class="stab" :title="title">
    <span class="stab-meter" aria-hidden="true">
      <i v-for="i in 5" :key="i" :class="{ on: i <= level, none: level === 0 }" />
    </span>
    <span class="stab-text">
      <b v-if="value != null" class="num">{{ Math.round(value) }}</b>
      <span class="stab-grade">{{ grade }}</span>
    </span>
    <span v-if="series && series.length && showSeries" class="stab-series mono">{{ seriesText }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

// 排名稳定度:五段计量条(1 段 = 20 分)+ 数值 + 文字等级 + 排名序列。
// 序列是原始证据,计量条只是压缩视图;两者都来自服务端。
const props = withDefaults(defineProps<{
  value: number | null | undefined
  grade: string
  level: number
  series?: (number | null)[]
  showSeries?: boolean
  cap?: number
}>(), { showSeries: true, cap: 150 })

const seriesText = computed(() =>
  (props.series || []).map(r => (r == null ? `>${props.cap}` : String(r))).join('·'))
const title = computed(() =>
  props.value == null
    ? '快照不足 3 个,稳定度暂不可评'
    : `排名稳定度 ${Math.round(props.value)} = 100 − 3×排名标准差 − 0.5×(平均排名−1);排名序列 ${seriesText.value}`)
</script>

<style scoped>
.stab { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.stab-meter { display: inline-flex; gap: 2px; }
.stab-meter i { width: 10px; height: 8px; border-radius: 2px; background: var(--line-strong); display: inline-block; }
.stab-meter i.on { background: var(--brand); }
.stab-meter i.none { background: var(--line); }
.stab-text { display: inline-flex; gap: 4px; align-items: baseline; font-size: 12px; color: var(--text-2); }
.stab-text b { color: var(--text); }
.stab-grade { color: var(--text-3); }
.stab-series { font-size: 11px; color: var(--text-4); }
</style>
