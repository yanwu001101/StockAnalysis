// Visual regression fixture only. The adapter below blocks all real API calls.
import { createApp, h, nextTick } from 'vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import * as icons from '@element-plus/icons-vue'
import PredictionPanel from '@/components/charts/PredictionPanel.vue'
import BacktestPanel from '@/components/screener/BacktestPanel.vue'
import PaperPanel from '@/components/screener/PaperPanel.vue'
import AppCard from '@/components/ui/AppCard.vue'
import request from '@/api/request'
import type { PredictionResult } from '@/types'
import 'element-plus/dist/index.css'
import '@/styles/theme.css'

const scenario = new URLSearchParams(location.search).get('case') || 'uncalibrated'
const failures: string[] = []
window.addEventListener('error', event => failures.push(event.message))
const testResult = {
  totalReturn: 0, annualizedReturn: null, maxDrawdown: 0, sharpeRatio: null, winRate: null, tradeCount: 0,
  equityCurve: [{ date: '2026-10-08', value: 1 }, { date: '2026-10-09', value: 1 }], trades: [],
  metrics: { status: 'VALID', metric_status: { sharpe_ratio: 'INSUFFICIENT_DATA', win_rate: 'INSUFFICIENT_DATA' },
    metric_reasons: { sharpe_ratio: 'ZERO_RETURN_VOLATILITY', win_rate: 'NO_CLOSED_TRADES' },
    win_rate_basis: 'CLOSED_TRADES', win_rate_sample_size: 0,
    sample_info: { equity_observations: 2, valid_equity_observations: 2, return_observations: 1, expected_return_observations: 1,
      start: '2026-10-08', end: '2026-10-09', periods_per_year: 252 },
    benchmark_info: { status: 'INSUFFICIENT_DATA', reason: 'MISSING_BENCHMARK_ENDPOINT', observations: 1, expected_observations: 2, coverage_ratio: 0.5 } },
}
request.defaults.adapter = async config => {
  const url = config.url || ''
  if (url === '/paper') throw new Error('DEMO：模拟盘接口暂不可用')
  const data = url === '/async/backtest' ? { job_id: 'fixture', status: 'QUEUED' }
    : url === '/async/jobs/fixture' ? { status: 'DONE', result: scenario === 'backtest-error'
      ? { status: 'INSUFFICIENT_DATA', error: 'DEMO：价格截面不足，未生成回测结果' } : testResult }
    : (() => { throw new Error(`Unexpected API request in fixture: ${url}`) })()
  return { data: { code: 200, data }, status: 200, statusText: 'OK', headers: {}, config }
}

const prediction: PredictionResult = {
  code: '000001', name: 'DEMO', price: 10, probabilityUp: 89.5, probabilityDown: 10.5,
  confidence: 72, signal: 'bullish', signalLabel: '偏多', compositeDirection: 0.5,
  dimensions: [], keyDrivers: ['DEMO：信号仅用于验证页面展示'], riskWarnings: ['DEMO：不提供真实行情或投资结论'],
  timeHorizon: '3-5 个交易日',
}
if (scenario === 'insufficient') Object.assign(prediction, {
  signalLabel: '数据不足', probabilityUp: 50, probabilityDown: 50, confidence: 0,
  calibration: { insufficient: true, n: 12 },
})
if (scenario === 'calibrated') prediction.calibration = {
  insufficient: false, n: 120, win_rate: 0.65, avg_return: null, cal_date: '2026-10-09', universe: 500,
}
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { render: () => null } }] })
await router.push('/')
const app = createApp({ render: () => h('main', { style: 'padding:12px;max-width:100%;box-sizing:border-box' }, [
  h('p', { style: 'font-size:12px;color:#956a00' }, `DEMO · ${scenario} · 仅本地展示回归`),
  scenario.startsWith('backtest') ? h(BacktestPanel) : scenario === 'paper-error' ? h(PaperPanel)
    : h(AppCard, null, () => h(PredictionPanel, { prediction })),
]) })
app.use(createPinia()).use(router).use(ElementPlus)
for (const [name, icon] of Object.entries(icons)) app.component(name, icon)
app.mount('#app')
await nextTick()
if (scenario.startsWith('backtest')) (document.querySelector('.config-form .el-button--primary') as HTMLButtonElement)?.click()
setTimeout(() => {
  const text = document.getElementById('app')?.textContent || ''
  const passed = !failures.length && document.documentElement.scrollWidth <= window.innerWidth &&
    (scenario === 'uncalibrated' ? text.includes('89.5 / 100') && !text.includes('89.5%') :
      scenario === 'insufficient' ? text.includes('历史行情不足') && !text.includes('50.0 / 100') :
      scenario === 'backtest-error' ? text.includes('样本不足') && !document.querySelector('.stat-grid:not(.is-loading)') :
      scenario === 'backtest-null' ? text.includes('夏普比率—') && text.includes('0.00%') && text.includes('波动为零') :
      scenario === 'paper-error' ? text.includes('模拟盘数据加载失败') && !text.includes('以 100 万本金启动') : text.includes('平均收益 —'))
  document.body.dataset.smoke = JSON.stringify({ passed, scenario, viewport: window.innerWidth,
    contentWidth: document.documentElement.scrollWidth, errors: failures })
}, 4500)
