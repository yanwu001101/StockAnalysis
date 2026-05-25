import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

// A-share users mostly use 红涨绿跌 (red-up). Older int'l-trained users may
// prefer red-down. Either way the underlying semantics (up/down) drive the
// `.price-up` / `.price-down` classes via a [data-color-scheme] attribute on
// :root that theme.css listens for.
export type ColorScheme = 'red-up' | 'red-down'
export type AmountUnit = 'yi' | 'wan'        // 亿 or 万 — display unit for big numbers
export type KlineAdjust = 'qfq' | 'hfq' | 'none'

const lsGet = (k: string, fallback: string) => localStorage.getItem(k) || fallback
const lsNum = (k: string, fallback: number) => Number(localStorage.getItem(k)) || fallback

export const useSettingsStore = defineStore('settings', () => {
  const refreshInterval = ref(lsNum('refreshInterval', 15))
  const defaultLimit = ref(lsNum('defaultLimit', 80))

  const colorScheme = ref<ColorScheme>((lsGet('colorScheme', 'red-up')) as ColorScheme)
  const amountUnit = ref<AmountUnit>((lsGet('amountUnit', 'yi')) as AmountUnit)
  const klineAdjust = ref<KlineAdjust>((lsGet('klineAdjust', 'qfq')) as KlineAdjust)

  // Apply color scheme to :root so theme.css can react via attribute selector.
  function applyColorScheme(v: ColorScheme) {
    document.documentElement.setAttribute('data-color-scheme', v)
  }
  applyColorScheme(colorScheme.value)

  watch(refreshInterval, v => localStorage.setItem('refreshInterval', String(v)))
  watch(defaultLimit, v => localStorage.setItem('defaultLimit', String(v)))
  watch(colorScheme, v => {
    localStorage.setItem('colorScheme', v)
    applyColorScheme(v)
  })
  watch(amountUnit, v => localStorage.setItem('amountUnit', v))
  watch(klineAdjust, v => localStorage.setItem('klineAdjust', v))

  return {
    refreshInterval,
    defaultLimit,
    colorScheme,
    amountUnit,
    klineAdjust,
  }
})
