/**
 * IconRail — 扁平化图标导航条（禁用传统菜单树）。
 *
 * 五个工作区入口 + 底部命令面板提示；悬停显示文字提示，
 * 当前路由高亮。图标为内联 SVG，不引图标库。
 */
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

interface RailItem {
  key: string
  label: string
  to: string
  icon: string
}

const items: RailItem[] = [
  { key: 'cockpit', label: '驾驶舱', to: '/command-center', icon: 'gauge' },
  { key: 'analysis', label: '智能分析', to: '/analysis', icon: 'chart' },
  { key: 'backtest', label: '回测实验室', to: '/backtest', icon: 'flask' },
  { key: 'watchlist', label: '雷达监控', to: '/watchlist', icon: 'radar' },
]

const route = useRoute()
const activeKey = computed<string>(() => {
  const path = route.path
  if (path.startsWith('/analysis')) return 'analysis'
  if (path.startsWith('/backtest')) return 'backtest'
  if (path.startsWith('/watchlist')) return 'watchlist'
  return 'cockpit'
})
</script>

<template>
  <nav class="rail" aria-label="工作区导航">
    <router-link
      v-for="item in items"
      :key="item.key"
      :to="item.to"
      class="rail-item"
      :class="{ active: activeKey === item.key }"
      :aria-current="activeKey === item.key ? 'page' : undefined"
    >
      <span class="rail-tip">{{ item.label }}</span>
      <!-- gauge -->
      <svg v-if="item.icon === 'gauge'" viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M3 14a8 8 0 1 1 14 0" />
        <path d="M10 14l3.5-4.5" />
        <circle cx="10" cy="14" r="1.2" fill="currentColor" stroke="none" />
      </svg>
      <!-- candlestick chart -->
      <svg v-else-if="item.icon === 'chart'" viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M6 3v3M6 12v5M14 2v4M14 11v6" />
        <rect x="4.5" y="6.5" width="3" height="5" fill="currentColor" stroke="none" />
        <rect x="12.5" y="6" width="3" height="5" fill="currentColor" stroke="none" />
      </svg>
      <!-- flask -->
      <svg v-else-if="item.icon === 'flask'" viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M7 3v5l-3 6a2 2 0 0 0 2 3h8a2 2 0 0 0 2-3l-3-6V3" />
        <path d="M6 3h8M6.5 13h7" />
      </svg>
      <!-- radar -->
      <svg v-else-if="item.icon === 'radar'" viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="10" cy="10" r="7.5" />
        <circle cx="10" cy="10" r="4" />
        <circle cx="10" cy="10" r="1" fill="currentColor" stroke="none" />
        <path d="M10 10l6-4" />
      </svg>
    </router-link>

    <div class="rail-spacer" />

    <div class="rail-item cmd" aria-label="命令面板">
      <span class="rail-tip">命令面板 Ctrl/⌘+K</span>
      <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="3" y="3" width="14" height="14" rx="3" />
        <path d="M7 8h6M7 12h4" />
      </svg>
    </div>
  </nav>
</template>

<style scoped>
.rail {
  width: var(--rail-width);
  flex: none;
  background: var(--bg-panel);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-2) 0;
  gap: var(--space-1);
}

.rail-item {
  position: relative;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  display: grid;
  place-items: center;
  color: var(--text-muted);
  text-decoration: none;
  transition: color 120ms ease, background 120ms ease;
}

.rail-item:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.rail-item.active {
  color: var(--accent);
  background: var(--accent-soft);
}

.rail-item.active::before {
  content: '';
  position: absolute;
  left: -8px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: var(--accent);
  border-radius: 1px;
}

.rail-tip {
  position: absolute;
  left: calc(100% + 8px);
  top: 50%;
  transform: translateY(-50%);
  background: var(--bg-elevated);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 12px;
  padding: 2px 8px;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 120ms ease;
  z-index: 50;
}

.rail-item:hover .rail-tip {
  opacity: 1;
}

.rail-spacer {
  flex: 1;
}

.cmd {
  cursor: pointer;
}
</style>
