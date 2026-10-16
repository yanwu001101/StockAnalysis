/**
 * Store tests — WebSocket lifecycle with a fake socket.
 *
 * The only cast in this file is installing the fake WebSocket onto the global;
 * everything under test is exercised through the store's public surface.
 */
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAnalysisStore } from '@/stores/useAnalysisStore'
import type { WsEnvelope } from '@/types/quant'

class FakeWebSocket {
  static readonly OPEN = 1
  static instances: FakeWebSocket[] = []

  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  readonly sent: string[] = []

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this)
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.readyState = 3
    this.onclose?.()
  }

  open(): void {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  emit(envelope: WsEnvelope): void {
    this.onmessage?.({ data: JSON.stringify(envelope) })
  }
}

function installFetch(): void {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ taskId: 'task-1', symbol: '600519', status: 'PENDING' }),
  }) as unknown as typeof fetch
}

function installWebSocket(): void {
  globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket
}

beforeEach(() => {
  setActivePinia(createPinia())
  FakeWebSocket.instances = []
  installFetch()
  installWebSocket()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useAnalysisStore', () => {
  it('submits, connects and reaches CONNECTED', async () => {
    const store = useAnalysisStore()
    const taskId = await store.submit('600519')

    expect(taskId).toBe('task-1')
    expect(store.symbol).toBe('600519')
    expect(store.connectionState).toBe('CONNECTING')

    const ws = FakeWebSocket.instances[0]
    expect(ws?.url).toContain('/ws/v1/progress/task-1')
    ws?.open()
    expect(store.connectionState).toBe('CONNECTED')
  })

  it('dispatches progress frames per agentId', async () => {
    const store = useAnalysisStore()
    await store.submit('600519')
    const ws = FakeWebSocket.instances[0]
    ws?.open()

    ws?.emit({
      type: 'progress',
      taskId: 'task-1',
      payload: {
        taskId: 'task-1',
        agentId: 'fundamental',
        agentName: '基本面分析师',
        status: 'RUNNING',
        progress: 0.4,
        message: '读取财报',
        timestamp: 1,
      },
    })
    ws?.emit({
      type: 'progress',
      taskId: 'task-1',
      payload: {
        taskId: 'task-1',
        agentId: 'sentiment',
        agentName: '舆情分析师',
        status: 'RUNNING',
        progress: 0.2,
        message: '抓取新闻',
        timestamp: 2,
      },
    })

    expect(store.agents.fundamental?.progress).toBe(0.4)
    expect(store.agents.fundamental?.thoughts).toEqual(['读取财报'])
    expect(store.agents.sentiment?.message).toBe('抓取新闻')
    expect(store.agentList.map((c) => c.agentId)).toEqual(['fundamental', 'sentiment'])
  })

  it('commits the final verdict exactly once', async () => {
    const store = useAnalysisStore()
    await store.submit('600519')
    const ws = FakeWebSocket.instances[0]
    ws?.open()

    const verdict = {
      rawMetrics: {
        sharpeRatio: 1.2,
        maxDrawdown: -0.1,
        winRate: 0.5,
        totalReturn: 0.2,
        alpha: 0.05,
        beta: 1,
      },
      humanVerdict: {
        score: 70,
        signal: 'BUY' as const,
        reasons: ['好'],
        colorClass: 'text-green' as const,
      },
      chartMarkers: [],
      metricStatus: {
        sharpeRatio: 'VALID' as const,
        maxDrawdown: 'VALID' as const,
        winRate: 'VALID' as const,
        totalReturn: 'VALID' as const,
        alpha: 'VALID' as const,
        beta: 'VALID' as const,
      },
      symbol: '600519',
      candles: [],
      dates: [],
      equityCurve: [],
      trades: [],
      debate: [],
      warnings: [],
    }

    ws?.emit({ type: 'verdict', taskId: 'task-1', payload: verdict })
    expect(store.verdict?.humanVerdict.signal).toBe('BUY')
    expect(store.isRunning).toBe(false)
  })

  it('heartbeats every 30s', async () => {
    const store = useAnalysisStore()
    await store.submit('600519')
    const ws = FakeWebSocket.instances[0]
    ws?.open()

    vi.advanceTimersByTime(30_000)
    expect(ws?.sent).toContain('{"type":"ping"}')
  })

  it('reconnects with exponential backoff after a drop', async () => {
    const store = useAnalysisStore()
    await store.submit('600519')
    const ws = FakeWebSocket.instances[0]
    ws?.open()

    ws?.close()
    expect(store.connectionState).toBe('ERROR')

    vi.advanceTimersByTime(999)
    expect(FakeWebSocket.instances).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(store.connectionState).toBe('CONNECTING')
  })

  it('reset stops reconnecting', async () => {
    const store = useAnalysisStore()
    await store.submit('600519')
    const ws = FakeWebSocket.instances[0]
    ws?.open()

    store.reset()
    ws?.close() // stale socket closing must not schedule a reconnect
    vi.advanceTimersByTime(60_000)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(store.connectionState).toBe('DISCONNECTED')
    expect(store.verdict).toBeNull()
  })
})
