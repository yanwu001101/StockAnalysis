<template>
  <section class="app-card" :class="{ flush, compact }" v-loading="loading">
    <header v-if="title || $slots.title || $slots.actions" class="ac-head">
      <div class="ac-title-wrap">
        <div class="ac-title"><slot name="title">{{ title }}</slot></div>
        <p v-if="sub || $slots.sub" class="ac-sub"><slot name="sub">{{ sub }}</slot></p>
      </div>
      <div v-if="$slots.actions" class="ac-actions"><slot name="actions" /></div>
    </header>
    <slot />
  </section>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  sub?: string
  /** 内容区不留内边距（放表格 / 列表时用） */
  flush?: boolean
  /** 标题与内容间距更紧凑 */
  compact?: boolean
  loading?: boolean
}>(), { flush: false, compact: false, loading: false })
</script>

<style scoped>
.app-card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 16px 18px;
  min-width: 0;
}
.app-card.flush { padding: 0; overflow: hidden; }
.app-card.flush .ac-head { padding: 14px 16px 0; }
.ac-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}
.app-card.compact .ac-head { margin-bottom: 8px; }
.ac-title { font-size: 15px; font-weight: 600; color: var(--text); margin: 0; }
.ac-sub { color: var(--text-3); font-size: 12px; margin: 2px 0 0; }
.ac-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; flex-shrink: 0; }
@media (max-width: 768px) {
  .app-card { padding: 14px; border-radius: var(--radius); }
  .app-card.flush { padding: 0; }
  .app-card.flush .ac-head { padding: 12px 14px 0; }
  .ac-head { flex-wrap: wrap; }
  /* 操作区允许收缩并换行，否则一排按钮会把卡片撑出屏幕 */
  .ac-actions { flex-shrink: 1; min-width: 0; max-width: 100%; }
  .ac-actions :deep(.el-button + .el-button) { margin-left: 0; }
}
</style>
