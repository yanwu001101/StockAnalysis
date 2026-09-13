<template>
  <AppCard v-if="signal && signal.action !== 'no_data'" class="t-signal-card" :class="signal.action">
    <template #title>
      <span class="t-title">做T操作计划</span>
      <el-tag :type="tagType" effect="dark" size="large" class="t-action">{{ plan?.title || signal.action_label }}</el-tag>
    </template>
    <template #actions>
      <div class="t-strength">
        <span class="t-strength-label">信号强度</span>
        <el-progress :percentage="signal.strength" :stroke-width="8" :show-text="false" class="t-strength-bar" />
        <span class="t-strength-num num">{{ signal.strength }}</span>
      </div>
      <span class="t-time" v-if="signal.data_time">{{ signal.data_time }}</span>
    </template>

    <!-- 当前价 + 计划区:第一眼就是"哪里卖、哪里买" -->
    <div class="plan-price-row">
      <span class="plan-price-label">当前价</span>
      <span class="plan-price num" :class="signal.pct_change != null && signal.pct_change >= 0 ? 'price-up' : 'price-down'">
        {{ signal.price ?? '—' }}
      </span>
      <ChangeText :value="signal.pct_change" class="plan-pct" />
    </div>

    <div v-if="plan && plan.mode !== 'wait'" class="plan-steps">
      <template v-if="plan.mode === 'sell_first'">
        <div class="plan-step sell">
          <div class="ps-head"><span class="ps-no">第一步 · 卖出</span><span class="ps-hint">{{ plan.size_hint }}</span></div>
          <div class="ps-zone num">{{ plan.sell_zone?.[0] }} ~ {{ plan.sell_zone?.[1] }}</div>
          <div class="ps-note">分笔卖出,避免一笔打光</div>
        </div>
        <div class="ps-arrow">→ 等待回落</div>
        <div class="plan-step buy">
          <div class="ps-head"><span class="ps-no">第二步 · 接回</span><span class="ps-hint">买回等量</span></div>
          <div class="ps-zone num">{{ plan.buyback_zone?.[0] }} ~ {{ plan.buyback_zone?.[1] }}</div>
          <div class="ps-note">未到接回区不追接</div>
        </div>
      </template>
      <template v-else>
        <div class="plan-step buy">
          <div class="ps-head"><span class="ps-no">第一步 · 低吸</span><span class="ps-hint">{{ plan.size_hint }}</span></div>
          <div class="ps-zone num">{{ plan.buy_zone?.[0] }} ~ {{ plan.buy_zone?.[1] }}</div>
          <div class="ps-note">分笔买入,跌破失效位不接</div>
        </div>
        <div class="ps-arrow">→ 等待反弹</div>
        <div class="plan-step sell">
          <div class="ps-head"><span class="ps-no">第二步 · 卖出</span><span class="ps-hint">卖出等量</span></div>
          <div class="ps-zone num">{{ plan.sellback_zone?.[0] }} ~ {{ plan.sellback_zone?.[1] }}</div>
          <div class="ps-note">14:50 前未到则按纪律处理</div>
        </div>
      </template>
    </div>

    <div v-else-if="plan" class="plan-wait">
      <div class="pw-line">{{ plan.rules }}</div>
      <div class="pw-line" v-if="plan.watch_hint">{{ plan.watch_hint }}</div>
    </div>

    <!-- 分时图:买卖区带 + 支撑/压力/失效位直接标注 -->
    <IntradayTChart v-if="signal.trend && signal.trend.length" :signal="signal" :height="isMobile ? 240 : 300" />

    <!-- 执行规则 / 失效条件:明确什么时候不做 -->
    <div class="plan-rules" v-if="plan?.rules">
      <div class="pr-head">
        <span class="pr-block rules">执行规则</span>
        <span class="pr-text">{{ plan.rules }}</span>
      </div>
      <div class="pr-head" v-if="plan.invalidation">
        <span class="pr-block invalid">失效条件</span>
        <span class="pr-text">{{ plan.invalidation }}</span>
      </div>
    </div>

    <ul class="t-reasons">
      <li class="reasons-cap">为什么是这个计划</li>
      <li v-for="r in signal.reasons" :key="r">{{ r }}</li>
    </ul>

    <StatGrid :items="metrics" :min-width="isMobile ? 96 : 110" size="sm" variant="inline" class="t-metrics" />

    <div class="t-risks" v-if="signal.risks && signal.risks.length">
      <el-icon><Warning /></el-icon> {{ signal.risks.join('；') }}
    </div>
    <div class="t-disclaimer">{{ signal.disclaimer }}</div>
  </AppCard>
  <AppCard v-else-if="signal" title="做T操作计划">
    <el-empty description="暂无分时数据（非交易时段或数据源不可用）" :image-size="72" />
  </AppCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Warning } from '@element-plus/icons-vue'
import { PV_LABEL, type TSignal } from '@/api/t'
import { useDevice } from '@/composables/useDevice'
import type { StatItem } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import StatGrid from '@/components/ui/StatGrid.vue'
import ChangeText from '@/components/stock/ChangeText.vue'
import IntradayTChart from '@/components/charts/IntradayTChart.vue'

