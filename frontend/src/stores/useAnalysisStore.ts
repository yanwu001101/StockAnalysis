/**
 * Analysis store — the single owner of the WebSocket lifecycle.
 *
 * State machine: DISCONNECTED -> CONNECTING -> CONNECTED -> ERROR -> (backoff)
 *                               ^                              |
 *                               +------------------------------+
 *
 * Guarantees:
 *  - client heartbeat every 30s; a silent server for 90s forces a reconnect;
 *  - reconnect uses exponential backoff (1s -> 30s cap) and never gives up
 *    while a task is still running;
 *  - frames dispatch per agentId into a keyed map, so the four agent cards
 *    update independently;
 *  - the final QuantVerdictPayload commits to `verdict` exactly once.
 *
 * Stale sockets are invalidated with a generation counter: a reset() or a new
 * submit() bumps it, and every handler from an older generation no-ops. This
 * is what keeps "close old socket" from scheduling a reconnect afterwards.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { quantApi } from '@/services/quantApi'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import type {
  AgentId,
  AgentProgressPayload,
  BacktestOverrides,
  QuantVerdictPayload,
  WsEnvelope,
} from '@/types/quant'

export type WsConnectionState = 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED' | 'ERROR'

export interface AgentCardState {
  agentId: AgentId
  agentName: string
  status: AgentProgressPayload['status']
  progress: number
  message: string
  updatedAt: number
  /** Rolling log of this agent's messages ("streaming thoughts"). */
  thoughts: string[]
}

const HEARTBEAT_INTERVAL_MS = 30_000
const SERVER_SILENCE_LIMIT_MS = 90_000
const BACKOFF_BASE_MS = 1_000
const BACKOFF_CAP_MS = 30_000
const THOUGHTS_LIMIT = 30

const AGENT_ORDER: readonly AgentId[] = ['fundamental', 'sentiment', 'technical', 'risk']

function isAgentId(value: unknown): value is AgentId {
  return typeof value === 'string' && (AGENT_ORDER as readonly string[]).includes(value)
}

function parseEnvelope(raw: string): WsEnvelope | null {
  try {
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) return null
    const envelope = parsed as Partial<WsEnvelope>
    if (typeof envelope.type !== 'string' || typeof envelope.taskId !== 'string') return null
    return envelope as WsEnvelope
  } catch {
    return null
  }
}

