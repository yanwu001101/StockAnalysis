<template>
  <div class="app-layout">
    <Sidebar :collapsed="sidebarCollapsed" @toggle="sidebarCollapsed = !sidebarCollapsed" />
    <div class="main-area" :class="{ collapsed: sidebarCollapsed }">
      <Header @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed" />
      <RefreshBar v-if="refreshStore.reloader" />
      <main class="content-area">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <keep-alive>
              <component :is="Component" />
            </keep-alive>
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import Sidebar from './Sidebar.vue'
import Header from './Header.vue'
import RefreshBar from './RefreshBar.vue'
import { useRefreshStore } from '@/stores/refresh'

const sidebarCollapsed = ref(false)
const refreshStore = useRefreshStore()
</script>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  background: var(--bg);
  overflow: hidden;
}
.main-area {
  flex: 1;
  margin-left: var(--sidebar-width);
  transition: margin-left 0.25s ease;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.main-area.collapsed { margin-left: var(--sidebar-collapsed-width); }
.content-area {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--bg);
}
.page-enter-active, .page-leave-active { transition: opacity 0.2s, transform 0.2s; }
.page-enter-from { opacity: 0; transform: translateY(4px); }
.page-leave-to { opacity: 0; }
</style>
