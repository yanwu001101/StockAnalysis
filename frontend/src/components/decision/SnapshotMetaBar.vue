<template>
  <div class="snap-meta" :class="{ stale }">
    <template v-if="snapshot">
      <span class="sm-item"><span class="sm-k">本次计算</span><b class="num">{{ fmt(snapshot.computed_at) }}</b></span>
      <span class="sm-item"><span class="sm-k">行情时间</span><b class="num">{{ snapshot.quote_time ? fmt(snapshot.quote_time) : '—' }}</b></span>
      <span class="sm-item"><span class="sm-k">数据源</span><b>{{ snapshot.quote_source || '—' }}</b></span>
      <span v-if="klineDate" class="sm-item"><span class="sm-k">因子日K截止</span><b class="num">{{ klineDate }}</b></span>
      <span class="sm-item"><span class="sm-k">快照</span><b class="mono">{{ snapshot.snapshot_id }}</b><span v-if="prev" class="sm-prev">上一 {{ prev.slot }}</span></span>
      <span class="sm-item"><span class="sm-k">宇宙</span><b class="num">{{ snapshot.scored_n }}</b><span class="sm-k">/{{ snapshot.universe_n }} 只</span></span>
      <span v-if="stale" class="sm-warn">快照已超过 {{ staleMinutes }} 分钟,盘中请等待下一快照(每 15 分钟)</span>
      <span v-if="note" class="sm-warn">{{ note }}</span>
    </template>
    <template v-else>
      <span class="sm-warn">{{ note || '尚无排名快照' }}</span>
    </template>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SnapshotHeader } from '@/api/decision'

// 快照元信息条:让用户一眼看到"这组数字是什么时候、用什么行情、哪个数据源算出来的"。
// 同一快照 id 下的数据不会变;变化只会在快照 id 变化时出现。
const props = defineProps<{
  snapshot: SnapshotHeader | null | undefined
  prev?: SnapshotHeader | null
  klineDate?: string | null
  note?: string | null
}>()

function fmt(s: string) {
  // "2026-09-16 10:30:05" → "09-16 10:30:05"
  return s.length >= 16 ? s.slice(5) : s
}

const staleMinutes = computed(() => {
  if (!props.snapshot?.computed_at) return 0
  const t = new Date(props.snapshot.computed_at.replace(' ', 'T')).getTime()
  return Math.floor((Date.now() - t) / 60000)
})
// 交易时段内超过 30 分钟没有新快照说明任务没跑;非交易时段最后一个快照本来就会"旧",不提示。
const stale = computed(() => {
  const h = new Date().getHours(), m = new Date().getMinutes(), hm = h * 60 + m
  const trading = (hm >= 9 * 60 + 40 && hm <= 11 * 60 + 35) || (hm >= 13 * 60 + 5 && hm <= 15 * 60 + 10)
  return trading && staleMinutes.value > 30
})
</script>

<style scoped>
.snap-meta {
  display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: center;
  font-size: 12px; color: var(--text-3); padding: 8px 12px;
  background: var(--surface-2); border-radius: var(--radius);
}
.sm-item { display: inline-flex; align-items: baseline; gap: 5px; white-space: nowrap; }
.sm-k { color: var(--text-4); }
.sm-item b { color: var(--text); font-weight: 600; }
.sm-prev { color: var(--text-4); margin-left: 4px; }
.sm-warn { color: var(--warn-text); }
.snap-meta.stale { outline: 1px solid var(--warn); }
@media (max-width: 768px) {
  .snap-meta { gap: 4px 12px; padding: 8px 10px; }
}
</style>
