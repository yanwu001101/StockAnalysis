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

      <!-- 实盘委托单（半自动，里程碑1） -->
      <AppCard title="实盘委托单" sub="半自动：生成清单 → 人工在券商执行 → 勾选标记。系统不会自动下单" compact>
        <template #actions>
          <span v-if="orders?.trade_date" class="sweep-meta">调仓日 {{ orders.trade_date }} · {{ orders.orders.length }} 笔 · 已执行 {{ doneCount }}</span>
          <el-button size="small" plain :loading="ordersLoading" @click="loadOrders">生成委托单</el-button>
          <el-button size="small" plain :disabled="!orders?.orders?.length" @click="exportOrdersCsv">导出 CSV</el-button>
        </template>
        <div v-if="orders?.note" class="order-note">{{ orders.note }}</div>
        <StockTable v-if="orders?.orders?.length" :rows="orders.orders" :columns="orderColumns"
                    :stock="false" :clickable="false" dense row-key="orderKey">
          <template #cell-direction="{ row }">
            <span :class="['side-tag', row.side]">{{ row.direction }}</span>
          </template>
          <template #cell-done="{ row }">
            <el-checkbox :model-value="isDone(row)" @change="toggleDone(row)">已执行</el-checkbox>
          </template>
        </StockTable>
        <div v-else-if="orders" class="order-note">最近一个调仓日（{{ orders.trade_date || '—' }}）没有调仓交易，无需委托。</div>
        <div v-else class="order-note">点击「生成委托单」，按最近一次模拟盘调仓生成实盘委托清单。</div>
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
import { getPaper, getPaperOrders, resetPaper } from '@/api/paper'
import { useDevice } from '@/composables/useDevice'
import { useChartTokens, baseTooltip } from '@/composables/useEcharts'
import type { EChartsOption } from 'echarts'
import type { PaperOrders, PaperOverview } from '@/types'
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

// ---- 实盘委托单（半自动）----
const orders = ref<PaperOrders | null>(null)
const ordersLoading = ref(false)
// 已执行标记只存本机 localStorage：key = paper_orders_done:{调仓日} → { "side:code": true }。
// localStorage 非响应式，用 doneMap 作为响应式镜像驱动重渲染。
const DONE_KEY_PREFIX = 'paper_orders_done:'
const doneMap = ref<Record<string, boolean>>({})

function loadDoneMap() {
  try {
    doneMap.value = JSON.parse(localStorage.getItem(DONE_KEY_PREFIX + (orders.value?.trade_date || '')) || '{}')
  } catch {
    doneMap.value = {}
  }
}

function orderKey(row: { side: string; code: string }): string {
  return `${row.side}:${row.code}`
}

function isDone(row: { side: string; code: string }): boolean {
  return !!doneMap.value[orderKey(row)]
}

const doneCount = computed(() => (orders.value?.orders || []).filter(isDone).length)

function toggleDone(row: { side: string; code: string }) {
  if (!orders.value?.trade_date) return
  const store = { ...doneMap.value }
  if (store[orderKey(row)]) delete store[orderKey(row)]
  else store[orderKey(row)] = true
  doneMap.value = store
  localStorage.setItem(DONE_KEY_PREFIX + orders.value.trade_date, JSON.stringify(store))
}

function exportOrdersCsv() {
  const o = orders.value
  if (!o?.orders?.length || !o.trade_date) return
  const header = ['代码', '名称', '方向', '股数', '参考价', '金额', '原因', '已执行']
  const lines = o.orders.map(r =>
    [r.code, r.name, r.direction, r.shares, r.ref_price, r.amount, r.reason, isDone(r) ? '已执行' : '待执行']
      .map(v => {
        const s = String(v ?? '')
        return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
      }).join(','))
  const csv = '\uFEFF' + [header.join(','), ...lines].join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `委托单_${o.trade_date}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

async function loadOrders() {
  ordersLoading.value = true
  try {
    orders.value = await getPaperOrders()
    loadDoneMap()
  } catch {
    ElMessage.error('委托单生成失败')
  } finally {
    ordersLoading.value = false
  }
}

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

const orderColumns: StockColumn[] = [
  { key: 'code', label: '代码', mobile: 'title' },
  { key: 'name', label: '名称', mobile: 'primary' },
  { key: 'direction', label: '方向', align: 'center', mobile: 'primary' },
  { key: 'shares', label: '股数', type: 'num', digits: 0, mobile: 'secondary' },
  { key: 'ref_price', label: '参考价', type: 'num', digits: 3 },
  { key: 'amount', label: '金额', type: 'num', digits: 0, mobile: 'hidden' },
  { key: 'reason', label: '原因', mobile: 'hidden' },
  { key: 'done', label: '执行标记', align: 'center', mobile: 'secondary' },
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
.order-note { font-size: 12px; color: var(--text-3); line-height: 1.6; margin-bottom: 8px; }

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
