<template>
  <div ref="root" class="seg-tabs" :class="{ block, small }" role="tablist">
    <button
      v-for="o in options"
      :key="String(o.value)"
      type="button"
      role="tab"
      class="seg-btn"
      :class="{ active: o.value === modelValue }"
      :aria-selected="o.value === modelValue"
      :style="o.color && o.value === modelValue ? { color: o.color } : undefined"
      @click="$emit('update:modelValue', o.value)"
    >{{ o.label }}</button>
  </div>
</template>

<script setup lang="ts" generic="T extends string | number">
import { nextTick, onMounted, ref, watch } from 'vue'
import type { SegmentOption } from '@/types/ui'

const props = withDefaults(defineProps<{
  modelValue: T
  options: SegmentOption<T>[]
  /** 撑满整行，按钮等分 */
  block?: boolean
  small?: boolean
}>(), { block: false, small: false })

defineEmits<{ (e: 'update:modelValue', v: T): void }>()

// 手机上选项超出一屏时横向滚动，当前项要能看见（如从旧链接直接落到最后一个 tab）。
const root = ref<HTMLElement>()
function revealActive(smooth = true) {
  const el = root.value
  if (!el || el.scrollWidth <= el.clientWidth) return
  const btn = el.querySelector<HTMLElement>('.seg-btn.active')
  if (!btn) return
  const left = btn.offsetLeft - (el.clientWidth - btn.offsetWidth) / 2
  el.scrollTo({ left: Math.max(0, left), behavior: smooth ? 'smooth' : 'auto' })
}
onMounted(() => nextTick(() => revealActive(false)))
watch(() => props.modelValue, () => nextTick(() => revealActive()))
</script>

<style scoped>
.seg-tabs {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  background: var(--bg-2);
  border-radius: 10px;
  max-width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}
.seg-tabs::-webkit-scrollbar { display: none; }
.seg-tabs.block { display: flex; }
/* 窄屏等分会被长文案挤爆（“策略权重”“回测”），小屏改回内容宽度 + 横向滚动 */
@media (min-width: 769px) {
  .seg-tabs.block .seg-btn { flex: 1; }
}
.seg-btn {
  border: 0;
  background: transparent;
  color: var(--text-3);
  font-size: 13px;
  font-weight: 500;
  padding: 0 12px;
  height: 32px;
  border-radius: 8px;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: background 0.15s ease, color 0.15s ease;
}
.seg-tabs.small .seg-btn { height: 28px; font-size: 12px; padding: 0 10px; }
.seg-btn:hover { color: var(--text); }
.seg-btn.active {
  background: var(--surface);
  color: var(--text);
  box-shadow: var(--shadow-card);
}
@media (max-width: 768px) {
  .seg-btn { height: 36px; font-size: 14px; padding: 0 14px; }
  .seg-tabs.small .seg-btn { height: 30px; font-size: 13px; }
}
</style>
