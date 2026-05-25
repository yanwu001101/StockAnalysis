<template>
  <div class="page-container">
    <div class="backtest-header glass-card">
      <h2>策略回测</h2>
      <p class="desc">基于历史数据验证策略有效性</p>
    </div>

    <div class="config-grid">
      <div class="glass-card config-card">
        <h3>回测参数</h3>
        <el-form label-position="top" size="small">
          <el-form-item label="股票代码 (留空=组合回测)">
            <el-input v-model="config.stockCode" placeholder="例如 600519，留空跑十大策略组合" clearable>
              <template #append v-if="config.stockCode">单股择时</template>
            </el-input>
          </el-form-item>
          <el-form-item label="策略">
            <el-select v-model="config.strategyId" style="width: 100%;">
              <el-option v-for="s in strategyStore.strategies" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="开始日期">
            <el-date-picker v-model="config.startDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 100%;" />
          </el-form-item>
          <el-form-item label="结束日期">
            <el-date-picker v-model="config.endDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 100%;" />
          </el-form-item>
          <el-form-item label="初始资金 (万元)">
            <el-input-number v-model="config.initialCapital" :min="10" :max="10000" :step="10" style="width: 100%;" />
          </el-form-item>
          <el-form-item label="每期选股数量" v-if="!config.stockCode">
            <el-input-number v-model="config.topN" :min="1" :max="50" :step="1" style="width: 100%;" />
          </el-form-item>
          <el-button type="primary" :loading="loading" @click="runTest" style="width: 100%;">
            <el-icon><TrendCharts /></el-icon>开始回测
          </el-button>
        </el-form>
      </div>

      <div class="result-area" v-if="result">
        <div class="glass-card metrics-card">
          <h3>回测结果</h3>
          <div class="metrics-grid">
            <div class="metric-item">
              <span class="metric-label">总收益率</span>
              <span class="metric-value" :class="result.totalReturn >= 0 ? 'price-up' : 'price-down'">
                {{ result.totalReturn >= 0 ? '+' : '' }}{{ (result.totalReturn * 100).toFixed(2) }}%
              </span>
            </div>
            <div class="metric-item">
              <span class="metric-label">年化收益率</span>
              <span class="metric-value" :class="result.annualizedReturn >= 0 ? 'price-up' : 'price-down'">
                {{ result.annualizedReturn >= 0 ? '+' : '' }}{{ (result.annualizedReturn * 100).toFixed(2) }}%
              </span>
            </div>
            <div class="metric-item">
              <span class="metric-label">最大回撤</span>
              <span class="metric-value price-down">-{{ (result.maxDrawdown * 100).toFixed(2) }}%</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">夏普比率</span>
              <span class="metric-value brand-text">{{ result.sharpeRatio.toFixed(2) }}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">胜率</span>
              <span class="metric-value warn-text">{{ (result.winRate * 100).toFixed(1) }}%</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">交易次数</span>
              <span class="metric-value">{{ result.tradeCount }}</span>
            </div>
          </div>
        </div>

        <div class="glass-card picks-card" v-if="(result as any).picks?.length">
          <h3>本次回测选股（按策略综合分排名）</h3>
          <div class="picks-grid">
            <span v-for="(code, idx) in (result as any).picks" :key="code" class="pick-chip"
                  @click="$router.push(`/stock/${code}`)">
              <span class="pick-rank">{{ idx + 1 }}</span>
              <span class="pick-code">{{ code }}</span>
            </span>
          </div>
        </div>

        <div class="glass-card curve-card">
          <h3>收益曲线</h3>
          <div ref="curveChartRef" style="height: 350px;"></div>
        </div>

        <div class="glass-card trades-card" v-if="(result as any).trades?.length">
          <div class="trades-head">
            <h3>交易明细 <span class="trades-count">共 {{ (result as any).trades.length }} 笔</span></h3>
            <div class="trades-filter">
              <el-radio-group v-model="tradeSideFilter" size="small">
                <el-radio-button value="all">全部</el-radio-button>
                <el-radio-button value="buy">仅买入</el-radio-button>
                <el-radio-button value="sell">仅卖出</el-radio-button>
              </el-radio-group>
            </div>
          </div>
          <el-table :data="filteredTrades" stripe size="small" max-height="420"
                    :row-style="{ cursor: 'pointer' }"
                    @row-click="(row: any) => row.code && $router.push(`/stock/${row.code}`)">
            <el-table-column label="日期" prop="date" width="120" sortable />
            <el-table-column label="代码" prop="code" width="100" />
            <el-table-column label="方向" width="80">
              <template #default="{ row }">
                <span :class="['side-tag', row.side]">
                  {{ row.side === 'buy' ? '买入' : row.side === 'sell' ? '卖出' : row.side }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="价格" width="100" align="right">
              <template #default="{ row }">{{ row.price != null ? Number(row.price).toFixed(2) : '—' }}</template>
            </el-table-column>
            <el-table-column label="股数" width="120" align="right">
              <template #default="{ row }">{{ row.shares != null ? formatNumber(row.shares, 0) : '—' }}</template>
            </el-table-column>
            <el-table-column label="盈亏" width="120" align="right">
              <template #default="{ row }">
                <span v-if="row.pnl == null" class="dim">—</span>
                <span v-else :class="row.pnl >= 0 ? 'price-up' : 'price-down'">
                  {{ row.pnl >= 0 ? '+' : '' }}{{ formatNumber(row.pnl, 0) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="120">
              <template #default="{ row }">
                <span class="dim" v-if="row.reason === 'end_of_window'">期末强平</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>

    <el-empty v-if="!loading && !result" description="设置回测参数后点击「开始回测」" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { runBacktest } from '@/api/strategy'
import { useStrategyStore } from '@/stores/strategy'
import { useRefreshable } from '@/composables/useRefreshable'
import { formatNumber } from '@/utils/format'
import * as echarts from 'echarts'
import type { BacktestResult } from '@/types'

const strategyStore = useStrategyStore()
const loading = ref(false)
const result = ref<BacktestResult | null>(null)
const curveChartRef = ref<HTMLElement>()
const tradeSideFilter = ref<'all' | 'buy' | 'sell'>('all')

const filteredTrades = computed(() => {
  const all = ((result.value as any)?.trades ?? []) as any[]
  if (tradeSideFilter.value === 'all') return all
  return all.filter(t => t.side === tradeSideFilter.value)
})

const config = reactive({
  stockCode: '',
  strategyId: 'quality_factor',
  startDate: '2025-01-01',
  endDate: '2025-12-31',
  initialCapital: 100,
  topN: 10,
})

async function runTest() {
  loading.value = true
  try {
    const body: any = {
      strategyId: config.strategyId,
      startDate: config.startDate,
      endDate: config.endDate,
      initialCapital: config.initialCapital * 10000,    // 万元 -> 元
    }
    if (config.stockCode.trim()) {
      body.stockCode = config.stockCode.trim().padStart(6, '0')
    } else {
      body.topN = config.topN
      body.strategyConfig = strategyStore.getConfigMap()
    }
    result.value = await runBacktest(body)
    ElMessage.success(config.stockCode ? `${config.stockCode} 择时回测完成` : '组合回测完成')
    nextTick(renderCurve)
  } catch {
    ElMessage.error('回测失败')
  } finally {
    loading.value = false
  }
}

function renderCurve() {
  if (!curveChartRef.value || !result.value?.equityCurve?.length) return
  const root = getComputedStyle(document.documentElement)
  const brand = root.getPropertyValue('--brand').trim() || '#07C160'
  const text3 = root.getPropertyValue('--text-3').trim() || '#888888'
  const line = root.getPropertyValue('--line').trim() || '#E5E5E5'
  const surface = root.getPropertyValue('--surface').trim() || '#FFFFFF'

  const chart = echarts.init(curveChartRef.value)
  const data = result.value.equityCurve
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 60, right: 30, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: data.map(d => d.date),
      axisLabel: { color: text3, fontSize: 10 },
      axisLine: { lineStyle: { color: line } } },
    yAxis: { type: 'value',
      splitLine: { lineStyle: { color: line } },
      axisLabel: { color: text3 } },
    series: [{
      type: 'line',
      data: data.map(d => d.value),
      smooth: true,
      symbol: 'none',
      lineStyle: { color: brand, width: 2 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: hexToRgba(brand, 0.18) },
        { offset: 1, color: hexToRgba(brand, 0.02) },
      ]) },
    }],
    tooltip: { trigger: 'axis',
      backgroundColor: surface,
      borderColor: line,
      textStyle: { color: root.getPropertyValue('--text').trim() || '#191919' } },
  })
}

