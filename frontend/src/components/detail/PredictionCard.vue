<template>
  <AppCard id="predict" title="预测">
    <template #actions>
      <SegmentTabs v-model="mode" :options="options" small />
    </template>
    <template v-if="mode === 'prob'">
      <PredictionPanel v-if="prediction" :prediction="prediction" />
      <el-empty v-else description="暂无涨跌概率数据" :image-size="72" />
    </template>
    <ProSignalPanel v-else :code="code" />
  </AppCard>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { PredictionResult } from '@/types'
import type { SegmentOption } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import PredictionPanel from '@/components/charts/PredictionPanel.vue'
import ProSignalPanel from './ProSignalPanel.vue'

// 涨跌概率（多策略）与专业预测（Leading 指标）在同一张卡片里切换。
type Mode = 'prob' | 'pro'
const props = withDefaults(defineProps<{
  prediction: PredictionResult | null
  code: string
  initialMode?: Mode
}>(), { initialMode: 'prob' })

const mode = ref<Mode>(props.initialMode)
const options: SegmentOption<Mode>[] = [
  { label: '涨跌概率', value: 'prob' },
  { label: '专业预测', value: 'pro' },
]

watch(() => props.initialMode, (m) => { mode.value = m })
defineExpose({ setMode: (m: Mode) => { mode.value = m } })
</script>
