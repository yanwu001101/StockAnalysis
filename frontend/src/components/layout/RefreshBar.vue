<template>
  <div class="refresh-bar">
    <div class="left">
      <el-icon :size="14" class="bar-icon" :class="{ spinning: store.isRefreshing }"><Refresh /></el-icon>
      <span class="bar-label">{{ store.label || '当前页' }}</span>
      <span class="bar-sep">·</span>
      <el-tooltip :content="fullLocal" placement="bottom" :show-after="200">
        <span class="bar-time">
          <span class="bar-time-tag">上次刷新</span>
          <span class="bar-time-val" :class="{ stale: isStale }">{{ shortLocal }}</span>
        </span>
      </el-tooltip>
      <el-tooltip :content="fullData" placement="bottom" :show-after="200">
        <span class="bar-time">
          <span class="bar-time-tag">数据时间</span>
          <span class="bar-time-val" :class="{ stale: isDataStale }">{{ shortData }}</span>
        </span>
      </el-tooltip>
    </div>
    <div class="right">
      <button class="ghost-btn" :disabled="store.isRefreshing || !store.reloader" @click="handleClick">
        <el-icon :size="14" :class="{ spinning: store.isRefreshing }"><Refresh /></el-icon>
        <span>{{ store.isRefreshing ? '刷新中' : '刷新' }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useRefreshStore } from '@/stores/refresh'

const store = useRefreshStore()

const now = ref(Date.now())
let tickTimer: number | null = null
onMounted(() => {
  tickTimer = window.setInterval(() => { now.value = Date.now() }, 1000)
})
onBeforeUnmount(() => {
  if (tickTimer != null) window.clearInterval(tickTimer)
})

function pad(n: number) { return n < 10 ? '0' + n : '' + n }
function fmtHMS(ms: number | null) {
  if (ms == null) return '—'
  const d = new Date(ms)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
function fmtFull(ms: number | null) {
  if (ms == null) return '尚无数据'
  const d = new Date(ms)
  const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  return `${date} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

const shortLocal = computed(() => fmtHMS(store.localTimeMs))
const fullLocal  = computed(() => fmtFull(store.localTimeMs))
const shortData  = computed(() => fmtHMS(store.dataTimeMs))
const fullData   = computed(() => fmtFull(store.dataTimeMs))

// 超过 60 秒视为"陈旧"提醒用户
const isStale = computed(() => store.localTimeMs != null && now.value - store.localTimeMs > 60_000)
const isDataStale = computed(() => store.dataTimeMs != null && now.value - store.dataTimeMs > 60_000)

function handleClick() { store.invokeReloader() }
</script>

<style scoped>
.refresh-bar {
  height: 36px;
  background: var(--surface);
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  gap: 16px;
  font-size: 12.5px;
  color: var(--text-3);
  flex-shrink: 0;
}
.left { display: flex; align-items: center; gap: 12px; min-width: 0; }
.right { display: flex; align-items: center; gap: 8px; }

.bar-icon { color: var(--text-3); }
.bar-label { color: var(--text); font-weight: 500; }
.bar-sep { color: var(--line-strong); }

.bar-time { display: inline-flex; align-items: center; gap: 6px; }
.bar-time-tag { color: var(--text-3); }
.bar-time-val {
  color: var(--text);
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
}
.bar-time-val.stale { color: var(--down, #d24042); }

.ghost-btn {
  border: 0;
  background: transparent;
  color: var(--text);
  height: 26px;
  padding: 0 10px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12.5px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.ghost-btn:hover:not(:disabled) { background: var(--surface-hover); }
.ghost-btn:disabled { opacity: 0.5; cursor: wait; }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
  .bar-sep { display: none; }
  .bar-label { display: none; }
  .refresh-bar { padding: 0 12px; gap: 8px; }
}
</style>
