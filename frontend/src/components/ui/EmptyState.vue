<template>
  <div class="empty-state" :class="variant" role="status">
    <div class="es-icon" aria-hidden="true">
      <el-icon :size="22">
        <component :is="icon" />
      </el-icon>
    </div>
    <div class="es-title">{{ title }}</div>
    <p v-if="description" class="es-desc">{{ description }}</p>
    <div v-if="$slots.default || (variant === 'error' && !hideRetry)" class="es-actions">
      <el-button v-if="variant === 'error' && !hideRetry" type="primary" size="small" :loading="loading" @click="$emit('retry')">
        重试
      </el-button>
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { DataLine, Search, WarningFilled } from '@element-plus/icons-vue'

/**
 * 四态空状态（首用 / 无结果 / 加载失败）。
 * - empty:      区块还没有数据，描述里给出下一步价值
 * - no-results: 筛选/搜索无命中，提示放宽条件（不要与首用混用）
 * - error:      请求失败 ≠ 没有数据，必须提供重试
 */
const props = withDefaults(defineProps<{
  variant?: 'empty' | 'no-results' | 'error'
  title?: string
  description?: string
  /** error 态隐藏重试按钮（例如全局已有重试入口） */
  hideRetry?: boolean
  loading?: boolean
}>(), {
  variant: 'empty',
  title: '',
  description: '',
  hideRetry: false,
  loading: false,
})

defineEmits<{ (e: 'retry'): void }>()

const icon = computed(() =>
  props.variant === 'error' ? WarningFilled : props.variant === 'no-results' ? Search : DataLine
)
const title = computed(() => props.title || ({
  empty: '暂无数据',
  'no-results': '没有匹配的结果',
  error: '加载失败',
}[props.variant]))
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 40px 20px;
  max-width: 440px;
  margin: 0 auto;
}
.es-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--bg-2);
  color: var(--text-4);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}
.error .es-icon { background: var(--color-red-soft); color: var(--color-red); }
.no-results .es-icon { background: var(--brand-soft); color: var(--brand); }
.es-title {
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
}
.es-desc {
  margin: 6px 0 0;
  font-size: var(--text-sm);
  color: var(--text-3);
  line-height: 1.6;
}
.es-actions { margin-top: 16px; display: flex; gap: 8px; align-items: center; }
</style>
