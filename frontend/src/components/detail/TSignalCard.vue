<template>
  <AppCard v-if="signal && signal.action !== 'no_data'" class="t-signal-card" :class="signal.action">
    <template #title>
      <span class="t-title">日内做 T 建议</span>
      <el-tag :type="tagType" effect="dark" size="large" class="t-action">{{ signal.action_label }}</el-tag>
    </template>
    <template #actions>
      <div class="t-strength">
        <span class="t-strength-label">信号强度</span>
        <el-progress :percentage="signal.strength" :stroke-width="8" :show-text="false" class="t-strength-bar" />
        <span class="t-strength-num num">{{ signal.strength }}</span>
      </div>
      <span class="t-time" v-if="signal.data_time">{{ signal.data_time }}</span>
    </template>

    <!-- 分时图 + 买卖区 + 支撑压力 + 成本线 -->
    <IntradayTChart v-if="signal.trend && signal.trend.length" :signal="signal" :height="isMobile ? 240 : 300" />

    <StatGrid :items="metrics" :min-width="isMobile ? 96 : 110" size="sm" variant="inline" class="t-metrics" />

    <!-- 四因子评分(去魔法数字,可解释) -->
    <div class="t-factors" v-if="signal.strength > 0">
      <div class="t-factor" v-for="f in factorList" :key="f.key">
        <span class="t-factor-label">{{ f.label }}</span>
        <el-progress :percentage="f.val" :stroke-width="6" :show-text="false" :color="f.color" />
        <b class="num">{{ f.val }}</b>
      </div>
    </div>

    <div class="t-zones" v-if="signal.buy_zone || signal.sell_zone">
      <div class="t-zone buy" v-if="signal.buy_zone">建议低吸区 <b class="num">{{ signal.buy_zone[0] }} ~ {{ signal.buy_zone[1] }}</b></div>
      <div class="t-zone sell" v-if="signal.sell_zone">建议高抛区 <b class="num">{{ signal.sell_zone[0] }} ~ {{ signal.sell_zone[1] }}</b></div>
    </div>

    <!-- 结合持仓的真 T 建议 -->
    <div class="t-position-plan" v-if="signal.has_position">
      <div class="tp-head"><el-icon><Wallet /></el-icon> 结合持仓做 T</div>
      <div class="tp-body" v-if="signal.t_shares > 0">
        <template v-if="signal.t_mode === 'reverse_t'">
          反T·先高抛:卖出可用底仓 <b>{{ signal.t_shares }}</b> 股,回补参考 <b>{{ signal.cover_price }}</b>,预计兑现价差 <b class="price-up">{{ signal.est_profit }}</b> 元
        </template>
        <template v-else-if="signal.t_mode === 'positive_t_add'">
          正T·补仓降本:补 <b>{{ signal.t_shares }}</b> 股,摊薄成本至 <b>{{ signal.new_avg_cost }}</b>(降 <b class="price-down">{{ signal.cost_impact != null ? Math.abs(signal.cost_impact).toFixed(2) : '' }}</b>)
        </template>
        <template v-else-if="signal.t_mode === 'positive_t_roundtrip'">
          正T·日内闭环:低吸买入 <b>{{ signal.t_shares }}</b> 股,反弹至 <b>{{ signal.cover_price }}</b> 卖出等量可用底仓
        </template>
      </div>
      <div class="tp-body warn" v-else-if="signal.t_mode === 'blocked_no_available'">
        有底仓但无可用(可卖)份额,T+1 当日不可高抛
      </div>
      <div class="tp-pnl" v-if="signal.position">
        持仓 {{ signal.position.shares }} 股 · 成本 {{ signal.position.avg_cost }} · 浮盈
        <ChangeText :value="signal.position.pnl_pct" />
      </div>
    </div>

    <!-- 持仓输入:填成本后按底仓实时重算真 T -->
    <div class="t-pos-input">
      <span class="tpi-label">持仓做 T</span>
      <el-input-number v-model="posShares" :min="0" :step="100" :controls="false" size="small" placeholder="持仓股数" />
      <el-input-number v-model="posCost" :min="0" :precision="2" :step="0.01" :controls="false" size="small" placeholder="成本价" />
      <el-input-number v-model="posAvail" :min="0" :step="100" :controls="false" size="small" placeholder="可用股数" />
      <el-button type="primary" size="small" @click="recalc">按持仓重算</el-button>
      <el-button v-if="signal.has_position" text size="small" @click="clearPosition">清除</el-button>
    </div>

    <ul class="t-reasons">
      <li v-for="r in signal.reasons" :key="r">{{ r }}</li>
    </ul>
    <div class="t-risks" v-if="signal.risks && signal.risks.length">
      <el-icon><Warning /></el-icon> {{ signal.risks.join('；') }}
    </div>
    <div class="t-disclaimer">{{ signal.disclaimer }}</div>
  </AppCard>
  <AppCard v-else-if="signal" title="日内做 T 建议">
    <el-empty description="暂无分时数据（非交易时段或数据源不可用）" :image-size="72" />
  </AppCard>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Wallet, Warning } from '@element-plus/icons-vue'
