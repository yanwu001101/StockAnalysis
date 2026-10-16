/**
 * GlobalShell — 单页应用框架：图标导航 + 顶栏 + 内容区 + 命令面板。
 *
 * 路由切换只替换内容区，全局框架（导航/顶栏/信息流/命令面板）保持不动，
 * 避免传统后台的页面跳转割裂感。
 */
<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import IconRail from '@/components/IconRail.vue'
import TopBar from '@/components/TopBar.vue'
import CommandPalette from '@/components/CommandPalette.vue'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'

const workspace = useWorkspaceStore()

onMounted(() => workspace.startPolling())
onBeforeUnmount(() => workspace.stopPolling())
</script>

<template>
  <div class="shell">
    <IconRail />
    <div class="shell-main">
      <TopBar />
      <main class="shell-content">
        <RouterView v-slot="{ Component }">
          <KeepAlive :include="['AnalysisWorkspace']">
            <component :is="Component" />
          </KeepAlive>
        </RouterView>
      </main>
    </div>
    <CommandPalette />
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.shell-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.shell-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: var(--space-3);
}
</style>
