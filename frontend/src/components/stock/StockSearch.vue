<template>
  <!-- 桌面顶栏：自动补全输入框 -->
  <el-autocomplete
    v-if="variant === 'inline'"
    v-model="keyword"
    :fetch-suggestions="fetchSuggestions"
    placeholder="搜索股票代码或名称"
    class="stock-search-inline"
    clearable
    @select="onSelect"
  >
    <template #prefix><el-icon><Search /></el-icon></template>
  </el-autocomplete>

  <!-- 手机：全屏搜索面板 -->
  <div v-else class="stock-search-panel">
    <div class="ssp-bar">
      <el-input
        ref="inputRef"
        v-model="keyword"
        placeholder="股票代码或名称"
        size="large"
        clearable
        @input="onInput"
        @keyup.enter="onEnter"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <button type="button" class="ssp-cancel" @click="closePanel">取消</button>
    </div>
    <div class="ssp-body">
      <div v-if="searching" class="ssp-hint">搜索中…</div>
      <div v-else-if="keyword && !results.length" class="ssp-hint">没有匹配的股票</div>
      <div v-else-if="!keyword" class="ssp-hint">输入代码或名称开始搜索</div>
      <div v-for="r in results" :key="r.code" class="ssp-item" @click="go(r.code)">
        <span class="ssp-name">{{ r.name }}</span>
        <span class="ssp-code mono">{{ padCode(r.code) }}</span>
        <span v-if="r.industry" class="ssp-ind">{{ r.industry }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { searchStock } from '@/api/stock'
import { padCode, stockPath } from '@/utils/score'

// 股票搜索：桌面头部内联自动补全 / 手机全屏面板，共用同一套请求逻辑。
const props = withDefaults(defineProps<{ variant?: 'inline' | 'panel' }>(), { variant: 'inline' })
const emit = defineEmits<{ (e: 'close'): void }>()

const router = useRouter()
const keyword = ref('')
const results = ref<any[]>([])
const searching = ref(false)
const inputRef = ref<{ focus: () => void }>()
let timer: number | undefined

// 手机全屏面板打开时锁定底层滚动（含 iOS）
function lockScroll(lock: boolean) {
  if (typeof document === 'undefined') return
  document.documentElement.style.overflow = lock ? 'hidden' : ''
  document.body.style.overflow = lock ? 'hidden' : ''
}

onMounted(() => {
  if (props.variant === 'panel') lockScroll(true)
  nextTick(() => inputRef.value?.focus())
})
onBeforeUnmount(() => lockScroll(false))

function closePanel() {
  lockScroll(false)
  emit('close')
}

async function fetchSuggestions(query: string, cb: (items: any[]) => void) {
  if (!query) { cb([]); return }
  try {
    const list = await searchStock(query)
    cb(list.map((r: any) => ({ value: `${padCode(r.code)} ${r.name}`, code: r.code })))
  } catch { cb([]) }
}

function onSelect(item: any) {
  if (item?.code) { go(item.code) }
}

function onInput() {
  if (timer) window.clearTimeout(timer)
  const q = keyword.value.trim()
  if (!q) { results.value = []; return }
  timer = window.setTimeout(async () => {
    searching.value = true
    try { results.value = await searchStock(q) } catch { results.value = [] } finally { searching.value = false }
  }, 250)
}

function onEnter() {
  const q = keyword.value.trim()
  if (/^\d{6}$/.test(q)) go(q)
  else if (results.value[0]) go(results.value[0].code)
}

function go(code: string) {
  keyword.value = ''
  results.value = []
  closePanel()
  router.push(stockPath(code))
}

onMounted(() => { nextTick(() => inputRef.value?.focus()) })
</script>

<style scoped>
.stock-search-inline { width: 320px; max-width: 100%; }

.stock-search-panel {
  position: fixed;
  inset: 0;
  z-index: 300;
  background: var(--bg);
  display: flex;
  flex-direction: column;
  padding-top: env(safe-area-inset-top);
}
.ssp-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px;
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}
.ssp-bar :deep(.el-input) { flex: 1; }
.ssp-cancel { border: 0; background: transparent; color: var(--brand); font-size: 15px; padding: 8px 4px; cursor: pointer; }
.ssp-body { flex: 1; overflow-y: auto; }
.ssp-hint { padding: 40px 16px; text-align: center; color: var(--text-4); font-size: 13px; }
.ssp-item {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 16px;
  background: var(--surface);
  border-bottom: 1px solid var(--line);
  min-height: 52px;
}
.ssp-item:active { background: var(--surface-hover); }
.ssp-name { font-size: 15px; font-weight: 500; color: var(--text); }
.ssp-code { font-size: 13px; color: var(--text-3); }
.ssp-ind { margin-left: auto; font-size: 12px; color: var(--text-4); }
@media (max-width: 900px) { .stock-search-inline { width: 180px; } }
</style>
