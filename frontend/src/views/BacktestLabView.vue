/**
 * BacktestLabView — /backtest 策略回测实验室。
 *
 * 上半区策略配置（股票池/日期/资金量/费率/滑点，T+1 与整手为引擎内置规则），
 * 下半区左为资金曲线，右为成交流水 + AI 归因（最大回撤大白话解读）。
 *
 * 配置通过 POST /api/v1/analyze 的 backtest 覆盖项下发，跑的还是同一条
 * 确定性回测引擎——不存在第二套计算逻辑。
 */
<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import PanelFrame from '@/components/PanelFrame.vue'
import EquityCurveChart from '@/components/EquityCurveChart.vue'
import TradeTable from '@/components/TradeTable.vue'
import { useAnalysisStore } from '@/stores/useAnalysisStore'
import { equitySeries, tradeRows } from '@/utils/selectors'

const analysis = useAnalysisStore()
const { verdict, submitting, errorMessage } = storeToRefs(analysis)

const symbol = ref<string>('600519')
const startDate = ref<string>('')
const endDate = ref<string>('')
const initialCapital = ref<string>('1000000')
const commissionRate = ref<string>('0.0003')
const slippage = ref<string>('0.001')

const series = computed(() => equitySeries(verdict.value))
const rows = computed(() => tradeRows(verdict.value))

/** 最大回撤点索引（曲线最低点相对峰值），用于图表标注 */
const drawdownIndex = computed<number | null>(() => {
  if (series.value.values.length === 0) return null
  let peak = Number.NEGATIVE_INFINITY
  let worst = 0
  let worstIndex = 0
  series.value.values.forEach((value, index) => {
    if (value > peak) peak = value
    const drawdown = peak > 0 ? value / peak - 1 : 0
    if (drawdown < worst) {
      worst = drawdown
      worstIndex = index
    }
  })
  return worst < 0 ? worstIndex : null
})

const attribution = computed<string[]>(() => {
  if (verdict.value === null) return []
  return verdict.value.humanVerdict.reasons.filter((reason) =>
    reason.includes('回撤') || reason.includes('夏普') || reason.includes('收益'),
  )
})

const capitalValid = computed<boolean>(() => {
  const value = Number(initialCapital.value)
  return Number.isFinite(value) && value > 0
})

async function run(): Promise<void> {
  const digits = symbol.value.replace(/\D/g, '')
  if (digits.length < 6) return
  const overrides: Record<string, number | string> = {}
  if (capitalValid.value) overrides.initialCapital = Number(initialCapital.value)
  const rate = Number(commissionRate.value)
  if (Number.isFinite(rate) && rate >= 0) overrides.commissionRate = rate
  const slip = Number(slippage.value)
  if (Number.isFinite(slip) && slip >= 0) overrides.slippage = slip
  if (startDate.value) overrides.startDate = startDate.value
  if (endDate.value) overrides.endDate = endDate.value
  await analysis.submit(digits.padStart(6, '0').slice(-6), overrides)
}
</script>

<template>
  <div class="lab">
    <!-- 上半区：策略配置 -->
    <PanelFrame id="lab-config" title="策略配置">
      <form class="config" @submit.prevent="run">
        <label>
          <span>股票代码</span>
          <input v-model="symbol" class="num" type="text" maxlength="10" placeholder="600519" />
        </label>
        <label>
          <span>开始日期</span>
          <input v-model="startDate" class="num" type="date" />
        </label>
        <label>
          <span>结束日期</span>
          <input v-model="endDate" class="num" type="date" />
        </label>
        <label>
          <span>初始资金（元）</span>
          <input v-model="initialCapital" class="num" type="text" inputmode="decimal" />
        </label>
        <label>
          <span>佣金费率</span>
          <input v-model="commissionRate" class="num" type="text" inputmode="decimal" />
        </label>
        <label>
          <span>滑点</span>
          <input v-model="slippage" class="num" type="text" inputmode="decimal" />
        </label>
        <div class="config-rules">
          <span>引擎内置规则：</span>
          <span>佣金最低 5 元</span><span>印花税 0.1%（卖出）</span><span>过户费 0.002%（沪市）</span>
          <span>整手 100 股</span><span>T+1</span><span>信号基于 t-1 日收盘，t 日开盘成交</span>
        </div>
        <button class="run-btn" type="submit" :disabled="submitting">
          {{ submitting ? '回测进行中…' : '运行回测' }}
        </button>
      </form>
      <p v-if="errorMessage" class="lab-error">{{ errorMessage }}</p>
    </PanelFrame>

    <!-- 下半区：曲线 + 流水/归因 -->
    <div class="lab-bottom">
      <PanelFrame id="lab-curve" title="资金曲线" :meta="verdict ? `${series.values.length} 个交易日` : ''">
        <EquityCurveChart
          v-if="series.values.length > 0"
          :dates="series.dates"
          :values="series.values"
          :drawdown-index="drawdownIndex"
        />
        <p v-else class="state-loading">运行回测后在此展示资金曲线。</p>
      </PanelFrame>

      <div class="lab-right">
        <PanelFrame id="lab-trades" title="交易流水" :meta="`${rows.length} 笔`">
          <TradeTable :rows="rows" />
        </PanelFrame>
        <PanelFrame id="lab-attribution" title="AI 归因（大白话）">
          <ul v-if="attribution.length > 0" class="attribution">
            <li v-for="(reason, index) in attribution" :key="index">{{ reason }}</li>
          </ul>
          <p v-else class="state-loading">回测完成后，AI 会用大白话解读收益来源与最大回撤。</p>
        </PanelFrame>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lab {
  display: grid;
  grid-template-rows: auto 1fr;
  gap: var(--space-3);
  height: 100%;
  min-height: 0;
}

.config {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--space-3);
  align-items: end;
}

.config label {
  display: grid;
  gap: var(--space-1);
  font-size: 11px;
  color: var(--text-muted);
}

.config input {
  background: var(--bg-app);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  padding: var(--space-1) var(--space-2);
  outline: none;
  height: 28px;
}

.config input:focus {
  border-color: var(--accent);
}

.config-rules {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  font-size: 11px;
  color: var(--text-muted);
}

.config-rules span {
  border: 1px solid var(--border-subtle);
  border-radius: 3px;
  padding: 0 6px;
}

.run-btn {
  grid-column: 1 / -1;
  justify-self: start;
  background: var(--accent);
  border: none;
  border-radius: var(--radius-sm);
  color: #fff;
  font-size: 13px;
  padding: var(--space-2) var(--space-5);
  cursor: pointer;
}

.run-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.lab-error {
  margin: var(--space-2) 0 0;
  color: var(--verdict-red);
  font-size: 12px;
}

.lab-bottom {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: var(--space-3);
  min-height: 0;
}

.lab-right {
  display: grid;
  grid-template-rows: 1.3fr 1fr;
  gap: var(--space-3);
  min-height: 0;
}

.attribution {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: var(--space-2);
}

.attribution li {
  font-size: 12px;
  color: var(--text-secondary);
  border-left: 2px solid var(--accent);
  padding-left: var(--space-2);
  line-height: 1.7;
}

.state-loading {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
