<template>
  <span v-if="signal === undefined" class="pro-loading">···</span>
  <span v-else-if="!signal" class="pro-na">—</span>
  <span
    v-else
    class="pro-pill"
    :class="signal.direction"
    :title="signal.keySignals?.[0] || ''"
    @click.stop="go"
  >
    {{ signal.label }}
    <span class="pro-prob">{{ signal.probabilityUp }}%</span>
  </span>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { stockPath } from '@/utils/score'

export interface ProSignalBrief {
  direction: 'up' | 'down' | 'flat' | string
  label: string
  probabilityUp: number
  keySignals?: string[]
}

// undefined = 加载中，null = 无数据；点击进入详情页的"专业预测"
const props = defineProps<{ signal?: ProSignalBrief | null; code?: string }>()
const router = useRouter()

function go() {
  if (props.code) router.push({ path: stockPath(props.code), query: { tab: 'predict' } })
}
</script>

<style scoped>
.pro-loading { color: var(--text-4); font-size: 14px; letter-spacing: 1px; }
.pro-na { color: var(--text-4); }
.pro-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  cursor: pointer;
  white-space: nowrap;
  transition: transform 0.15s, box-shadow 0.15s;
}
.pro-pill:hover { transform: translateY(-1px); box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
.pro-pill.up { background: var(--up-soft); color: var(--up); }
.pro-pill.down { background: var(--down-soft); color: var(--down); }
.pro-pill.flat { background: var(--surface-2); color: var(--text-3); }
.pro-prob { font-variant-numeric: tabular-nums; opacity: 0.8; font-size: 11px; }
</style>
