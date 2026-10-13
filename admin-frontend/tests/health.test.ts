import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, type App } from 'vue'
import ElementPlus from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import Health from '@/views/monitor/Health.vue'
import { getOverview } from '@/api/monitor'
vi.mock('@/api/monitor', () => ({ getOverview: vi.fn() }))
let app: App | undefined
let host: HTMLDivElement
afterEach(() => { app?.unmount(); host?.remove(); vi.mocked(getOverview).mockReset() })
async function mount() {
  host = document.createElement('div'); document.body.appendChild(host)
  app = createApp(Health); app.use(ElementPlus); app.component('Refresh', Refresh); app.mount(host)
  await Promise.resolve(); await nextTick(); await nextTick()
  return host.textContent || ''
}
describe('health screen evidence and failure presentation', () => {
  it('shows coverage anchor and historical population separately without treating event data as missing daily coverage', async () => {
    vi.mocked(getOverview).mockResolvedValue({ jvm: { heapUsedMB: 0, heapMaxMB: 100, processors: 2, uptimeMs: 0 }, dataService: {
      mysql: { connected: true, freshnessAnchor: { date: '2026-10-09', source: 'LATEST_OBSERVED_MARKET_SESSION', asOf: '2026-10-12', cutoffDate: '2026-10-12', lagCalendarDays: 3, calendarVerified: false, note: '库内参考日' },
        freshness: { daily: { status: 'PARTIAL', historyCodes: 5000, coveredOnAnchor: 500, eligibleUniverse: 5000, latestCoveragePct: 10 },
          financials: { status: 'EVENT_DRIVEN', latestCoveragePct: null } } },
    } })
    const text = await mount()
    expect(text).toContain('库内参考交易日覆盖')
    expect(text).toContain('日历未验证')
    expect(text).toContain('10.0%')
    expect(text).toContain('5000')
    expect(text).toContain('事件驱动')
    expect(text).toContain('不适用')
  })
  it('shows an outage as a failed inspection with unknown connectivity, not fake zero resources', async () => {
    vi.mocked(getOverview).mockRejectedValue(new Error('offline'))
    const text = await mount()
    expect(text).toContain('offline')
    expect(text).toContain('未确认')
    expect(text).not.toContain('断开')
    expect(text).not.toContain('0 / 0 MB')
  })
})
