<template>
  <section class="indices" v-if="indices.length">
    <div class="index-card" v-for="idx in indices" :key="idx.code">
      <div class="index-name">{{ idx.name }}</div>
      <div class="index-price num" :class="cls(idx.changePercent)">{{ Number(idx.price).toFixed(2) }}</div>
      <div class="index-change num" :class="cls(idx.changePercent)">
        {{ idx.change >= 0 ? '+' : '' }}{{ Number(idx.change).toFixed(2) }}
        ({{ idx.changePercent >= 0 ? '+' : '' }}{{ Number(idx.changePercent).toFixed(2) }}%)
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{ indices: any[] }>()
function cls(v: number) { return v > 0 ? 'price-up' : v < 0 ? 'price-down' : 'price-flat' }
</script>

<style scoped>
.indices {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}
.index-card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  padding: 12px 14px;
  box-shadow: var(--shadow-card);
  min-width: 0;
}
.index-name { font-size: 12px; color: var(--text-3); white-space: nowrap; }
.index-price { font-size: 18px; font-weight: 600; margin-top: 4px; letter-spacing: -0.01em; }
.index-change { font-size: 12px; margin-top: 2px; white-space: nowrap; }
@media (max-width: 768px) {
  /* 手机：横向滑动一排，卡片固定宽度 */
  .indices {
    display: flex;
    overflow-x: auto;
    gap: 8px;
    margin: 0 -12px;
    padding: 0 12px;
    scrollbar-width: none;
    -webkit-overflow-scrolling: touch;
  }
  .indices::-webkit-scrollbar { display: none; }
  .index-card { flex: 0 0 132px; border-radius: var(--radius); padding: 10px 12px; }
  .index-price { font-size: 16px; }
}
</style>
