<template>
  <span v-if="col.type === 'change'"><ChangeText :value="numValue" :digits="col.digits ?? 2" :suffix="col.suffix" /></span>
  <span v-else-if="col.type === 'price'"><ChangeText :value="numValue" :by="signOf(col.by ?? 'changePercent')" mode="price" :digits="col.digits ?? 2" :suffix="col.suffix" /></span>
  <ScorePill v-else-if="col.type === 'score'" :score="numValue" :size="small ? 'sm' : 'md'" />
  <SignalTag v-else-if="col.type === 'signal'" :signal="strValue" />
  <span v-else-if="col.type === 'amount'" class="num" :class="amountCls">{{ amountText }}</span>
  <span v-else-if="col.type === 'percent'" class="num">{{ percentText }}</span>
  <span v-else-if="col.type === 'num'" class="num" :class="numCls">{{ numText }}</span>
  <span v-else class="st-text">{{ textValue }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { StockColumn } from '@/types/ui'
import { formatNumber } from '@/utils/format'
import { useAmountFormat } from '@/composables/useAmountFormat'
import ChangeText from './ChangeText.vue'
import ScorePill from './ScorePill.vue'
import SignalTag from './SignalTag.vue'

// 按列类型渲染一个单元格；表格和手机卡片共用。
const props = defineProps<{ row: any; col: StockColumn; small?: boolean }>()

const { formatText } = useAmountFormat()

const raw = computed(() => (props.col.format ? props.col.format(props.row) : props.row?.[props.col.key]))

const numValue = computed<number | null>(() => {
  const v = raw.value
  const n = typeof v === 'string' ? Number(v) : v
  return typeof n === 'number' && Number.isFinite(n) ? n : null
})
const strValue = computed(() => (raw.value == null ? '' : String(raw.value)))
const textValue = computed(() => (raw.value == null || raw.value === '' ? '—' : String(raw.value)))

function signOf(key: string): number | null {
  const v = props.row?.[key]
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

const signCls = computed(() => {
  const by = props.col.by ? signOf(props.col.by) : numValue.value
  if (by == null) return ''
  return by > 0 ? 'price-up' : by < 0 ? 'price-down' : 'price-flat'
})

const amountCls = computed(() => (props.col.colored === false ? '' : signCls.value))
const amountText = computed(() => {
  if (numValue.value == null) return '—'
  return formatText(numValue.value, props.col.digits ?? 2) + (props.col.suffix ?? '')
})

const percentText = computed(() => {
  if (numValue.value == null) return '—'
  return numValue.value.toFixed(props.col.digits ?? 2) + (props.col.suffix ?? '%')
})

const numCls = computed(() => (props.col.colored ? signCls.value : ''))
const numText = computed(() => {
  if (numValue.value == null) return '—'
  return formatNumber(numValue.value, props.col.digits ?? 0) + (props.col.suffix ?? '')
})
</script>