export const useAnalysisStore = defineStore('analysis', () => {
  // ---------------------------------------------------------------- state
  const connectionState = ref<WsConnectionState>('DISCONNECTED')
  const taskId = ref<string | null>(null)
  const symbol = ref<string>('')
  const agents = ref<Partial<Record<AgentId, AgentCardState>>>({})
  const verdict = ref<QuantVerdictPayload | null>(null)
  const errorMessage = ref<string>('')
  const submitting = ref<boolean>(false)
  /** K 线图上被选中的交易日（YYYY-MM-DD）——左右面板联动的核心状态 */
  const selectedDate = ref<string | null>(null)

  // ------------------------------------------------------------ internals
  let socket: WebSocket | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectAttempt = 0
  let lastServerFrameAt = 0
  let generation = 0

  function clearTimers(): void {
    if (heartbeatTimer !== null) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function startHeartbeat(): void {
    if (heartbeatTimer !== null) clearInterval(heartbeatTimer)
    heartbeatTimer = setInterval(() => {
      const ws = socket
      if (ws === null || ws.readyState !== WebSocket.OPEN) return
      ws.send(JSON.stringify({ type: 'ping' }))
      if (Date.now() - lastServerFrameAt > SERVER_SILENCE_LIMIT_MS) {
        // Server went quiet: tear the socket down, the close handler reconnects.
        ws.close()
      }
    }, HEARTBEAT_INTERVAL_MS)
  }

  function scheduleReconnect(): void {
    if (taskId.value === null) return
    const delay = Math.min(BACKOFF_BASE_MS * 2 ** reconnectAttempt, BACKOFF_CAP_MS)
    reconnectAttempt += 1
    reconnectTimer = setTimeout(() => {
      const id = taskId.value
      if (id !== null) void openSocket(id)
    }, delay)
  }

  async function openSocket(id: string): Promise<void> {
    clearTimers()
    connectionState.value = 'CONNECTING'
    const mine = (generation += 1)
    const ws = new WebSocket(quantApi.progressSocket(id))
    socket = ws

    ws.onopen = (): void => {
      if (mine !== generation) {
        ws.close()
        return
      }
      reconnectAttempt = 0
      connectionState.value = 'CONNECTED'
      lastServerFrameAt = Date.now()
      startHeartbeat()
    }

    ws.onmessage = (event: MessageEvent<string>): void => {
      if (mine !== generation) return
      lastServerFrameAt = Date.now()
      const envelope = parseEnvelope(String(event.data))
      if (envelope !== null) dispatch(envelope)
    }

    ws.onerror = (): void => {
      if (mine !== generation) return
      errorMessage.value = '实时连接异常，正在自动重连…'
    }

    ws.onclose = (): void => {
      if (mine !== generation) return
      socket = null
      clearTimers()
      connectionState.value = 'ERROR'
      scheduleReconnect()
    }
  }

  function dispatch(envelope: WsEnvelope): void {
    switch (envelope.type) {
      case 'progress': {
        const payload = envelope.payload as AgentProgressPayload
        if (isAgentId(payload.agentId)) applyProgress(payload)
        return
      }
      case 'verdict': {
        const payload = envelope.payload as QuantVerdictPayload
        verdict.value = payload
        // 联动看名单：更新评分并可能产生异动日志
        useWorkspaceStore().recordVerdict(
          payload.symbol,
          payload.humanVerdict.score,
          payload.humanVerdict.signal,
        )
        return
      }
      case 'heartbeat': {
        return // liveness only
      }
      case 'error': {
        const payload = envelope.payload as { message?: string }
        errorMessage.value = payload.message ?? '分析失败，请稍后重试'
        return
      }
      default:
        return
    }
  }

  function applyProgress(payload: AgentProgressPayload): void {
    const current = agents.value[payload.agentId]
    const thoughts = current?.thoughts ?? []
    agents.value = {
      ...agents.value,
      [payload.agentId]: {
        agentId: payload.agentId,
        agentName: payload.agentName,
        status: payload.status,
        progress: payload.progress,
        message: payload.message,
        updatedAt: payload.timestamp,
        thoughts: [...thoughts, payload.message].slice(-THOUGHTS_LIMIT),
      },
    }
  }

  // ---------------------------------------------------------------- actions

  async function submit(
    nextSymbol: string,
    backtest?: BacktestOverrides,
  ): Promise<string | null> {
    submitting.value = true
    errorMessage.value = ''
    try {
      const response = await quantApi.submit(nextSymbol, backtest)
      reset()
      taskId.value = response.taskId
      symbol.value = response.symbol
      await openSocket(response.taskId)
      return response.taskId
    } catch (error: unknown) {
      errorMessage.value =
        error instanceof Error ? error.message : '提交失败，请检查股票代码后重试'
      return null
    } finally {
      submitting.value = false
    }
  }

  function reset(): void {
    generation += 1 // invalidate every live handler before closing
    clearTimers()
    const stale = socket
    socket = null
    if (stale !== null) stale.close()
    reconnectAttempt = 0
    connectionState.value = 'DISCONNECTED'
    taskId.value = null
    symbol.value = ''
    agents.value = {}
    verdict.value = null
    errorMessage.value = ''
    selectedDate.value = null
  }

  function setSelectedDate(date: string | null): void {
    selectedDate.value = date
  }

  // ---------------------------------------------------------------- getters
  const agentList = computed<AgentCardState[]>(() =>
    AGENT_ORDER.map((id) => agents.value[id]).filter(
      (card): card is AgentCardState => card !== undefined,
    ),
  )

  const overallProgress = computed<number>(() => {
    if (agentList.value.length === 0) return 0
    const total = agentList.value.reduce((sum, card) => sum + card.progress, 0)
    return total / agentList.value.length
  })

  const isRunning = computed<boolean>(
    () => verdict.value === null && (taskId.value !== null || submitting.value),
  )

  return {
    // state
    connectionState,
    taskId,
    symbol,
    agents,
    verdict,
    errorMessage,
    submitting,
    selectedDate,
    // actions
    submit,
    reset,
    setSelectedDate,
    // getters
    agentList,
    overallProgress,
    isRunning,
  }
})
