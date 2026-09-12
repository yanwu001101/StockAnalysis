<template>
  <div class="paper-panel" :class="{ mobile: isMobile }">
    <!-- 未启动 -->
    <EmptyState
      v-if="loaded && !data"
      title="模拟盘尚未启动"
      description="每个交易日 17:50 自动按综合评分（各策略默认权重加权）调仓并记录净值，与沪深300对比。也可在下方手动重置启动。"
    >
      <el-button type="primary" :loading="resetting" @click="doReset(1000000, 10)">以 100 万本金启动</el-button>
    </EmptyState>

    <template v-if="data?.account">
      <!-- 绩效 -->
      <AppCard title="模拟盘绩效" sub="每日 17:50 自动调仓 · 成本口径与回测一致（佣金+印花税+滑点）">
        <template #actions>
          <span class="sweep-meta">起始 {{ data.account.start_date || '—' }} · 本金 {{ fmtWan(data.account.initial_capital) }} 万 · Top{{ data.account.top_n }}</span>
          <el-popover trigger="click" :width="280">
            <template #reference>
              <el-button size="small" plain>重置</el-button>
            </template>
            <div class="reset-box">
              <div class="reset-tip">清空全部持仓与净值记录，以新本金重新开始。不可撤销。</div>
              <el-input-number v-model="resetCapital" :min="10" :max="10000" :step="10" style="width: 100%" />
              <el-button type="danger" size="small" style="width: 100%; margin-top: 8px"
                         :loading="resetting" @click="doReset(resetCapital * 10000, data?.account?.top_n ?? 10)">
                确认重置为 {{ resetCapital }} 万
              </el-button>
            </div>
          </el-popover>
        </template>
        <StatGrid :items="perfItems" :cols="isMobile ? 2 : 3" />
      </AppCard>

      <!-- 净值曲线 -->
      <AppCard title="净值对比" sub="模拟盘净值 vs 沪深300（同起点归一）" compact>
        <BaseChart :option="curveOption" :height="isMobile ? 260 : 340" />
      </AppCard>

      <!-- 当前持仓 -->
      <AppCard title="当前持仓" sub="按市值降序" compact>
        <StockTable :rows="data.positions" :columns="positionColumns" :stock="false" :clickable="false"
                    dense row-key="code" :empty="data.positions.length ? '' : '空仓'" />
      </AppCard>

      <!-- 调仓记录 -->
      <AppCard title="调仓记录" sub="最近 100 条" compact>
        <StockTable :rows="data.recent_trades" :columns="tradeColumns" :stock="false" :clickable="false"
                    dense row-key="id">
          <template #cell-side="{ row }">
            <span :class="['side-tag', row.side]">{{ row.side === 'buy' ? '买入' : '卖出' }}</span>
          </template>
        </StockTable>
      </AppCard>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getPaper, resetPaper } from '@/api/paper'
import { useDevice } from '@/composables/useDevice'
import { useChartTokens, baseTooltip } from '@/composables/useEcharts'
import type { EChartsOption } from 'echarts'
import type { PaperOverview } from '@/types'
import type { StatItem, StockColumn } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import StatGrid from '@/components/ui/StatGrid.vue'
import StockTable from '@/components/stock/StockTable.vue'
import BaseChart from '@/components/charts/BaseChart.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import * as echarts from 'echarts'

const { isMobile } = useDevice()
const tokens = useChartTokens()

const loaded = ref(false)
const data = ref<PaperOverview | null>(null)
const resetting = ref(false)
const resetCapital = ref(100)

function fmtWan(v: number): string {
  return (v / 10000).toFixed(0)
}

const perfItems = computed<StatItem[]>(() => {
  const r = data.value
  if (!r) return []
  const m = r.metrics
  const pct = (v: number) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
  return [
    { label: '总收益', value: pct(m.total_return), cls: m.total_return >= 0 ? 'price-up' : 'price-down' },
    { label: '年化收益', value: pct(m.annualized_return), cls: m.annualized_return >= 0 ? 'price-up' : 'price-down' },
    { label: '最大回撤', value: `-${(Math.abs(m.max_drawdown) * 100).toFixed(2)}%`, cls: 'price-down' },
    { label: '沪深300 同期', value: m.benchmark_return != null ? pct(m.benchmark_return) : '—' },
    { label: '超额收益', value: m.excess_return != null ? pct(m.excess_return) : '—', cls: (m.excess_return ?? 0) >= 0 ? 'price-up' : 'price-down' },
    { label: '累计交易成本', value: `${(r.total_costs / 10000).toFixed(2)} 万`, cls: 'warn-text' },
  ]
})

