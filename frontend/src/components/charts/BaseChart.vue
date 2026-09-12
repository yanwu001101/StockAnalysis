<template>
  <div ref="el" class="base-chart" :style="{ height: height + 'px' }"></div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { useEcharts } from '@/composables/useEcharts'

// 只负责 ECharts 生命周期的空壳：调用方用 useChartTokens() 算好 option 传进来即可。
const props = withDefaults(defineProps<{
  option: EChartsOption | null | undefined
  height?: number
}>(), { height: 240 })

const el = ref<HTMLElement>()
useEcharts(el, () => props.option, () => props.option)
</script>

<style scoped>
.base-chart { width: 100%; min-width: 0; }
</style>
