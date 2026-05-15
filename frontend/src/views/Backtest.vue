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
          <el-form-item label="开始日期">
            <el-date-picker v-model="config.startDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 100%;" />
          </el-form-item>
          <el-form-item label="结束日期">
            <el-date-picker v-model="config.endDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 100%;" />
          </el-form-item>
          <el-form-item label="初始资金 (万元)">
            <el-input-number v-model="config.initialCapital" :min="10" :max="10000" :step="10" style="width: 100%;" />
          </el-form-item>
          <el-form-item label="每期选股数量">
            <el-input-number v-model="config.topN" :min="1" :max="50" :step="1" style="width: 100%;" />
          </el-form-item>
          <el-form-item label="使用策略">
            <div class="strategy-checks">
              <el-checkbox v-for="s in strategyStore.strategies" :key="s.id" v-model="s.enabled" :label="s.name" />
            </div>
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
              <span class="metric-value" style="color: #00D4FF;">{{ result.sharpeRatio.toFixed(2) }}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">胜率</span>
              <span class="metric-value" style="color: #FFC312;">{{ (result.winRate * 100).toFixed(1) }}%</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">交易次数</span>
              <span class="metric-value">{{ result.tradeCount }}</span>
            </div>
          </div>
        </div>

        <div class="glass-card curve-card">
          <h3>收益曲线</h3>
          <div ref="curveChartRef" style="height: 350px;"></div>
        </div>
      </div>
    </div>

    <el-empty v-if="!loading && !result" description="设置回测参数后点击「开始回测」" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { runBacktest } from '@/api/strategy'
import { useStrategyStore } from '@/stores/strategy'
import * as echarts from 'echarts'
import type { BacktestResult } from '@/types'

const strategyStore = useStrategyStore()
const loading = ref(false)
const result = ref<BacktestResult | null>(null)
const curveChartRef = ref<HTMLElement>()

const config = reactive({
  startDate: '2024-01-01',
  endDate: '2025-12-31',
  initialCapital: 100,
  topN: 10,
})

async function runTest() {
  loading.value = true
  try {
    result.value = await runBacktest({
      strategyConfig: strategyStore.getConfigMap(),
      startDate: config.startDate,
      endDate: config.endDate,
      initialCapital: config.initialCapital,
      topN: config.topN,
    })
    ElMessage.success('回测完成')
    nextTick(renderCurve)
  } catch {
    ElMessage.error('回测失败')
  } finally {
    loading.value = false
  }
}

function renderCurve() {
  if (!curveChartRef.value || !result.value?.equityCurve?.length) return
  const chart = echarts.init(curveChartRef.value)
  const data = result.value.equityCurve
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 60, right: 30, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: data.map(d => d.date), axisLabel: { color: '#8892A4', fontSize: 10 }, axisLine: { lineStyle: { color: '#2A3A4A' } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(42,58,74,0.3)' } }, axisLabel: { color: '#8892A4' } },
    series: [{
      type: 'line',
      data: data.map(d => d.value),
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#00D4FF', width: 2 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(0,212,255,0.3)' },
        { offset: 1, color: 'rgba(0,212,255,0.02)' },
      ]) },
    }],
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(15,32,53,0.95)', borderColor: 'rgba(0,212,255,0.2)', textStyle: { color: '#E8EDF3' } },
  })
}
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
@media (max-width: 1000px) { .config-grid { grid-template-columns: 1fr; } }
</style>