// 做T决策卡:第一眼给出「哪里卖、哪里买、什么时候不做」。
// 计划(区间/规则/失效)全部由服务端 plan 计算,前端只做展示。
const props = defineProps<{ signal: TSignal | null; code: string }>()
const { isMobile } = useDevice()

const plan = computed(() => props.signal?.plan ?? null)

const tagType = computed(() => {
  const m = plan.value?.mode
  return m === 'sell_first' ? 'success' : m === 'buy_first' ? 'danger' : 'info'
})

const metrics = computed<StatItem[]>(() => {
  const s = props.signal
  if (!s) return []
  const items: StatItem[] = [
    { label: '分时均价', value: s.vwap },
    { label: '日内位置', value: s.intraday_pos != null ? (s.intraday_pos * 100).toFixed(0) + '%' : '—' },
    { label: '偏离均价', value: s.vwap_dev != null ? (s.vwap_dev > 0 ? '+' : '') + s.vwap_dev + '%' : '—' },
    { label: '日内振幅', value: s.amplitude != null ? s.amplitude + '%' : '—' },
    { label: '日内高/低', value: `${s.day_high ?? '—'} / ${s.day_low ?? '—'}` },
  ]
  if (s.active_buy_ratio != null) items.push({ label: '主动买占比', value: (s.active_buy_ratio * 100).toFixed(0) + '%' })
  const pv = PV_LABEL[s.pv_pattern || ''] || ''
  if (pv) items.push({ label: '量价', value: pv })
  if (s.index_ctx) {
    const pc = s.index_ctx.pct_change
    items.push({ label: '大盘', value: `${s.index_ctx.name} ${pc > 0 ? '+' : ''}${pc}%`, cls: pc >= 0 ? 'price-up' : 'price-down' })
  }
  return items
})
</script>

<style scoped>
.t-title { font-size: 15px; font-weight: 600; margin-right: 10px; }
.t-action { vertical-align: middle; }
.t-strength { display: flex; align-items: center; gap: 8px; }
.t-strength-label { color: var(--text-3); font-size: 12px; }
.t-strength-bar { width: 120px; }
.t-strength-num { font-weight: 700; color: var(--text); }
.t-time { color: var(--text-3); font-size: 12px; }

.plan-price-row { display: flex; align-items: baseline; gap: 10px; margin-bottom: 12px; }
.plan-price-label { font-size: 12px; color: var(--text-3); }
.plan-price { font-size: 30px; font-weight: 700; letter-spacing: -0.01em; }
.plan-pct { font-size: 15px; }

.plan-steps { display: grid; grid-template-columns: 1fr auto 1fr; gap: 10px; align-items: stretch; margin-bottom: 12px; }
.plan-step { border-radius: var(--radius); padding: 10px 14px; min-width: 0; }
.plan-step.sell { background: var(--down-soft); }
.plan-step.buy { background: var(--up-soft); }
.ps-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.ps-no { font-size: 12px; font-weight: 600; }
.plan-step.sell .ps-no { color: var(--down); }
.plan-step.buy .ps-no { color: var(--up); }
.ps-hint { font-size: 11px; color: var(--text-3); }
.ps-zone { font-size: 21px; font-weight: 700; margin: 4px 0 2px; letter-spacing: -0.01em; }
.plan-step.sell .ps-zone { color: var(--down); }
.plan-step.buy .ps-zone { color: var(--up); }
.ps-note { font-size: 11px; color: var(--text-3); }
.ps-arrow { align-self: center; color: var(--text-3); font-size: 12px; white-space: nowrap; }

.plan-wait {
  background: var(--bg-2); border-radius: var(--radius); padding: 10px 14px; margin-bottom: 12px;
  color: var(--text-2); font-size: 13px; line-height: 1.7;
}

.plan-rules { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.pr-head { display: flex; gap: 10px; align-items: flex-start; }
.pr-block {
  flex-shrink: 0; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: var(--radius-sm);
}
.pr-block.rules { background: var(--brand-soft); color: var(--brand); }
.pr-block.invalid { background: var(--warn-soft); color: var(--warn-text); }
.pr-text { font-size: 13px; color: var(--text-2); line-height: 1.7; min-width: 0; }

.t-metrics { margin-bottom: 12px; }
.t-reasons { margin: 0 0 10px; padding-left: 18px; }
.reasons-cap { list-style: none; margin-left: -18px; font-size: 12px; color: var(--text-3); font-weight: 600; }
.t-reasons li:not(.reasons-cap) { color: var(--text-3); font-size: 13px; line-height: 1.7; }
.t-risks { display: flex; align-items: center; gap: 6px; color: var(--warn-text); font-size: 13px; margin-bottom: 8px; }
.t-disclaimer { color: var(--text-4); font-size: 12px; font-style: italic; }

@media (max-width: 768px) {
  .t-strength-bar { width: 80px; }
  .plan-steps { grid-template-columns: 1fr; gap: 8px; }
  .ps-arrow { text-align: center; }
  .plan-price { font-size: 26px; }
}
</style>
