<template>
  <article class="pc" :class="[`state-${entry.buy_state}`, { hero }]">
    <header class="pc-head">
      <div class="pc-rank">{{ rankLabel }}</div>
      <div class="pc-title">
        <router-link class="pc-name" :to="stockPath(entry.code)">{{ entry.name }}</router-link>
        <span class="pc-code mono">{{ entry.code }}</span>
        <span v-if="entry.industry" class="pc-ind">{{ entry.industry }}</span>
        <el-tag v-if="entry.held" size="small" effect="plain" type="info">已持有</el-tag>
      </div>
      <div class="pc-score">
        <span class="pc-score-k">综合决策分</span>
        <b class="num">{{ entry.decision.toFixed(0) }}</b>
      </div>
    </header>

    <div class="pc-state-row">
      <el-tag :type="BUY_STATE_TYPE[entry.buy_state]" effect="dark" size="large" class="pc-state">{{ entry.buy_label }}</el-tag>
      <span v-if="entry.state_note" class="pc-state-note">{{ entry.state_note }}</span>
      <RankChangeCell :change="entry.change" :rank="entry.rank" :composite-now="entry.composite" :price="entry.price" :prev-slot="prevSlot" class="pc-change" />
    </div>

    <div class="pc-prices">
      <div class="pc-p">
        <span class="pc-k">{{ zoneLabel }}</span>
        <b class="num" :class="zoneCls">{{ zoneText }}</b>
      </div>
      <div class="pc-p">
        <span class="pc-k">当前价格</span>
        <b class="num">{{ entry.price ?? '—' }}</b>
        <ChangeText :value="entry.pct_change" class="pc-chg" />
      </div>
      <div class="pc-p">
        <span class="pc-k">失效位</span>
        <b class="num warn">{{ entry.invalid_level ?? '—' }}</b>
      </div>
      <div class="pc-p">
        <span class="pc-k">风险</span>
        <b :class="`risk-${entry.risk_level}`">{{ entry.risk_level }}</b>
        <span class="pc-k num">({{ entry.risk.toFixed(0) }})</span>
      </div>
    </div>

    <div class="pc-metrics">
      <div class="pc-m">
        <span class="pc-k">排名稳定度</span>
        <StabilityMeter :value="entry.rank_stability" :grade="entry.rank_stability_grade" :level="entry.rank_stability_level" :series="entry.rank_series" />
      </div>
      <div class="pc-m inline">
        <span class="pc-kv"><span class="pc-k">趋势稳定度</span><b class="num">{{ n(entry.trend_stability) }}</b></span>
        <span class="pc-kv"><span class="pc-k">买点质量</span><b class="num">{{ n(entry.buy_quality) }}</b></span>
        <span class="pc-kv"><span class="pc-k">板块强度</span><b class="num">{{ n(entry.sector_strength) }}</b></span>
        <span class="pc-kv"><span class="pc-k">综合评分</span><b class="num">{{ entry.composite.toFixed(1) }}</b></span>
        <span class="pc-kv"><span class="pc-k">当前排名</span><b class="num">#{{ entry.rank }}</b></span>
      </div>
    </div>

    <button v-if="!showExplain" type="button" class="pc-toggle" @click="expanded = !expanded">
      {{ expanded ? '收起说明' : '为什么是它 / 失效条件' }} {{ expanded ? '▴' : '▾' }}
    </button>
    <ul v-if="showExplain || expanded" class="pc-explain">
      <li v-for="(x, i) in entry.explain" :key="i">{{ x }}</li>
    </ul>
    <div v-if="entry.invalidation && (showExplain || expanded)" class="pc-inv">{{ entry.invalidation }}</div>
    <div v-if="entry.decision_missing?.length" class="pc-missing">
      缺失分量按中性 50 计:{{ entry.decision_missing.map(k => PART_LABEL[k as keyof typeof PART_LABEL] || k).join('、') }}
    </div>

    <footer v-if="$slots.default" class="pc-foot"><slot /></footer>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { stockPath } from '@/utils/score'
import { BUY_STATE_TYPE, PART_LABEL, type PoolEntry } from '@/api/decision'
import ChangeText from '@/components/stock/ChangeText.vue'
import StabilityMeter from './StabilityMeter.vue'
import RankChangeCell from './RankChangeCell.vue'

