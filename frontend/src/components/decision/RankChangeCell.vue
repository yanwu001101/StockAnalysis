<template>
  <el-popover v-if="change && !change.new && change.rank_delta != null" placement="bottom" :width="300" trigger="click">
    <template #reference>
      <button type="button" class="rc-btn" :class="cls" @click.stop>
        <span class="num">{{ arrow }}{{ Math.abs(change.rank_delta) || '' }}</span>
        <span v-if="!change.rank_delta" class="rc-flat">持平</span>
      </button>
    </template>
    <div class="rc-pop" @click.stop>
      <div class="rc-head">
        排名 <b class="num">{{ change.prev_rank }}</b> → <b class="num">{{ rank }}</b>
        <span class="rc-sep">·</span>
        综合分 <b class="num">{{ fmt(change.composite_prev) }}</b> → <b class="num">{{ fmt(compositeNow) }}</b>
        <span class="num" :class="signCls(change.composite_delta)">({{ signed(change.composite_delta) }})</span>
      </div>
      <div class="rc-sub">相对上一快照 {{ prevSlot || '' }}。各因子组对综合分的贡献变化(合计 = 综合分变化):</div>
      <ul class="rc-groups">
        <li v-for="g in change.group_deltas || []" :key="g.group">
          <span class="rc-g">{{ g.label }}</span>
          <span class="rc-bar"><i :style="barStyle(g.delta)" /></span>
          <span class="num rc-d" :class="signCls(g.delta)">{{ signed(g.delta) }}</span>
          <span class="rc-now num">{{ g.prev != null ? Math.round(g.prev) : '—' }}→{{ g.now != null ? Math.round(g.now) : '—' }}</span>
        </li>
      </ul>
      <div v-if="change.price_delta_pct != null" class="rc-line">
        行情:{{ change.price_prev }} → {{ price }}(<span :class="signCls(change.price_delta_pct)">{{ signed(change.price_delta_pct) }}%</span>)
      </div>
      <div v-for="f in change.flags || []" :key="f" class="rc-flag">{{ f }}</div>
      <div v-if="!(change.reasons || []).length && !(change.flags || []).length" class="rc-line muted">
        因子组分均无变化;若排名变动,来自其他股票的变化(相对排名)。
      </div>
    </div>
  </el-popover>
  <span v-else-if="change && change.new" class="rc-new">新进</span>
  <span v-else class="rc-none">—</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RankChange } from '@/api/decision'

// "排名为什么变":点开即见 趋势 +3.1 / 量价 −2.0 / 板块 +4.2 的贡献拆解,
// 以及行情变化与口径变化(日K更新)标记。数据全部来自服务端 change 字段。
const props = defineProps<{
  change: RankChange | null | undefined
  rank?: number
  compositeNow?: number
  price?: number | null
  prevSlot?: string | null
}>()

const arrow = computed(() => (props.change?.rank_delta || 0) > 0 ? '▲' : (props.change?.rank_delta || 0) < 0 ? '▼' : '')
const cls = computed(() => (props.change?.rank_delta || 0) > 0 ? 'up' : (props.change?.rank_delta || 0) < 0 ? 'down' : 'flat')

function fmt(v?: number | null) { return v == null ? '—' : v.toFixed(1) }
function signed(v?: number | null) { return v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(1) }
function signCls(v?: number | null) { return !v ? '' : v > 0 ? 'price-up' : 'price-down' }
function barStyle(d: number) {
  const w = Math.min(100, Math.abs(d) * 12)
  return { width: `${w}%`, background: d >= 0 ? 'var(--up)' : 'var(--down)' }
}
</script>

<style scoped>
.rc-btn {
  border: 0; background: transparent; cursor: pointer; padding: 0 4px; font: inherit;
  font-weight: 600; border-radius: var(--radius-sm); line-height: 1.6;
}
.rc-btn.up { color: var(--up); background: var(--up-soft); }
.rc-btn.down { color: var(--down); background: var(--down-soft); }
.rc-btn.flat { color: var(--text-3); }
.rc-flat { font-weight: 400; font-size: 12px; }
.rc-new { color: var(--brand); font-size: 12px; }
.rc-none { color: var(--text-4); }
.rc-pop { font-size: 12px; color: var(--text-2); }
.rc-head { color: var(--text); font-size: 13px; margin-bottom: 4px; }
.rc-sep { margin: 0 6px; color: var(--text-4); }
.rc-sub { color: var(--text-3); margin-bottom: 6px; line-height: 1.5; }
.rc-groups { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; }
.rc-groups li { display: grid; grid-template-columns: 58px 1fr 44px 56px; align-items: center; gap: 6px; }
.rc-g { color: var(--text-2); }
.rc-bar { height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; }
.rc-bar i { display: block; height: 100%; }
.rc-d { text-align: right; }
.rc-now { color: var(--text-4); font-size: 11px; text-align: right; }
.rc-line { margin-top: 6px; }
.rc-flag { margin-top: 4px; color: var(--warn-text); }
.muted { color: var(--text-4); }
</style>