import { PV_LABEL, type TSignal, type TPositionInput } from '@/api/t'
import { useDevice } from '@/composables/useDevice'
import type { StatItem } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import StatGrid from '@/components/ui/StatGrid.vue'
import ChangeText from '@/components/stock/ChangeText.vue'
import IntradayTChart from '@/components/charts/IntradayTChart.vue'

// 持仓输入由本组件持有；父组件负责按 position 重新请求信号。
const props = defineProps<{ signal: TSignal | null; code: string }>()
const emit = defineEmits<{ (e: 'recalc', pos: TPositionInput | undefined): void }>()
const { isMobile } = useDevice()

const posShares = ref<number | undefined>()
const posCost = ref<number | undefined>()
const posAvail = ref<number | undefined>()

// 切换股票时清空持仓输入,避免把上一只的持仓成本带到新股票
watch(() => props.code, () => {
  posShares.value = undefined
  posCost.value = undefined
  posAvail.value = undefined
})

const tagType = computed(() => {
  const a = props.signal?.action
  return a === 'positive_t' ? 'danger' : a === 'negative_t' ? 'success' : 'info'
})

const metrics = computed<StatItem[]>(() => {
  const s = props.signal
  if (!s) return []
  const items: StatItem[] = [
    { label: '现价', value: s.price },
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

const factorList = computed(() => {
  const s = props.signal?.subscores
  if (!s) return []
  return [
    { key: 'position', label: '位置', val: s.position, color: 'var(--brand)' },
    { key: 'volume', label: '量能', val: s.volume, color: 'var(--down)' },
    { key: 'momentum', label: '动量', val: s.momentum, color: 'var(--warn)' },
    { key: 'index', label: '大盘', val: s.index, color: 'var(--text-3)' },
  ]
})

function currentPos(): TPositionInput | undefined {
  return (posShares.value && posCost.value)
    ? { shares: posShares.value, avg_cost: posCost.value, available: posAvail.value ?? posShares.value }
    : undefined
}

function recalc() {
  if (!posShares.value || !posCost.value) {
    ElMessage.warning('请填写持仓数量与成本价')
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
.t-metrics { margin-bottom: 12px; }
.t-zones { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.t-zone { padding: 8px 14px; border-radius: 8px; font-size: 13px; }
.t-zone b { font-size: 15px; }
.t-zone.buy { background: var(--up-soft); color: var(--up); }
.t-zone.sell { background: var(--down-soft); color: var(--down); }
.t-reasons { margin: 0 0 10px; padding-left: 18px; }
.t-reasons li { color: var(--text-3); font-size: 13px; line-height: 1.7; }
.t-risks { display: flex; align-items: center; gap: 6px; color: var(--warn-text); font-size: 13px; margin-bottom: 8px; }
.t-disclaimer { color: var(--text-4); font-size: 12px; font-style: italic; }
.t-factors { display: flex; gap: 18px; flex-wrap: wrap; margin-bottom: 12px; }
.t-factor { display: flex; align-items: center; gap: 8px; min-width: 150px; flex: 1; }
.t-factor-label { color: var(--text-3); font-size: 12px; width: 28px; flex-shrink: 0; }
.t-factor :deep(.el-progress) { flex: 1; }
.t-factor b { color: var(--text); font-size: 13px; width: 24px; text-align: right; flex-shrink: 0; }
.t-position-plan { background: var(--brand-soft); border-radius: 8px; padding: 10px 14px; margin-bottom: 10px; }
.tp-head { display: flex; align-items: center; gap: 6px; color: var(--brand); font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.tp-body { color: var(--text); font-size: 14px; line-height: 1.6; }
.tp-body.warn { color: var(--warn-text); }
.tp-body b { font-size: 15px; margin: 0 2px; }
.tp-pnl { color: var(--text-3); font-size: 12px; margin-top: 6px; }
.t-pos-input { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.t-pos-input .tpi-label { color: var(--text-3); font-size: 13px; }
.t-pos-input :deep(.el-input-number) { width: 110px; }
@media (max-width: 768px) {
  .t-strength-bar { width: 80px; }
  .t-factor { min-width: 120px; }
  .t-pos-input :deep(.el-input-number) { width: calc(50% - 4px); }
}
</style>