function hexToRgba(hex: string, alpha: number): string {
  const m = hex.replace('#', '')
  const v = m.length === 3
    ? m.split('').map(c => c + c).join('')
    : m
  const r = parseInt(v.slice(0, 2), 16)
  const g = parseInt(v.slice(2, 4), 16)
  const b = parseInt(v.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

useRefreshable('回测', runTest, { immediate: false, autoRefresh: false })
</script>

<style scoped>
.backtest-header { padding: 20px 24px; margin-bottom: 16px; }
.backtest-header h2 { margin: 0; font-size: 20px; color: var(--text-primary); }
.desc { margin: 4px 0 0; font-size: 13px; color: var(--text-muted); }
.config-grid { display: grid; grid-template-columns: 320px 1fr; gap: 16px; }
.config-card { padding: 20px; }
.config-card h3 { margin: 0 0 16px; font-size: 15px; color: var(--text-primary); }
.strategy-checks { display: flex; flex-direction: column; gap: 4px; }
.result-area { display: flex; flex-direction: column; gap: 16px; }
.metrics-card { padding: 20px; }
.metrics-card h3 { margin: 0 0 16px; font-size: 15px; color: var(--text-primary); }
.metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.metric-item { display: flex; flex-direction: column; gap: 4px; }
.metric-label { font-size: 12px; color: var(--text-muted); }
.metric-value { font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }
.curve-card { padding: 20px; }
.curve-card h3 { margin: 0 0 12px; font-size: 15px; color: var(--text-primary); }
.picks-card { padding: 20px; }
.picks-card h3 { margin: 0 0 12px; font-size: 15px; color: var(--text-primary); }
.picks-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.trades-card { padding: 20px; margin-top: 16px; }
.trades-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 12px; }
.trades-card h3 { margin: 0; font-size: 15px; color: var(--text); }
.trades-count { margin-left: 8px; font-size: 12px; color: var(--text-3); font-weight: 400; }
.side-tag { font-size: 11px; padding: 2px 10px; border-radius: var(--radius-pill); }
.side-tag.buy  { background: var(--up-soft); color: var(--up); }
.side-tag.sell { background: var(--down-soft); color: var(--down); }
.dim { color: var(--text-3); }
.pick-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  background: var(--brand-soft);
  border: 1px solid transparent;
  border-radius: 16px;
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}
.pick-chip:hover { background: var(--surface-hover); }
.pick-rank {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px;
  border-radius: 50%;
  background: var(--brand);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}
.pick-code { font-variant-numeric: tabular-nums; }
@media (max-width: 1000px) { .config-grid { grid-template-columns: 1fr; } }
</style>
