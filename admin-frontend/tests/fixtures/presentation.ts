// Local-only UI evidence; every API request is intercepted, no jobs are triggered.
import { createApp, h } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as icons from '@element-plus/icons-vue'
import Health from '@/views/monitor/Health.vue'
import TaskCenter from '@/views/tasks/TaskCenter.vue'
import request from '@/api/request'
import 'element-plus/dist/index.css'
import '@/styles/theme.css'
const scenario = new URLSearchParams(location.search).get('case') || 'health'
const failures: string[] = []
window.addEventListener('error', event => failures.push(event.message))
const overview = {
  jvm: { heapUsedMB: 100, heapMaxMB: 500, processors: 4, uptimeMs: 10000 },
  dataService: { mysql: { connected: true, tables: { stock_kline_daily: 100000 },
    freshnessAnchor: { date: '2026-10-09', source: 'LATEST_OBSERVED_MARKET_SESSION', asOf: '2026-10-12T19:00:00+08:00', cutoffDate: '2026-10-12', lagCalendarDays: 3, calendarVerified: false, note: '参考日为库内已观测行情日，未接交易所日历；满覆盖不代表已追平最新交易日。' },
    freshness: { stock_kline_daily: { status: 'PARTIAL', latestDate: '2026-10-09', anchorDate: '2026-10-09', historyCodes: 5000, eligibleUniverse: 5000, coveredOnAnchor: 500, latestCoveragePct: 10, historyCoveragePct: 100, staleCodes: 4500, missingCodes: 0, universeSource: 'ACTIVE_SPOT_SNAPSHOT', coverageMode: 'SESSION' },
      stock_fundamental: { status: 'EVENT_DRIVEN', latestDate: '2026-09-30', latestCoveragePct: null, coverageMode: 'REPORT' } },
    basisRefresh: { pendingCount: 1, items: [{ table: 'stock_kline_daily', code: '000001', requiredBars: 700 }], scope: 'PROCESS_LOCAL', note: '仅当前进程待办，重启会丢失，不代表全库审计。' } },
    redis: { connected: true, ds_key_count: 0, memory_used_bytes: 0 }, spot: { present: true, rows: 5000, ttl_seconds: 300 } },
}
request.defaults.adapter = async config => {
  const url = config.url || ''
  if (url === '/admin/monitor/overview' && scenario === 'health-error') throw new Error('DEMO：健康检查接口暂不可用')
  const data = url === '/admin/monitor/overview' ? overview : url === '/admin/tasks/jobs'
    ? { jobs: [], running: false, valid_runs: ['postmarket'] } : url === '/admin/tasks/runs'
    ? { items: ['partial', 'failed', 'skipped', 'unknown'].map((status, i) => ({ id: String(i), job: 'postmarket', status,
      started_at: '2026-10-12T19:00:00+08:00', outcome_version: status === 'unknown' ? undefined : 1,
      reason: status === 'unknown' ? '未提供结果证据' : 'DEMO 管线证据', rows: status === 'partial' ? 100 : 0 })) }
    : (() => { throw new Error(`Blocked unexpected API: ${url}`) })()
  return { data: { code: 200, data }, status: 200, statusText: 'OK', headers: {}, config }
}
const app = createApp({ render: () => h('main', { style: 'padding:12px;max-width:100%;box-sizing:border-box' }, [
  h('p', { style: 'font-size:12px' }, `DEMO · ${scenario} · 本地回归，不触发任务`),
  scenario === 'tasks' ? h(TaskCenter) : h(Health),
]) })
app.use(createPinia()).use(ElementPlus)
for (const [name, icon] of Object.entries(icons)) app.component(name, icon)
app.mount('#app')
setTimeout(() => {
  const text = document.getElementById('app')?.textContent || ''
  const passed = !failures.length && document.documentElement.scrollWidth <= window.innerWidth &&
    (scenario === 'tasks' ? ['部分成功', '失败', '已跳过', '结果未确认'].every(word => text.includes(word))
      : scenario === 'health-error' ? text.includes('未确认') && text.includes('接口暂不可用') && !text.includes('断开')
      : text.includes('日历未验证') && text.includes('10.0%') && text.includes('不适用') && text.includes('PROCESS_LOCAL'))
  document.body.dataset.smoke = JSON.stringify({ passed, scenario, viewport: window.innerWidth, contentWidth: document.documentElement.scrollWidth, errors: failures })
}, 3000)
