<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="brand">
      <div class="brand-mark">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="3 17 9 11 13 15 21 7"></polyline>
          <polyline points="14 7 21 7 21 14"></polyline>
        </svg>
      </div>
      <transition name="fade">
        <span v-if="!collapsed" class="brand-name">智能选股</span>
      </transition>
    </div>

    <nav class="nav">
      <router-link
        v-for="route in menuRoutes"
        :key="route.path"
        :to="'/' + route.path"
        class="nav-item"
        :class="{ active: currentRoute === '/' + route.path || currentRoute.startsWith('/' + route.path + '/') }"
      >
        <el-icon class="nav-icon" :size="18"><component :is="route.meta?.icon" /></el-icon>
        <transition name="fade"><span v-if="!collapsed" class="nav-label">{{ route.meta?.title }}</span></transition>
      </router-link>
    </nav>

    <div class="sidebar-footer">
      <button class="theme-btn" @click="cycleTheme" :title="`主题：${themeLabel}`">
        <el-icon :size="16">
          <component :is="themeIcon" />
        </el-icon>
        <transition name="fade">
          <span v-if="!collapsed" class="theme-label">{{ themeLabel }}</span>
        </transition>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Sunny, Moon, MagicStick } from '@element-plus/icons-vue'

defineProps<{ collapsed: boolean }>()
defineEmits(['toggle'])

const route = useRoute()
const router = useRouter()
const currentRoute = computed(() => route.path)

const menuRoutes = computed(() => {
  const mainRoute = router.options.routes.find(r => r.path === '/')
  return mainRoute?.children?.filter(r => !r.meta?.hidden) || []
})

type Theme = 'auto' | 'light' | 'dark'
const theme = ref<Theme>('auto')

function applyTheme(t: Theme) {
  const root = document.documentElement
  if (t === 'auto') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', t)
  localStorage.setItem('theme', t)
  theme.value = t
}
function cycleTheme() {
  const order: Theme[] = ['auto', 'light', 'dark']
  const next = order[(order.indexOf(theme.value) + 1) % order.length]
  applyTheme(next)
}
const themeLabel = computed(() =>
  theme.value === 'auto' ? '跟随系统' : theme.value === 'light' ? '浅色' : '深色'
)
const themeIcon = computed(() =>
  theme.value === 'auto' ? MagicStick : theme.value === 'light' ? Sunny : Moon
)

onMounted(() => {
  const saved = (localStorage.getItem('theme') as Theme) || 'auto'
  applyTheme(saved)
})
</script>

<style scoped>
.sidebar {
  position: fixed;
  left: 0; top: 0; bottom: 0;
  width: var(--sidebar-width);
  background: var(--bg-2);
  border-right: 1px solid var(--line);
  display: flex; flex-direction: column;
  z-index: 100;
  transition: width 0.25s ease;
  overflow: hidden;
}
.sidebar.collapsed { width: var(--sidebar-collapsed-width); }

.brand {
  height: var(--header-height);
  display: flex; align-items: center; gap: 10px;
  padding: 0 16px;
  flex-shrink: 0;
}
.brand-mark {
  width: 32px; height: 32px;
  border-radius: 8px;
  background: var(--brand);
  color: #FFFFFF;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.brand-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: -0.01em;
  white-space: nowrap;
}

.nav {
  flex: 1;
  padding: 8px 8px 16px;
  display: flex; flex-direction: column; gap: 2px;
  overflow-y: auto;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 40px;
  padding: 0 12px;
  border-radius: 8px;
  text-decoration: none;
  color: var(--text-2);
  font-size: 14px;
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}
.nav-item:hover {
  background: var(--surface-hover);
  color: var(--text);
}
.nav-item.active {
  background: var(--brand-soft);
  color: var(--brand);
  font-weight: 500;
}
.nav-icon { flex-shrink: 0; }
.nav-label { flex: 1; overflow: hidden; }

.sidebar-footer {
  padding: 8px 12px 14px;
  border-top: 1px solid var(--line);
}
.theme-btn {
  width: 100%;
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s ease, color 0.15s ease;
}
.theme-btn:hover { background: var(--surface-hover); color: var(--text); }
.theme-label { white-space: nowrap; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.18s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
