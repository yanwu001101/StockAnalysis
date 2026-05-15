<template>
  <div class="app-header">
    <div class="header-left">
      <el-button class="collapse-btn" text @click="$emit('toggle-sidebar')">
        <el-icon :size="20"><Fold /></el-icon>
      </el-button>

      <el-autocomplete
        v-model="searchText"
        :fetch-suggestions="querySearch"
        placeholder="搜索股票代码或名称..."
        class="search-input"
        @select="handleSelect"
        clearable
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-autocomplete>
    </div>

    <div class="header-right">
      <div class="market-indicator" v-if="marketStore.summary">
        <span class="indicator-item">
          <span class="label">涨</span>
          <span class="value price-up">{{ marketStore.summary.upCount }}</span>
        </span>
        <span class="indicator-item">
          <span class="label">跌</span>
          <span class="value price-down">{{ marketStore.summary.downCount }}</span>
        </span>
        <span class="indicator-item">
          <span class="label">北向</span>
          <span class="value" :class="marketStore.summary.northboundFlow >= 0 ? 'price-up' : 'price-down'">
            {{ formatFlow(marketStore.summary.northboundFlow) }}
          </span>
        </span>
      </div>

      <el-tooltip content="刷新数据" placement="bottom">
        <el-button class="action-btn" text :loading="refreshing" @click="refreshData">
          <el-icon :size="18"><Refresh /></el-icon>
        </el-button>
      </el-tooltip>

      <el-dropdown trigger="click" v-if="userStore.isLoggedIn">
        <div class="user-avatar">
          <el-avatar :size="32" :src="userStore.userInfo?.avatar">
            {{ userStore.userInfo?.nickname?.[0] || 'U' }}
          </el-avatar>
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
  </div>
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
  if (!query || query.length < 1) {
    cb([])
    return
  }
  try {
    const results = await searchStock(query)
    cb(results.map((r: any) => ({
      value: `${r.code} ${r.name}`,
      code: r.code,
    })))
  } catch {
    cb([])
  }
}

function handleSelect(item: any) {
  if (item.code) {
    router.push(`/stock/${item.code}`)
    searchText.value = ''
  }
}

async function refreshData() {
  refreshing.value = true
  try {
    await marketStore.fetchAll()
  } finally {
    refreshing.value = false
  }
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
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--glass-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.collapse-btn {
  color: var(--text-secondary);
}
.collapse-btn:hover {
  color: var(--accent-cyan);
}
.search-input {
  width: 320px;
}
.search-input :deep(.el-input__wrapper) {
  background: var(--bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: 8px;
  box-shadow: none;
}
.search-input :deep(.el-input__wrapper:hover),
.search-input :deep(.el-input__wrapper.is-focus) {
  border-color: var(--accent-cyan-dim);
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.market-indicator {
  display: flex;
  gap: 16px;
  font-size: 13px;
}
.indicator-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.indicator-item .label {
  color: var(--text-muted);
}
.indicator-item .value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.action-btn {
  color: var(--text-secondary);
}
.action-btn:hover {
  color: var(--accent-cyan);
}
.user-avatar {
  cursor: pointer;
  display: flex;
  align-items: center;
}
</style>
