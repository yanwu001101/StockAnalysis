<template>
  <header class="app-header">
    <div class="left">
      <button class="ghost-btn" @click="$emit('toggle-sidebar')" aria-label="toggle">
        <el-icon :size="18"><Fold /></el-icon>
      </button>
      <StockSearch variant="inline" />
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
          <UserAvatar :name="userStore.userInfo?.nickname || userStore.userInfo?.username" :size="32" />
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
import StockSearch from '@/components/stock/StockSearch.vue'
import UserAvatar from '@/components/ui/UserAvatar.vue'

defineEmits(['toggle-sidebar'])

const router = useRouter()
const marketStore = useMarketStore()
const userStore = useUserStore()

const refreshing = ref(false)

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

.user-chip { cursor: pointer; display: flex; align-items: center; }

@media (max-width: 900px) {
  .market-pill { display: none; }
}
</style>
