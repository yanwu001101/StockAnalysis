<template>
  <div class="skeleton-rows" :class="{ shimmer }" aria-busy="true" aria-label="加载中">
    <div v-for="i in rows" :key="i" class="sk-row" :style="{ height: rowHeight + 'px' }">
      <span class="sk-bar rank" v-if="rank" />
      <span class="sk-bar name" />
      <span class="sk-bar cell" v-for="c in cells" :key="c" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 表格加载骨架：行高与列分布对齐真实表格（rank + 名称 + 数字列），
 * 整组共享一个脉冲周期，避免逐元素闪烁。
 */
withDefaults(defineProps<{
  rows?: number
  /** 单行高度，需与真实行高一致避免加载完成后跳动 */
  rowHeight?: number
  /** 名称列之后的数字列数量 */
  cells?: number
  rank?: boolean
  /** 关闭脉冲（reduced-motion 由 CSS 兜底） */
  shimmer?: boolean
}>(), { rows: 6, rowHeight: 44, cells: 4, rank: true, shimmer: true })
</script>

<style scoped>
.skeleton-rows { width: 100%; }
.sk-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 12px;
  border-bottom: 1px solid var(--line);
}
.sk-row:last-child { border-bottom: 0; }
.shimmer .sk-bar { animation: skeleton-pulse 1.4s ease-in-out infinite; }
.sk-bar {
  display: inline-block;
  height: 10px;
  border-radius: 5px;
  background: var(--bg-2);
}
.sk-bar.rank { width: 14px; flex-shrink: 0; }
.sk-bar.name { width: 18%; }
.sk-bar.cell { width: 12%; margin-left: auto; }
.sk-bar.cell:first-of-type { margin-left: 0; }
@media (prefers-reduced-motion: reduce) {
  .shimmer .sk-bar { animation: none; }
}
</style>
