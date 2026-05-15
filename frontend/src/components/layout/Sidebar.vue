<template>
  <div class="sidebar" :class="{ collapsed }">
    <div class="sidebar-header">
      <div class="logo-area">
        <div class="logo-icon">
          <el-icon :size="28" color="#00D4FF"><TrendCharts /></el-icon>
        </div>
        <transition name="fade">
          <span v-if="!collapsed" class="logo-text">智能选股</span>
        </transition>
      </div>
    </div>

    <el-menu
      :default-active="currentRoute"
      :collapse="collapsed"
      class="sidebar-menu"
      background-color="transparent"
      text-color="#8892A4"
      active-text-color="#00D4FF"
      router
    >
      <template v-for="route in menuRoutes" :key="route.path">
        <el-menu-item :index="route.path">
          <el-icon><component :is="route.meta?.icon" /></el-icon>
          <template #title>{{ route.meta?.title }}</template>
        </el-menu-item>
      </template>
    </el-menu>

    <div class="sidebar-footer">
      <div class="version-info" v-if="!collapsed">
        <span class="version-tag">v1.0.0</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

defineProps<{ collapsed: boolean }>()
defineEmits(['toggle'])

const route = useRoute()
const router = useRouter()

const currentRoute = computed(() => route.path)

const menuRoutes = computed(() => {
  const mainRoute = router.options.routes.find(r => r.path === '/')
  return mainRoute?.children?.filter(r => !r.meta?.hidden) || []
})
</script>

<style scoped>
.sidebar {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  width: var(--sidebar-width);
  background: var(--bg-secondary);
  border-right: 1px solid var(--glass-border);
  display: flex;
  flex-direction: column;
  z-index: 100;
  transition: width 0.3s ease;
  overflow: hidden;
}
.sidebar.collapsed {
  width: var(--sidebar-collapsed-width);
}
.sidebar-header {
  height: var(--header-height);
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid var(--glass-border);
}
.logo-area {
  display: flex;
  align-items: center;
  gap: 10px;
  overflow: hidden;
  white-space: nowrap;
}
.logo-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 212, 255, 0.1);
  border-radius: 8px;
}
.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: var(--accent-cyan);
  text-shadow: 0 0 10px rgba(0, 212, 255, 0.3);
}
.sidebar-menu {
  flex: 1;
  border: none !important;
  padding: 8px;
}
.sidebar-menu .el-menu-item {
  border-radius: 8px;
  margin-bottom: 4px;
  height: 44px;
  line-height: 44px;
}
.sidebar-menu .el-menu-item:hover {
  background: rgba(0, 212, 255, 0.08) !important;
}
.sidebar-menu .el-menu-item.is-active {
  background: rgba(0, 212, 255, 0.12) !important;
  color: #00D4FF !important;
}
.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--glass-border);
}
.version-tag {
  font-size: 11px;
  color: var(--text-muted);
  background: rgba(0, 212, 255, 0.06);
  padding: 2px 8px;
  border-radius: 4px;
}
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
