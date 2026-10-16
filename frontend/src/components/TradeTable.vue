/**
 * TradeTable — 回测成交流水。
 *
 * 买入/卖出配对展示，费用合计与已实现盈亏（红涨绿跌）。
 * 纯展示；数据由 tradeRows 选择器预处理。
 */
<script setup lang="ts">
import type { TradeRow } from '@/utils/selectors'

defineProps<{
  rows: readonly TradeRow[]
}>()

function pnlClass(value: number | null): string {
  if (value === null || value === 0) return 'pnl-zero'
  return value > 0 ? 'pnl-pos' : 'pnl-neg'
}

function formatPnl(value: number | null): string {
  if (value === null) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`
}

function formatPnlPct(value: number | null): string {
  if (value === null) return '—'
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
}
</script>

<template>
  <div class="trade-table">
    <table v-if="rows.length > 0">
      <thead>
        <tr>
          <th>日期</th>
          <th>方向</th>
          <th>股数</th>
          <th>成交价</th>
          <th>费用</th>
          <th>盈亏</th>
          <th>收益率</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.key">
          <td class="num">{{ row.date }}</td>
          <td :class="row.side === 'BUY' ? 'up' : 'down'">{{ row.side === 'BUY' ? '买入' : '卖出' }}</td>
          <td class="num">{{ row.shares.toLocaleString() }}</td>
          <td class="num">{{ row.price.toFixed(2) }}</td>
          <td class="num">{{ row.fees.toFixed(2) }}</td>
          <td class="num" :class="pnlClass(row.pnl)">{{ formatPnl(row.pnl) }}</td>
          <td class="num" :class="pnlClass(row.pnlPct)">{{ formatPnlPct(row.pnlPct) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="empty">区间内没有成交记录。调整信号阈值或扩大日期范围后重试。</p>
  </div>
</template>

<style scoped>
.trade-table {
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

th {
  text-align: left;
  font-weight: 500;
  color: var(--text-muted);
  font-size: 11px;
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--border-subtle);
  white-space: nowrap;
}

td {
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--border-subtle);
  white-space: nowrap;
}

tbody tr:hover {
  background: var(--bg-hover);
}

.empty {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
