/**
 * CommandPalette — Ctrl/⌘+K 全局快捷命令。
 *
 * 三类条目：导航（跳转工作区）、自选股（跳转分析）、动态动作
 * （分析输入的代码/名称）。选择逻辑是纯函数 filterPaletteItems，
 * 键盘上下/回车/Esc 全支持。
 */
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import { useAnalysisStore } from '@/stores/useAnalysisStore'
import { filterPaletteItems, type PaletteItem } from '@/utils/selectors'

const workspace = useWorkspaceStore()
const analysis = useAnalysisStore()
const router = useRouter()
const { paletteOpen, paletteQuery, watchlist } = storeToRefs(workspace)

const inputEl = ref<HTMLInputElement | null>(null)
const activeIndex = ref<number>(0)

const items = computed<PaletteItem[]>(() => {
  const base: PaletteItem[] = [
    { id: 'nav-cockpit', label: '驾驶舱', hint: '宏观数据 · 智能体状态 · 预警', group: 'navigation', target: '/command-center' },
    { id: 'nav-analysis', label: '智能分析', hint: '多智能体分析工作台', group: 'navigation', target: '/analysis' },
    { id: 'nav-backtest', label: '回测实验室', hint: '策略配置 · 资金曲线 · 归因', group: 'navigation', target: '/backtest' },
    { id: 'nav-watchlist', label: '雷达监控', hint: '自选股 · AI 异动日志', group: 'navigation', target: '/watchlist' },
  ]
  for (const entry of watchlist.value) {
    base.push({
      id: `watch-${entry.symbol}`,
      label: entry.symbol,
      hint: entry.lastSignal ? `自选 · AI 评分 ${entry.lastScore ?? '-'}` : '自选股',
      group: 'watchlist',
      target: `/analysis/${entry.symbol}`,
    })
  }
  const query = paletteQuery.value.trim()
  if (query.length > 0) {
    base.push({
      id: 'action-analyze',
      label: `分析「${query}」`,
      hint: '提交给多智能体流水线',
      group: 'action',
      target: `analyze:${query}`,
    })
    base.push({
      id: 'action-watch',
      label: `加入自选「${query}」`,
      hint: '加入雷达监控列表',
      group: 'action',
      target: `watch:${query}`,
    })
  }
  return base
})

const filtered = computed<PaletteItem[]>(() =>
  filterPaletteItems(paletteQuery.value, items.value),
)

watch(filtered, () => {
  activeIndex.value = 0
})

watch(paletteOpen, (open) => {
  if (open) {
    void nextTick(() => inputEl.value?.focus())
  }
})

function onKeydown(event: KeyboardEvent): void {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    if (paletteOpen.value) workspace.closePalette()
    else workspace.openPalette()
    return
  }
  if (!paletteOpen.value) return
  if (event.key === 'Escape') {
    workspace.closePalette()
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, filtered.value.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const item = filtered.value[activeIndex.value]
    if (item) void execute(item)
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

async function execute(item: PaletteItem): Promise<void> {
  workspace.closePalette()
  if (item.target.startsWith('analyze:')) {
    const raw = item.target.slice('analyze:'.length).replace(/\D/g, '')
    if (raw.length < 6) return
    const symbol = raw.padStart(6, '0').slice(-6)
    await router.push(`/analysis/${symbol}`)
    await analysis.submit(symbol)
    return
  }
  if (item.target.startsWith('watch:')) {
    const raw = item.target.slice('watch:'.length).replace(/\D/g, '')
    if (raw.length < 6) return
    workspace.addToWatchlist(raw.padStart(6, '0').slice(-6))
    await router.push('/watchlist')
    return
  }
  await router.push(item.target)
}
</script>

<template>
  <div v-if="paletteOpen" class="overlay" @click.self="workspace.closePalette()">
    <div class="palette" role="dialog" aria-label="命令面板">
      <input
        ref="inputEl"
        v-model="paletteQuery"
        class="palette-input"
        type="text"
        placeholder="搜索股票、跳转工作区，或输入 6 位代码进行分析…"
        autocomplete="off"
      />
      <ul v-if="filtered.length > 0" class="palette-list">
        <li
          v-for="(item, index) in filtered"
          :key="item.id"
          :class="{ active: index === activeIndex }"
          @mouseenter="activeIndex = index"
          @click="execute(item)"
        >
          <span class="group-tag" :class="`group-${item.group}`">
            {{ item.group === 'navigation' ? '导航' : item.group === 'watchlist' ? '自选' : '动作' }}
          </span>
          <span class="item-label num">{{ item.label }}</span>
          <span class="item-hint">{{ item.hint }}</span>
        </li>
      </ul>
      <p v-else class="palette-empty">没有匹配项。输入 6 位股票代码可直接发起分析。</p>
      <footer class="palette-foot">
        <span>↑↓ 选择</span><span>↵ 执行</span><span>Esc 关闭</span>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(4, 6, 10, 0.66);
  display: grid;
  place-items: start center;
  padding-top: 14vh;
  z-index: 100;
}

.palette {
  width: min(560px, 92vw);
  background: var(--bg-elevated);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.palette-input {
  width: 100%;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-primary);
  font-size: 15px;
  padding: var(--space-3) var(--space-4);
  outline: none;
}

.palette-input::placeholder {
  color: var(--text-muted);
}

.palette-list {
  list-style: none;
  margin: 0;
  padding: var(--space-1);
  max-height: 46vh;
  overflow-y: auto;
}

.palette-list li {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.palette-list li.active {
  background: var(--accent-soft);
}

.group-tag {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  border: 1px solid var(--border-strong);
  color: var(--text-secondary);
  flex: none;
}

.group-watchlist {
  color: var(--verdict-yellow);
  border-color: var(--verdict-yellow);
}

.group-action {
  color: var(--accent);
  border-color: var(--accent);
}

.item-label {
  font-size: 13px;
  color: var(--text-primary);
}

.item-hint {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.palette-empty {
  margin: 0;
  padding: var(--space-4);
  color: var(--text-muted);
  font-size: 12px;
}

.palette-foot {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-2) var(--space-4);
  border-top: 1px solid var(--border-subtle);
  font-size: 11px;
  color: var(--text-muted);
}
</style>
