<template>
  <el-container class="layout">
    <el-aside class="sidebar" :width="collapsed ? '64px' : '220px'">
      <div class="brand">
        <el-icon :size="20" color="var(--brand)"><Setting /></el-icon>
        <span v-show="!collapsed">管理后台</span>
      </div>
      <el-menu
        :default-active="route.path"
        :collapse="collapsed"
        :unique-opened="true"
        router
        background-color="transparent"
        text-color="var(--text-2)"
        active-text-color="var(--brand)"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <template #title>仪表盘</template>
        </el-menu-item>
        <el-menu-item index="/users">
          <el-icon><User /></el-icon>
          <template #title>用户管理</template>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><Operation /></el-icon>
          <template #title>任务中心</template>
        </el-menu-item>
        <el-sub-menu index="configs">
          <template #title>
            <el-icon><Tools /></el-icon>
            <span>业务配置</span>
          </template>
          <el-menu-item index="/configs">通用配置</el-menu-item>
          <el-menu-item index="/configs/stock-list">股票名单</el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="monitor">
          <template #title>
            <el-icon><Monitor /></el-icon>
            <span>系统监控</span>
          </template>
          <el-menu-item index="/monitor/health">健康检查</el-menu-item>
          <el-menu-item index="/monitor/access-log">访问日志</el-menu-item>
          <el-menu-item index="/monitor/audit-log">审计日志</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-button text @click="collapsed = !collapsed">
            <el-icon :size="18"><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
          </el-button>
          <span class="page-title">{{ route.meta?.title || '管理后台' }}</span>
        </div>
        <div class="header-right">
          <el-dropdown @command="onCommand">
            <span class="user-trigger">
              <el-avatar :size="28" style="background:var(--brand)">
                {{ initial }}
              </el-avatar>
              <span class="username">{{ user.userInfo?.nickname || user.userInfo?.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  <small>{{ user.userInfo?.role }}</small>
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main">
        <router-view v-slot="{ Component }">
          <component :is="Component" v-if="user.isAdmin" />
          <el-empty v-else description="加载中..." />
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const user = useUserStore()
const route = useRoute()
const router = useRouter()
const collapsed = ref(false)

const initial = computed(() => {
  const n = user.userInfo?.nickname || user.userInfo?.username || 'A'
  return n.charAt(0).toUpperCase()
})

onMounted(async () => {
  if (!user.userInfo) await user.hydrate()
  if (!user.isAdmin) {
    user.logout()
    router.replace('/login')
  }
})

function onCommand(cmd: string) {
  if (cmd === 'logout') {
    user.logout()
    router.replace('/login')
  }
}
</script>

<style scoped>
.layout { height: 100vh; }

.sidebar {
  background: var(--surface);
  border-right: 1px solid var(--line);
  transition: width .2s;
  overflow: hidden;
}
.brand {
  height: 56px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 20px;
  font-weight: 600;
  color: var(--text);
  border-bottom: 1px solid var(--line);
}
:deep(.el-menu) { border-right: none; }

.header {
  height: 56px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header-left { display: flex; align-items: center; gap: 12px; }
.page-title { font-size: 15px; font-weight: 600; color: var(--text); }
.user-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: var(--text-2);
}
.username { font-size: 13px; }
.main {
  background: var(--bg);
  padding: 16px;
  overflow-y: auto;
}
</style>
