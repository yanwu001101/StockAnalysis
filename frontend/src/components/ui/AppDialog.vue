<template>
  <el-drawer
    v-if="isMobile"
    :model-value="modelValue"
    direction="btt"
    :size="size"
    :title="title"
    :with-header="true"
    class="app-sheet"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="sheet-body"><slot /></div>
    <template v-if="$slots.footer" #footer>
      <div class="sheet-footer"><slot name="footer" /></div>
    </template>
  </el-drawer>
  <el-dialog
    v-else
    :model-value="modelValue"
    :title="title"
    :width="width"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <slot />
    <template v-if="$slots.footer" #footer><slot name="footer" /></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { useDevice } from '@/composables/useDevice'

// 桌面用居中对话框，手机用底部抽屉，调用方不用关心差异。
withDefaults(defineProps<{
  modelValue: boolean
  title?: string
  width?: string
  /** 手机抽屉高度 */
  size?: string
}>(), { width: '480px', size: 'auto' })

defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const { isMobile } = useDevice()
</script>

<style scoped>
.sheet-body { padding-bottom: env(safe-area-inset-bottom); }
.sheet-footer { display: flex; justify-content: flex-end; gap: 8px; padding-bottom: env(safe-area-inset-bottom); }
</style>

<style>
.app-sheet { border-radius: 16px 16px 0 0; max-height: 90vh; }
.app-sheet .el-drawer__header { margin-bottom: 8px; padding: 16px 16px 0; }
.app-sheet .el-drawer__body { padding: 8px 16px 16px; overflow-y: auto; }
.app-sheet .el-drawer__footer { padding: 8px 16px 12px; }
</style>