const positionColumns: StockColumn[] = [
  { key: 'code', label: '代码', mobile: 'title' },
  { key: 'shares', label: '股数', type: 'num', digits: 0, mobile: 'secondary' },
  { key: 'avg_cost', label: '成本', type: 'num', digits: 3, mobile: 'secondary' },
  { key: 'last_close', label: '现价', type: 'num', digits: 3 },
  { key: 'market_value', label: '市值', type: 'num', digits: 0, mobile: 'primary' },
  { key: 'weight', label: '权重', type: 'num', digits: 1, suffix: '%', align: 'center' },
  { key: 'pnl_pct', label: '盈亏', type: 'percent', digits: 2, colored: true, mobile: 'primary' },
]

const tradeColumns: StockColumn[] = [
  { key: 'trade_date', label: '日期', mobile: 'title' },
  { key: 'code', label: '代码', mobile: 'secondary' },
  { key: 'side', label: '方向', align: 'center', mobile: 'primary' },
  { key: 'shares', label: '股数', type: 'num', digits: 0, mobile: 'secondary' },
  { key: 'price', label: '价格', type: 'num', digits: 3 },
  { key: 'cost', label: '费用', type: 'num', digits: 2, mobile: 'secondary' },
  { key: 'reason', label: '备注', mobile: 'hidden' },
]

const curveOption = computed<EChartsOption | null>(() => {
  const rows = data.value?.equity_curve
  if (!rows?.length) return null
  const t = tokens.value
  const series: any[] = [{
    type: 'line',
    name: '模拟盘',
    data: rows.map(r => r.equity),
    symbol: 'none',
    smooth: true,
    lineStyle: { color: t.brand, width: 2 },
    areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: t.brand },
      { offset: 1, color: t.brand },
    ]) },
  }]
  const hasBench = rows.some(r => r.benchmark != null)
  if (hasBench) {
    series.push({
      type: 'line',
      name: '沪深300',
      data: rows.map(r => r.benchmark),
      symbol: 'none',
      smooth: true,
      lineStyle: { color: t.series[5] || t.text3, width: 1.5, type: 'dashed' },
    })
  }
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: t.font },
    legend: { data: series.map(s => s.name), top: 0, right: 8, textStyle: { color: t.text3, fontSize: 11 }, itemWidth: 16 },
    grid: { left: 64, right: 20, top: series.length > 1 ? 32 : 20, bottom: 36 },
    xAxis: { type: 'category', data: rows.map(r => r.date),
      axisLabel: { color: t.text3, fontSize: 10 },
      axisLine: { lineStyle: { color: t.line } } },
    yAxis: { type: 'value', scale: true,
      splitLine: { lineStyle: { color: t.line } },
      axisLabel: { color: t.text3 } },
    series,
    tooltip: { trigger: 'axis', ...baseTooltip(t) },
  }
})

async function load() {
  try {
    const r = await getPaper()
    data.value = (r as any).status === 'not-started' ? null : r
  } catch {
    data.value = null
  } finally {
    loaded.value = true
  }
}

async function doReset(capital: number, topN: number) {
  try {
    await ElMessageBox.confirm(
      `将清空全部持仓与净值记录，以 ${capital / 10000} 万本金重新开始。不可撤销。`,
      '重置模拟盘', { confirmButtonText: '重置', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  resetting.value = true
  try {
    await resetPaper({ initialCapital: capital, topN })
    ElMessage.success('已重置，下个交易日 17:50 自动开始调仓')
    await load()
  } catch {
    ElMessage.error('重置失败')
  } finally {
    resetting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.paper-panel { display: flex; flex-direction: column; gap: 16px; }
.paper-panel.mobile { gap: 12px; }
.sweep-meta { font-size: 12px; color: var(--text-3); }
.side-tag { font-size: 11px; padding: 2px 10px; border-radius: var(--radius-pill); }
.side-tag.buy  { background: var(--up-soft); color: var(--up); }
.side-tag.sell { background: var(--down-soft); color: var(--down); }
.reset-box { display: flex; flex-direction: column; gap: 6px; }
.reset-tip { font-size: 12px; color: var(--text-3); line-height: 1.5; }

.score-block {
  min-width: 132px;
  padding: 10px 14px;
  border-radius: var(--radius);
  background: var(--bg-2);
}
.score-label { font-size: 11px; color: var(--text-3); margin-bottom: 2px; }
.score-num { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
.score-sub { font-size: 11px; color: var(--text-4); font-weight: 400; margin-left: 4px; }
</style>
