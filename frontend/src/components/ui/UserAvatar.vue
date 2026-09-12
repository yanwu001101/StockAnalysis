<template>
  <div class="user-avatar" :style="style">{{ initial }}</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  /** 用户昵称或用户名，取首字符做缩写 */
  name?: string
  size?: number
}>(), { size: 32 })

const initial = computed(() => props.name?.trim()?.[0]?.toUpperCase() || 'U')
const style = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  fontSize: `${Math.round(props.size * 0.42)}px`,
}))
</script>

<style scoped>
.user-avatar {
  border-radius: 50%;
  background: var(--brand);
  color: var(--on-brand);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  flex-shrink: 0;
  user-select: none;
}
</style>
