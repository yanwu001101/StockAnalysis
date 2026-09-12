<template>
  <nav class="tab-bar">
    <router-link
      v-for="item in items"
      :key="item.path"
      :to="item.path"
      class="tab-item"
      :class="{ active: isActive(item.path) }"
    >
      <span class="tab-ico">
        <el-icon :size="21"><component :is="item.icon" /></el-icon>
      </span>
      <span class="tab-label">{{ item.label }}</span>
    </router-link>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

// 底栏条目来自路由表，和桌面侧栏同源：非 hidden 的一级子路由。
const items = computed(() => {
  const main = router.options.routes.find(r => r.path === '/')
  return (main?.children || [])
    .filter(r => r.component && !r.meta?.hidden)
    .map(r => ({
      path: '/' + r.path,
      label: String(r.meta?.mobileTitle || r.meta?.title || ''),
      icon: String(r.meta?.mobileIcon || r.meta?.icon || 'Menu'),
    }))
})

function isActive(path: string) {
  return route.path === path || route.path.startsWith(path + '/')
}
</script>

<style scoped>
.tab-bar {
  position: fixed;
  left: 0; right: 0; bottom: 0;
  height: calc(var(--tabbar-height) + env(safe-area-inset-bottom));
  padding-bottom: env(safe-area-inset-bottom);
  background: var(--surface);
  border-top: 1px solid var(--line);
  display: flex;
  z-index: 30;
}
.tab-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  text-decoration: none;
  color: var(--text-3);
  font-size: 11px;
  -webkit-tap-highlight-color: transparent;
  min-height: 44px;
}
/* 色调式激活态：tint pill + 颜色 + 字重，灰度下也可读 */
.tab-ico {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 27px;
  border-radius: 14px;
  transition: background 0.18s ease;
}
.tab-item.active { color: var(--brand); font-weight: 600; }
.tab-item.active .tab-ico { background: var(--brand-soft); }
.tab-label { line-height: 1; }
</style>
