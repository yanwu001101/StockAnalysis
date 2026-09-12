<template>
  <el-button
    :type="inList ? 'warning' : 'primary'"
    :plain="true"
    :size="size"
    :loading="busy"
    :circle="iconOnly"
    @click.stop="onClick"
  >
    <el-icon><component :is="inList ? StarFilled : Star" /></el-icon>
    <span v-if="!iconOnly" class="wb-text">{{ inList ? '已自选' : '加自选' }}</span>
  </el-button>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Star, StarFilled } from '@element-plus/icons-vue'
import { useWatchlist } from '@/composables/useWatchlist'

const props = withDefaults(defineProps<{
  code: string
  size?: 'small' | 'default' | 'large'
  iconOnly?: boolean
}>(), { size: 'small', iconOnly: false })

const wl = useWatchlist()
const busy = ref(false)
const inList = computed(() => wl.has(props.code))

async function onClick() {
  busy.value = true
  try { await wl.toggle(props.code) } catch { /* 拦截器已提示 */ } finally { busy.value = false }
}

onMounted(() => { wl.ensureLoaded() })
</script>

<style scoped>
.wb-text { margin-left: 4px; }
</style>
