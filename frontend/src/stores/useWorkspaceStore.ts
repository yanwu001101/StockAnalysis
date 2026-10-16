/**
 * Workspace store — everything the terminal shell owns:
 * watchlist (persisted), AI alert feed, panel collapse states, and the
 * polling of system stats / market overview for the top bar and command
 * center. Kept separate from the analysis store (single responsibility).
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { quantApi } from '@/services/quantApi'
import type { MarketOverview, SystemStats } from '@/types/quant'

const WATCHLIST_KEY = 'alphaforge.watchlist.v1'
const STATS_POLL_MS = 15_000
const OVERVIEW_POLL_MS = 60_000
const MAX_ALERTS = 50

export type AlertSeverity = 'info' | 'warning' | 'critical'

export interface AlertEvent {
  id: string
  symbol: string
  message: string
  severity: AlertSeverity
  timestamp: number
}

export interface WatchEntry {
  symbol: string
  /** 最近一次结论评分；null = 尚未分析 */
  lastScore: number | null
  lastSignal: string | null
  updatedAt: number | null
}

function loadWatchlist(): WatchEntry[] {
  try {
    const raw = localStorage.getItem(WATCHLIST_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (item): item is WatchEntry =>
        typeof item === 'object' &&
        item !== null &&
        typeof (item as WatchEntry).symbol === 'string',
    )
  } catch {
    return []
  }
}

function persistWatchlist(entries: WatchEntry[]): void {
  try {
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify(entries))
  } catch {
    // 隐私模式下 localStorage 可能不可写——看名单退化为会话级
  }
}

let alertSeq = 0

function nextAlertId(): string {
  alertSeq += 1
  return `alert-${Date.now()}-${alertSeq}`
}

export const useWorkspaceStore = defineStore('workspace', () => {
  // ---------------------------------------------------------------- state
  const watchlist = ref<WatchEntry[]>(loadWatchlist())
  const alerts = ref<AlertEvent[]>([])
  const collapsedPanels = ref<Record<string, boolean>>({})
  const stats = ref<SystemStats | null>(null)
  const overview = ref<MarketOverview | null>(null)
  const statsError = ref<string>('')
  const overviewError = ref<string>('')
  /** 全局命令面板（Ctrl/⌘+K） */
  const paletteOpen = ref<boolean>(false)
  const paletteQuery = ref<string>('')

  let statsTimer: ReturnType<typeof setInterval> | null = null
  let overviewTimer: ReturnType<typeof setInterval> | null = null

  // ------------------------------------------------------------ watchlist

  function addToWatchlist(symbol: string): void {
    const normalized = symbol.replace(/\D/g, '').padStart(6, '0').slice(-6)
    if (watchlist.value.some((entry) => entry.symbol === normalized)) return
    watchlist.value = [
      ...watchlist.value,
      { symbol: normalized, lastScore: null, lastSignal: null, updatedAt: null },
    ]
    persistWatchlist(watchlist.value)
  }

  function removeFromWatchlist(symbol: string): void {
    watchlist.value = watchlist.value.filter((entry) => entry.symbol !== symbol)
    persistWatchlist(watchlist.value)
  }

  function isWatched(symbol: string): boolean {
    return watchlist.value.some((entry) => entry.symbol === symbol)
  }

  /** 结论到达时更新看名单条目，并触发异动日志。 */
  function recordVerdict(symbol: string, score: number, signal: string): void {
    const entry = watchlist.value.find((item) => item.symbol === symbol)
    const previousScore = entry?.lastScore ?? null
    if (entry !== undefined) {
      watchlist.value = watchlist.value.map((item) =>
        item.symbol === symbol
          ? { ...item, lastScore: score, lastSignal: signal, updatedAt: Date.now() }
          : item,
      )
      persistWatchlist(watchlist.value)
    }
    // 异动规则：首次结论、评分大幅波动（>=10）、或强信号
    if (entry === undefined) return
    if (previousScore === null || Math.abs(score - previousScore) >= 10) {
      pushAlert(
        symbol,
        previousScore === null
          ? `AI 首次结论：评分 ${score}（${signal}）`
          : `AI 评分变动 ${previousScore} -> ${score}（${signal}）`,
        signal === 'BUY' ? 'critical' : signal === 'SELL' ? 'warning' : 'info',
      )
    }
  }

  // ---------------------------------------------------------------- alerts

  function pushAlert(symbol: string, message: string, severity: AlertSeverity): void {
    alerts.value = [
      { id: nextAlertId(), symbol, message, severity, timestamp: Date.now() },
      ...alerts.value,
    ].slice(0, MAX_ALERTS)
  }

  function clearAlerts(): void {
    alerts.value = []
  }

  // ---------------------------------------------------------------- panels

  function togglePanel(id: string): void {
    collapsedPanels.value = {
      ...collapsedPanels.value,
      [id]: !isCollapsed(id),
    }
  }

  function isCollapsed(id: string): boolean {
    return collapsedPanels.value[id] === true
  }

  // ---------------------------------------------------------------- palette

  function openPalette(): void {
    paletteOpen.value = true
    paletteQuery.value = ''
  }

  function closePalette(): void {
    paletteOpen.value = false
    paletteQuery.value = ''
  }

  // ------------------------------------------------------------ polling

  async function refreshStats(): Promise<void> {
    try {
      stats.value = await quantApi.getStats()
      statsError.value = ''
    } catch (error: unknown) {
      statsError.value = error instanceof Error ? error.message : '统计获取失败'
    }
  }

  async function refreshOverview(): Promise<void> {
    try {
      overview.value = await quantApi.getMarketOverview()
      overviewError.value = ''
    } catch (error: unknown) {
      overviewError.value = error instanceof Error ? error.message : '行情概览获取失败'
    }
  }

  function startPolling(): void {
    if (statsTimer === null) {
      void refreshStats()
      statsTimer = setInterval(() => void refreshStats(), STATS_POLL_MS)
    }
    if (overviewTimer === null) {
      void refreshOverview()
      overviewTimer = setInterval(() => void refreshOverview(), OVERVIEW_POLL_MS)
    }
  }

  function stopPolling(): void {
    if (statsTimer !== null) {
      clearInterval(statsTimer)
      statsTimer = null
    }
    if (overviewTimer !== null) {
      clearInterval(overviewTimer)
      overviewTimer = null
    }
  }

  // ---------------------------------------------------------------- getters

  const watchSymbols = computed<string[]>(() =>
    watchlist.value.map((entry) => entry.symbol),
  )

  /** 顶栏信息流：最近异动 + 系统状态一句话 */
  const tickerItems = computed<string[]>(() => {
    const items = alerts.value.slice(0, 8).map((alert) => `[${alert.symbol}] ${alert.message}`)
    if (stats.value !== null) {
      items.push(
        `系统：今日任务 ${stats.value.total}，成功率 ${(stats.value.successRate * 100).toFixed(0)}%`,
      )
    }
    return items
  })

  return {
    // state
    watchlist,
    alerts,
    collapsedPanels,
    stats,
    overview,
    statsError,
    overviewError,
    paletteOpen,
    paletteQuery,
    // actions
    addToWatchlist,
    removeFromWatchlist,
    isWatched,
    recordVerdict,
    pushAlert,
    clearAlerts,
    togglePanel,
    isCollapsed,
    openPalette,
    closePalette,
    refreshStats,
    refreshOverview,
    startPolling,
    stopPolling,
    // getters
    watchSymbols,
    tickerItems,
  }
})
