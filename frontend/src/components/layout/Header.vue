<template>
  <header class="app-header">
    <div class="left">
      <button class="ghost-btn" @click="$emit('toggle-sidebar')" aria-label="toggle">
        <el-icon :size="18"><Fold /></el-icon>
      </button>

      <el-autocomplete
        v-model="searchText"
        :fetch-suggestions="querySearch"
        placeholder="搜索股票代码或名称"
        class="search-input"
        @select="handleSelect"
        clearable
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-autocomplete>
    </div>

    <div class="right">
      <div class="market-pill" v-if="marketStore.summary">
        <span class="pill-item">
          <span class="pill-dot up"></span>
          <span class="pill-label">涨</span>
          <span class="pill-val num">{{ marketStore.summary.upCount }}</span>
        </span>
        <span class="pill-sep"></span>
        <span class="pill-item">
          <span class="pill-dot down"></span>
          <span class="pill-label">跌</span>
          <span class="pill-val num">{{ marketStore.summary.downCount }}</span>
        </span>
        <span class="pill-sep"></span>
        <span class="pill-item">
          <span class="pill-label">北向</span>
          <span class="pill-val num" :class="marketStore.summary.northboundFlow >= 0 ? 'price-up' : 'price-down'">
            {{ formatFlow(marketStore.summary.northboundFlow) }}
          </span>
        </span>
      </div>

      <el-tooltip content="刷新市场概览" placement="bottom">
        <button class="ghost-btn" :disabled="refreshing" @click="refreshData">
          <el-icon :size="16" :class="{ spinning: refreshing }"><Refresh /></el-icon>
        </button>
      </el-tooltip>

      <el-dropdown trigger="click" v-if="userStore.isLoggedIn">
        <div class="user-chip">
          <div class="avatar">{{ userStore.userInfo?.nickname?.[0] || 'U' }}</div>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="$router.push('/settings')">
              <el-icon><Setting /></el-icon>设置
            </el-dropdown-item>
            <el-dropdown-item divided @click="handleLogout">
              <el-icon><SwitchButton /></el-icon>退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button v-else type="primary" size="small" @click="$router.push('/login')">登录</el-button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMarketStore } from '@/stores/market'
import { useUserStore } from '@/stores/user'
import { searchStock } from '@/api/stock'

defineEmits(['toggle-sidebar'])

const router = useRouter()
const marketStore = useMarketStore()
const userStore = useUserStore()

const searchText = ref('')
const refreshing = ref(false)

async function querySearch(query: string, cb: Function) {
  if (!query || query.length < 1) { cb([]); return }
  try {
    const results = await searchStock(query)
    cb(results.map((r: any) => ({ value: `${r.code} ${r.name}`, code: r.code })))
  } catch { cb([]) }
}

function handleSelect(item: any) {
  if (item.code) { router.push(`/stock/${item.code}`); searchText.value = '' }
}

async function refreshData() {
  refreshing.value = true
  try { await marketStore.fetchAll() } finally { refreshing.value = false }
}

function handleLogout() {
  userStore.logout()
  router.push('/login')
}

function formatFlow(val: number) {
  if (!val) return '--'
  return (val / 10000).toFixed(1) + '亿'
}
</script>

<style scoped>
.app-header {
  height: var(--header-height);
  background: var(--bg);
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  gap: 16px;
  flex-shrink: 0;
}
.left { display: flex; align-items: center; gap: 12px; flex: 1; min-width: 0; }
.search-input { width: 320px; max-width: 100%; }

.right { display: flex; align-items: center; gap: 12px; }

.market-pill {
  display: flex; align-items: center; gap: 12px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-pill);
  padding: 6px 14px;
  font-size: 13px;
  color: var(--text-2);
}
.pill-item { display: flex; align-items: center; gap: 6px; }
.pill-dot {
  width: 6px; height: 6px; border-radius: 50%;
}
.pill-dot.up { background: var(--up); }
.pill-dot.down { background: var(--down); }
.pill-label { color: var(--text-3); font-size: 12px; }
.pill-val { font-weight: 600; }
.pill-sep {
  width: 1px; height: 12px;
  background: var(--line-strong);
}

.ghost-btn {
  border: 0;
  background: transparent;
  color: var(--text-3);
  width: 32px; height: 32px;
  border-radius: 8px;
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.ghost-btn:hover { color: var(--text); background: var(--surface-hover); }
.ghost-btn:disabled { opacity: 0.5; cursor: wait; }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.user-chip { cursor: pointer; }
.avatar {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: var(--brand);
  color: #FFFFFF;
  display: flex; align-items: center; justify-content: center;
  font-weight: 600;
  font-size: 13px;
}

@media (max-width: 900px) {
  .market-pill { display: none; }
  .search-input { width: 180px; }
}
</style>
