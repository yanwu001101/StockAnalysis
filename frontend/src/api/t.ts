import request from './request'

// 短线做 T(日内 T+0)建议
export interface TSignal {
  code: string
  name: string
  price: number | null
  pct_change: number | null
  vwap: number | null
  day_high: number | null
  day_low: number | null
  day_open: number | null
  prev_close: number | null
  intraday_pos: number | null
  vwap_dev: number | null
  amplitude: number | null
  action: 'positive_t' | 'negative_t' | 'wait' | 'no_data'
  action_label: string
  strength: number
  buy_zone: [number, number] | null
  sell_zone: [number, number] | null
  reasons: string[]
  risks: string[]
  data_time: string | null
  disclaimer: string
}

export function getTSignal(code: string): Promise<TSignal> {
  return request.get(`/t/stock/${code}`)
}

export function getTSignalBatch(codes: string[]): Promise<TSignal[]> {
  return request.post('/t/batch', { codes })
}
