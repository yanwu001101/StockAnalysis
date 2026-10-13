import { afterEach, describe, expect, it } from 'vitest'
import { createApp, defineComponent, h, type App } from 'vue'
import PredictionPanel from '@/components/charts/PredictionPanel.vue'
import type { PredictionResult } from '@/types'

let app: App | undefined
let host: HTMLDivElement | undefined
afterEach(() => { app?.unmount(); host?.remove() })

function render(overrides: Partial<PredictionResult> = {}) {
  const prediction: PredictionResult = {
    code: '000001', name: '测试', price: 10, probabilityUp: 89.5, probabilityDown: 10.5,
    confidence: 72, signal: 'bullish', signalLabel: '偏多', compositeDirection: 0.5,
    dimensions: [], keyDrivers: [], riskWarnings: [], timeHorizon: '3-5 个交易日', ...overrides,
  }
  host = document.createElement('div'); document.body.appendChild(host)
  app = createApp(PredictionPanel, { prediction })
  const passthrough = defineComponent({ setup: (_, { slots }) => () => h('span', slots.default?.()) })
  app.component('ElTag', passthrough); app.component('ElIcon', passthrough)
  app.mount(host)
  return host
}

describe('prediction panel rendered financial semantics', () => {
  it('does not label an uncalibrated score as a percent or a probability', () => {
    const panel = render()
    expect(panel.textContent).toContain('89.5 / 100')
    expect(panel.textContent).toContain('72.0 / 100')
    expect(panel.textContent).not.toContain('89.5%')
    expect(panel.textContent).not.toContain('72%')
    expect(panel.querySelector('h4')?.textContent).toBe('趋势评分 · 未校准')
    expect(panel.querySelector('.prob-bar')).toBeNull()
  })

  it('renders calibrated history with missing returns as — and never calls the complement down probability', () => {
    const panel = render({ calibration: { insufficient: false, n: 100, win_rate: 0, avg_return: null } })
    expect(panel.textContent).toContain('T+5 上涨频率 0.0%')
    expect(panel.textContent).toContain('平均收益 —')
    expect(panel.textContent).toContain('其余样本含持平')
    expect(panel.textContent).not.toContain('100%')
    expect(panel.querySelector('.prob-bar')).not.toBeNull()
  })

  it('shows sample shortage and hides the insufficient-data 50/50 fallback', () => {
    const panel = render({ signalLabel: '数据不足', probabilityUp: 50, probabilityDown: 50, confidence: 0,
      calibration: { insufficient: true, n: 12 } })
    expect(panel.querySelector('[role="status"]')?.textContent).toContain('历史行情不足')
    expect(panel.textContent).toContain('n=12')
    expect(panel.textContent).not.toContain('50.0 / 100')
    expect(panel.querySelector('.conf-value')?.textContent).toBe('—')
  })
})
