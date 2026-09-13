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
      <!-- 仓位状态:可卖 / 今日买入锁定 / 总持仓 -->
      <span v-if="execution" class="pos-status num">
        可卖 <b>{{ execution.available_shares }}</b> · 今日买入锁定 <b>{{ execution.locked_today }}</b> · 总持仓 <b>{{ execution.total_shares }}</b>
      </span>
    </div>

    <div v-if="plan && plan.mode !== 'wait'" class="plan-steps">
      <template v-if="plan.mode === 'sell_first'">
        <div class="plan-step sell">
          <div class="ps-head"><span class="ps-no">第一步 · 卖出</span><span class="ps-hint" v-if="execution && execution.sell_shares > 0">昨日可卖底仓 {{ execution.sell_shares }} 股</span></div>
          <div class="ps-zone num">{{ plan.sell_zone?.[0] }} ~ {{ plan.sell_zone?.[1] }}</div>
          <div class="ps-note">{{ execution && execution.available_shares > 0 ? '卖出昨日可卖底仓;今日买入的仓位 T+1 不可卖' : '无昨日底仓可卖:本步今日不可执行' }}</div>
        </div>
        <div class="ps-arrow">→ 等待回落</div>
        <div class="plan-step buy">
          <div class="ps-head"><span class="ps-no">第二步 · 接回</span><span class="ps-hint" v-if="execution && execution.rebuy_shares > 0">买回等量 {{ execution.rebuy_shares }} 股</span></div>
          <div class="ps-zone num">{{ plan.buyback_zone?.[0] }} ~ {{ plan.buyback_zone?.[1] }}</div>
          <div class="ps-note">回补部分今日锁定至下一交易日</div>
        </div>
      </template>
      <template v-else>
        <div class="plan-step buy">
          <div class="ps-head"><span class="ps-no">第一步 · 低吸</span><span class="ps-hint" v-if="execution && execution.rebuy_shares > 0">买入 {{ execution.rebuy_shares }} 股(今日锁定)</span></div>
          <div class="ps-zone num">{{ plan.buy_zone?.[0] }} ~ {{ plan.buy_zone?.[1] }}</div>
          <div class="ps-note">跌破失效位不接</div>
        </div>
        <div class="ps-arrow">→ 等待反弹</div>
        <div class="plan-step sell">
          <div class="ps-head"><span class="ps-no">第二步 · 卖出</span><span class="ps-hint" v-if="execution && execution.sell_shares > 0">卖出昨日底仓 {{ execution.sell_shares }} 股</span></div>
          <div class="ps-zone num">{{ plan.sellback_zone?.[0] }} ~ {{ plan.sellback_zone?.[1] }}</div>
          <div class="ps-note">{{ execution?.sell_shares ? '卖昨日可卖底仓完成等量闭环' : '今日买入部分 T+1,下一交易日才可卖' }}</div>
        </div>
      </template>
    </div>

    <div v-else-if="plan" class="plan-wait">
      <div class="pw-line">{{ plan.rules }}</div>
      <div class="pw-line" v-if="plan.watch_hint">{{ plan.watch_hint }}</div>
      <div class="pw-line" v-if="execution?.exec_text">{{ execution.exec_text }}</div>
    </div>

    <!-- 执行明细:卖哪一部分、为什么能卖 -->
    <div class="exec-block" v-if="execution && plan?.mode !== 'wait'">
      <div class="exec-line">{{ execution.exec_text }}</div>
      <ul class="exec-notes">
        <li v-for="(n, i) in execution.notes" :key="i">{{ n }}</li>
      </ul>
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

    <!-- 持仓输入:填总持仓/可卖/成本后,按 T+1 规则重算精确股数 -->
    <div class="t-pos-input">
      <span class="tpi-label">按我的持仓重算</span>
      <el-input-number v-model="posShares" :min="0" :step="100" :controls="false" size="small" placeholder="总持仓(股)" />
      <el-input-number v-model="posAvail" :min="0" :step="100" :controls="false" size="small" placeholder="可卖(股)" />
      <el-input-number v-model="posCost" :min="0" :precision="2" :step="0.01" :controls="false" size="small" placeholder="成本价" />
      <el-button type="primary" size="small" @click="recalc">重算</el-button>
      <el-button v-if="signal.has_position" text size="small" @click="clearPosition">清除</el-button>
    </div>
    <div class="tpi-tip">可卖 ≤ 总持仓;总持仓 − 可卖 = 今日买入锁定部分</div>

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
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Warning } from '@element-plus/icons-vue'
import { PV_LABEL, type TSignal, type TPositionInput } from '@/api/t'
import { useDevice } from '@/composables/useDevice'
import type { StatItem } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import StatGrid from '@/components/ui/StatGrid.vue'
import ChangeText from '@/components/stock/ChangeText.vue'
import IntradayTChart from '@/components/charts/IntradayTChart.vue'

// 做T决策卡:第一眼给出「哪里卖、哪里买、卖哪一部分、什么时候不做」。
// 计划(区间/规则/失效/T+1执行明细)全部由服务端计算,前端只做展示;
// 持仓输入仅用于把通用建议换算成精确股数。
const props = defineProps<{ signal: TSignal | null; code: string }>()
const emit = defineEmits<{ (e: 'recalc', pos: TPositionInput | undefined): void }>()
const { isMobile } = useDevice()

const plan = computed(() => props.signal?.plan ?? null)
const execution = computed(() => props.signal?.plan?.execution ?? null)

// 持仓输入由本组件持有;切股票时清空,避免把上一只的持仓带到新股票
const posShares = ref<number | undefined>()
const posCost = ref<number | undefined>()
const posAvail = ref<number | undefined>()
watch(() => props.code, () => {
  posShares.value = undefined
  posCost.value = undefined
  posAvail.value = undefined
})

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

function currentPos(): TPositionInput | undefined {
  return (posShares.value && posCost.value)
    ? { shares: posShares.value, avg_cost: posCost.value, available: posAvail.value ?? posShares.value }
    : undefined
}

function recalc() {
  if (!posShares.value || !posCost.value) {
    ElMessage.warning('请填写总持仓与成本价')
    return
  }
  emit('recalc', currentPos())
}

function clearPosition() {
  posShares.value = undefined
  posCost.value = undefined
  posAvail.value = undefined
  emit('recalc', undefined)
}

defineExpose({ currentPos })
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
.pos-status { margin-left: auto; font-size: 12px; color: var(--text-3); }
.pos-status b { color: var(--text); font-weight: 600; }
.exec-block {
  background: var(--brand-soft); border-radius: var(--radius); padding: 10px 14px; margin-bottom: 12px;
}
.exec-line { font-size: 14px; color: var(--text); line-height: 1.7; }
.exec-notes { margin: 6px 0 0; padding-left: 18px; }
.exec-notes li { font-size: 12px; color: var(--text-3); line-height: 1.7; }
.t-pos-input { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 4px 0 6px; }
.t-pos-input .tpi-label { color: var(--text-3); font-size: 13px; }
.t-pos-input :deep(.el-input-number) { width: 110px; }
.tpi-tip { font-size: 11px; color: var(--text-4); margin-bottom: 12px; }
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
  .plan-price-row { flex-wrap: wrap; }
  .pos-status { margin-left: 0; flex-basis: 100%; }
  .t-pos-input :deep(.el-input-number) { width: calc(50% - 4px); }
}
</style>
