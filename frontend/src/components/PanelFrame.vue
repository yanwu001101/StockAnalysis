/**
 * PanelFrame — every workspace panel is wrapped in this collapsible frame.
 *
 * 专业终端惯例：面板右上角始终有折叠/展开按钮；折叠后只留标题栏，
 * 工作区布局不塌陷。折叠状态由 workspace store 按 panel id 持久化。
 */
<script setup lang="ts">
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'

const props = defineProps<{
  /** 稳定标识，用于记住折叠状态 */
  id: string
  title: string
  /** 标题右侧的附加信息（如代码、计数） */
  meta?: string
  /** 默认折叠 */
  defaultCollapsed?: boolean
}>()

const workspace = useWorkspaceStore()

// defaultCollapsed 只在首次访问时生效（store 里没有记录时才写入）
if (props.defaultCollapsed === true && workspace.collapsedPanels[props.id] === undefined) {
  workspace.togglePanel(props.id)
}
</script>

<template>
  <section class="panel" :class="{ collapsed: workspace.isCollapsed(id) }">
    <header class="panel-head">
      <h2 class="panel-title">{{ title }}</h2>
      <span v-if="meta" class="panel-meta num">{{ meta }}</span>
      <button
        class="collapse-btn"
        type="button"
        :aria-expanded="!workspace.isCollapsed(id)"
        :title="workspace.isCollapsed(id) ? '展开面板' : '折叠面板'"
        @click="workspace.togglePanel(id)"
      >
        {{ workspace.isCollapsed(id) ? '＋' : '－' }}
      </button>
    </header>
    <div v-show="!workspace.isCollapsed(id)" class="panel-body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.panel {
  background: var(--bg-panel);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-subtle);
  flex: none;
}

.panel.collapsed .panel-head {
  border-bottom: none;
}

.panel-title {
  margin: 0;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.06em;
  color: var(--text-secondary);
  text-transform: uppercase;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.panel-meta {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
}

.collapse-btn {
  margin-left: var(--space-2);
  width: 20px;
  height: 20px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  flex: none;
  display: grid;
  place-items: center;
}

.collapse-btn:hover {
  color: var(--text-primary);
  border-color: var(--border-strong);
}

.panel-body {
  padding: var(--space-3);
  overflow: auto;
  min-height: 0;
}
</style>
