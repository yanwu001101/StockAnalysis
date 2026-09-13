<template>
  <div class="chart-wrap" :style="{ height: height + 'px' }">
    <div v-if="loading" class="chart-loading">
      <div class="sk-row" style="width: 88%; height: 30%;">
        <div class="skeleton-block" style="flex: 1; height: 100%;"></div>
      </div>
      <div class="sk-row" style="width: 100%; height: 34%;">
        <div class="skeleton-block" style="flex: 1; height: 100%;"></div>
      </div>
      <div class="sk-row" style="width: 72%; height: 22%;">
        <div class="skeleton-block" style="flex: 1; height: 100%;"></div>
      </div>
    </div>
    <div v-else-if="!option || !hasData" class="chart-overlay">
      <span>{{ placeholder }}</span>
    </div>
    <div ref="el" class="base-chart" :style="{ height: height + 'px' }"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useEcharts } from '@/composables/useEcharts'

// 只负责 ECharts 生命周期的空壳：调用方用 useChartTokens() 算好 option 传进来即可。
// loading 期间渲染骨架条；option 为空渲染占位文案——禁止裸空白（SKILL §34）。
const props = withDefaults(defineProps<{
  option: EChartsOption | null | undefined
  height?: number
  loading?: boolean
  placeholder?: string
}>(), { height: 240, loading: false, placeholder: '暂无数据' })

const el = ref<HTMLElement>()
useEcharts(el, () => props.option, () => props.option)

const hasData = computed(() => {
  const s = (props.option as any)?.series
  if (!s) return false
  return Array.isArray(s) ? s.length > 0 : true
})
</script>

<style scoped>
.chart-wrap { position: relative; width: 100%; min-width: 0; }
.base-chart { width: 100%; min-width: 0; }
.chart-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 8px 4px;
}
.sk-row { display: flex; }
</style>
