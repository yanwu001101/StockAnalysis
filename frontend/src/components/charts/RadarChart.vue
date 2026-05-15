<template>
  <div ref="chartRef" class="radar-chart" :style="{ height: height + 'px' }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = withDefaults(defineProps<{
  indicators: { name: string; max: number }[]
  values: number[]
  label?: string
  color?: string
  height?: number
}>(), {
  color: '#00D4FF',
  height: 300,
})

const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

function buildOption() {
  return {
    backgroundColor: 'transparent',
    radar: {
      indicator: props.indicators,
      shape: 'polygon',
      axisName: { color: '#8892A4', fontSize: 11 },
      splitArea: { areaStyle: { color: ['rgba(0,212,255,0.02)', 'rgba(0,212,255,0.04)'] } },
      splitLine: { lineStyle: { color: 'rgba(0,212,255,0.1)' } },
      axisLine: { lineStyle: { color: 'rgba(0,212,255,0.15)' } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: props.values,
        name: props.label || '',
        areaStyle: { color: `${props.color}20` },
        lineStyle: { color: props.color, width: 2 },
        itemStyle: { color: props.color },
        symbol: 'circle',
        symbolSize: 5,
      }],
    }],
  }
}

onMounted(() => {
  nextTick(() => {
    if (chartRef.value) {
      chart = echarts.init(chartRef.value)
      chart.setOption(buildOption())
      window.addEventListener('resize', () => chart?.resize())
    }
  })
})

onUnmounted(() => chart?.dispose())

watch(() => props.values, () => {
  chart?.setOption(buildOption(), true)
}, { deep: true })
</script>

<style scoped>
.radar-chart {
  width: 100%;
}
</style>
