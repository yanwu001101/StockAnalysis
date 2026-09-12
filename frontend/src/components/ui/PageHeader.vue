<template>
  <!-- 手机端顶栏已经显示了页面标题，这里只在桌面渲染 -->
  <header v-if="!isMobile" class="page-header">
    <div class="ph-text">
      <h1>{{ title }}</h1>
      <p v-if="sub || $slots.sub" class="ph-sub"><slot name="sub">{{ sub }}</slot></p>
    </div>
    <div v-if="$slots.default" class="ph-actions"><slot /></div>
  </header>
</template>

<script setup lang="ts">
import { useDevice } from '@/composables/useDevice'

defineProps<{ title: string; sub?: string }>()
const { isMobile } = useDevice()
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 12px;
  margin-bottom: 18px;
}
.page-header h1 { font-size: 22px; font-weight: 600; }
.ph-sub { margin-top: 4px; color: var(--text-3); font-size: 13px; }
.ph-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
</style>
