<template>
  <section class="indices" v-if="indices.length" :style="{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }">
    <div class="index-card" v-for="idx in indices" :key="idx.code">
      <div class="index-name">{{ idx.name }}</div>
      <div class="index-price num" :class="cls(idx.changePercent)">{{ Number(idx.price).toFixed(2) }}</div>
      <div class="index-change num" :class="cls(idx.changePercent)">
        {{ idx.changePercent >= 0 ? '+' : '' }}{{ Number(idx.changePercent).toFixed(2) }}%
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDevice } from '@/composables/useDevice'

const props = defineProps<{ indices: any[] }>()
const { isMobile } = useDevice()
function cls(v: number) { return v > 0 ? 'price-up' : v < 0 ? 'price-down' : 'price-flat' }

// 均衡列数：行数 = ceil(n / 每行上限)，列数 = ceil(n / 行数)。
// 7 个指数桌面排 7 列一行；手机排 4+3——任何数量都不会再出现
// 「最后一张孤行占满整宽」的破相（原 auto-fit + 孤行占满规则已废）。
const cols = computed(() => {
  const n = props.indices.length
  if (!n) return 7
  const maxPerRow = isMobile.value ? 4 : 7
  const rows = Math.ceil(n / maxPerRow)
  return Math.ceil(n / rows)
})
</script>

<style scoped>
.indices {
  display: grid;
  gap: 10px;
}
.index-card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  padding: 12px 14px;
  box-shadow: var(--shadow-card);
  min-width: 0;
}
.index-name { font-size: 12px; color: var(--text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.index-price { font-size: 18px; font-weight: 600; margin-top: 4px; letter-spacing: -0.01em; }
.index-change { font-size: 12px; margin-top: 2px; white-space: nowrap; }
@media (max-width: 768px) {
  .indices { gap: 8px; }
  .index-card { border-radius: var(--radius); padding: 10px 12px; }
  .index-price { font-size: 16px; }
}
</style>
