<template>
  <section class="indices" v-if="indices.length">
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
defineProps<{ indices: any[] }>()
function cls(v: number) { return v > 0 ? 'price-up' : v < 0 ? 'price-down' : 'price-flat' }
</script>

<style scoped>
/* 流体网格:卡片随屏宽自然收缩(auto-fit + minmax),任何宽度都完整放下,
   不再按断点切换固定宽度/横滑。窄卡只展示 涨跌幅(绝对变动是噪音)。 */
.indices {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(150px, 100%), 1fr));
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
/* 奇数张时最后一张落单半宽很难看——自动占满整行,内容横排填满 */
.index-card:last-child:nth-child(odd) { grid-column: 1 / -1; display: flex; align-items: baseline; gap: 12px; }
.index-card:last-child:nth-child(odd) .index-name { flex: 1; }
.index-card:last-child:nth-child(odd) .index-price { margin-top: 0; }
.index-card:last-child:nth-child(odd) .index-change { margin-top: 0; }
@media (max-width: 768px) {
  .indices { grid-template-columns: repeat(auto-fit, minmax(min(112px, 100%), 1fr)); gap: 8px; }
  .index-card { border-radius: var(--radius); padding: 10px 12px; }
  .index-price { font-size: 16px; }
}
</style>