// 优先级卡:一张卡回答"这只为什么值得看、现在能不能买、什么价买、到哪失效、风险多大"。
const props = withDefaults(defineProps<{
  entry: PoolEntry
  rankLabel: string
  hero?: boolean
  showExplain?: boolean
  prevSlot?: string | null
}>(), { showExplain: true })
const expanded = ref(false)

const zoneLabel = computed(() => {
  const s = props.entry.buy_state
  if (s === 'in_zone') return '买入区间'
  if (s === 'near_above' || s === 'wait_pullback' || s === 'extended') return '等待价格'
  if (s === 'below_zone') return '企稳后买点区'
  if (s === 'invalidated') return '买点区(已失效)'
  if (s === 'bearish') return '买点区'
  return '买点区'
})
const zoneText = computed(() => {
  const z = props.entry.buy_zone
  if (!z) return props.entry.buy_state === 'bearish' ? '不建仓' : '未计算'
  return `${z[0]}–${z[1]}`
})
const zoneCls = computed(() => props.entry.buy_state === 'in_zone' ? 'price-up' : '')
function n(v: number | null | undefined) { return v == null ? '—' : Math.round(v) }
</script>

<style scoped>
.pc {
  border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--surface);
  padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; min-width: 0;
}
.pc.hero { border-color: var(--brand); box-shadow: var(--shadow-card); }
.pc.state-in_zone { border-left: 4px solid var(--up); }
.pc.state-near_above, .pc.state-wait_pullback { border-left: 4px solid var(--warn); }
.pc.state-extended, .pc.state-below_zone, .pc.state-no_zone { border-left: 4px solid var(--line-strong); }
.pc.state-invalidated, .pc.state-bearish { border-left: 4px solid var(--down); }
.pc-head { display: flex; align-items: flex-start; gap: 10px; }
.pc-rank { font-size: 12px; color: var(--brand); font-weight: 600; white-space: nowrap; padding-top: 3px; }
.pc-title { flex: 1; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; }
.pc-name { font-size: 17px; font-weight: 600; color: var(--text); text-decoration: none; }
.pc-code { font-size: 12px; color: var(--text-3); }
.pc-ind { font-size: 12px; color: var(--text-3); }
.pc-score { text-align: right; white-space: nowrap; }
.pc-score-k { display: block; font-size: 11px; color: var(--text-3); }
.pc-score b { font-size: 26px; line-height: 1.1; color: var(--text); }
.pc-state-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.pc-state { font-weight: 600; }
.pc-state-note { font-size: 12px; color: var(--warn-text); }
.pc-change { margin-left: auto; }
.pc-prices { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px 12px; }
.pc-p { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.pc-p b { font-size: 17px; color: var(--text); }
.pc-p b.warn { color: var(--warn-text); }
.pc-chg { font-size: 12px; }
.pc-k { font-size: 11px; color: var(--text-3); }
.risk-低 { color: var(--up); } .risk-中 { color: var(--warn-text); } .risk-高 { color: var(--down); }
.pc-metrics { display: flex; flex-direction: column; gap: 6px; }
.pc-m { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.pc-m.inline { gap: 4px 14px; }
.pc-kv { display: inline-flex; gap: 4px; align-items: baseline; white-space: nowrap; }
.pc-m.inline b { color: var(--text); }
.pc-toggle { border: 0; background: transparent; padding: 0; color: var(--brand); cursor: pointer; text-align: left; font: inherit; font-size: 12px; }
.pc-explain { margin: 0; padding-left: 18px; font-size: 12px; color: var(--text-2); line-height: 1.7; }
.pc-inv { font-size: 12px; color: var(--warn-text); background: var(--warn-soft); padding: 6px 10px; border-radius: var(--radius-sm); }
.pc-missing { font-size: 11px; color: var(--text-4); }
.pc-foot { display: flex; gap: 8px; flex-wrap: wrap; }
.pc:not(.hero) .pc-prices { grid-template-columns: repeat(2, 1fr); }
@media (max-width: 768px) {
  .pc { padding: 12px; }
  .pc-prices { grid-template-columns: repeat(2, 1fr); }
  .pc-score b { font-size: 22px; }
}
</style>
