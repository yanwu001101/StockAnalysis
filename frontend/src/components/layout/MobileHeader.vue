<template>
  <header class="m-header">
    <div class="mh-left">
      <button v-if="back" type="button" class="mh-btn" aria-label="返回" @click="goBack">
        <el-icon :size="20"><ArrowLeft /></el-icon>
      </button>
      <span class="mh-title">{{ title }}</span>
    </div>
    <div class="mh-right">
      <span v-if="store.reloader && store.localTimeMs" class="mh-time num" :class="{ stale: isStale }">{{ shortTime }}</span>
      <button
        v-if="store.reloader"
        type="button"
        class="mh-btn"
        :disabled="store.isRefreshing"
        aria-label="刷新"
        @click="store.invokeReloader()"
      >
        <el-icon :size="18" :class="{ spinning: store.isRefreshing }"><Refresh /></el-icon>
      </button>
      <button type="button" class="mh-btn" aria-label="搜索" @click="$emit('search')">
        <el-icon :size="19"><Search /></el-icon>
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Refresh, Search } from '@element-plus/icons-vue'
import { useRefreshStore } from '@/stores/refresh'

defineProps<{ title: string; back?: boolean }>()
defineEmits<{ (e: 'search'): void }>()

const router = useRouter()
const store = useRefreshStore()

const now = ref(Date.now())
let timer: number | null = null
onMounted(() => { timer = window.setInterval(() => { now.value = Date.now() }, 1000) })
onBeforeUnmount(() => { if (timer != null) window.clearInterval(timer) })

const shortTime = computed(() => {
  const ms = store.localTimeMs
  if (ms == null) return ''
  const d = new Date(ms)
  const p = (n: number) => (n < 10 ? '0' + n : '' + n)
  return `${p(d.getHours())}:${p(d.getMinutes())}`
})
const isStale = computed(() => store.localTimeMs != null && now.value - store.localTimeMs > 60_000)

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/dashboard')
}
</script>

<style scoped>
.m-header {
  height: calc(var(--mobile-header-height) + env(safe-area-inset-top));
  padding-top: env(safe-area-inset-top);
  padding-left: 8px;
  padding-right: 8px;
  background: var(--surface);
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  position: relative;
  z-index: 20;
}
.mh-left, .mh-right { display: flex; align-items: center; gap: 2px; min-width: 0; }
.mh-title { font-size: 17px; font-weight: 600; color: var(--text); padding-left: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mh-btn {
  width: 40px; height: 40px;
  border: 0; background: transparent; color: var(--text-2);
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 10px; cursor: pointer;
}
.mh-btn:active { background: var(--surface-hover); }
.mh-btn:disabled { opacity: 0.5; }
.mh-time { font-size: 11px; color: var(--text-4); }
.mh-time.stale { color: var(--warn); }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
