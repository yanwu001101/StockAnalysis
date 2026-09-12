<template>
  <span class="num" :class="cls">{{ text }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatNumber } from '@/utils/format'

// 涨跌染色数字：percent 带正负号与 %，number 只染色不加号，price 按 by 染色。
const props = withDefaults(defineProps<{
  value: number | string | null | undefined
  /** 决定颜色的数值；不传按 value 本身 */
  by?: number | null
  mode?: 'percent' | 'number' | 'price'
  digits?: number
  suffix?: string
  /** 0 是否显示为灰色（默认是） */
  flatZero?: boolean
}>(), { mode: 'percent', flatZero: true })

const num = computed(() => {
  const v = typeof props.value === 'string' ? Number(props.value) : props.value
  return v == null || !Number.isFinite(v) ? null : v
})

const signSource = computed(() => (props.by != null ? props.by : num.value))

const cls = computed(() => {
  const s = signSource.value
  if (s == null) return 'price-flat'
  if (s > 0) return 'price-up'
  if (s < 0) return 'price-down'
  return props.flatZero ? 'price-flat' : 'price-up'
})

const text = computed(() => {
  const v = num.value
  if (v == null) return '—'
  const digits = props.digits ?? (props.mode === 'percent' ? 2 : 2)
  if (props.mode === 'percent') {
    const sign = v > 0 ? '+' : ''
    return `${sign}${v.toFixed(digits)}${props.suffix ?? '%'}`
  }
  if (props.mode === 'price') return v.toFixed(digits) + (props.suffix ?? '')
  const sign = v > 0 ? '+' : ''
  return `${sign}${formatNumber(v, digits)}${props.suffix ?? ''}`
})
</script>
