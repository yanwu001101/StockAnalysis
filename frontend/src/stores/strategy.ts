import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { StrategyConfig } from '@/types'

const DEFAULT_STRATEGIES: StrategyConfig[] = [
  { id: 'macd_ma', name: 'MACD+均线趋势共振', nameEn: 'MACD+MA', description: 'MACD金叉配合均线多头排列，趋势确认效果最强', enabled: true, weight: 12, icon: 'TrendCharts', color: '#00D4FF' },
  { id: 'multi_factor', name: '多因子价值投资', nameEn: 'Multi-Factor', description: 'ROE+负债率+现金流+成长性综合打分', enabled: true, weight: 25, icon: 'DataAnalysis', color: '#2AE8A4' },
  { id: 'momentum_breakout', name: '动量突破策略', nameEn: 'Momentum', description: '股价突破N日新高+成交量放大确认', enabled: true, weight: 10, icon: 'Top', color: '#FF9F43' },
  { id: 'rsi_rebound', name: 'RSI超卖反弹', nameEn: 'RSI Rebound', description: 'RSI从超卖区回升，捕捉反弹机会', enabled: true, weight: 8, icon: 'Bottom', color: '#A78BFA' },
  { id: 'bollinger_squeeze', name: '布林带收口突破', nameEn: 'Bollinger', description: '布林带收窄后放量突破上轨', enabled: true, weight: 8, icon: 'Minus', color: '#FFC312' },
  { id: 'chip_concentration', name: '筹码集中+机构增持', nameEn: 'Chip+', description: '股东户数减少+机构持仓增加', enabled: true, weight: 10, icon: 'User', color: '#FF6B81' },
  { id: 'dividend_stability', name: '股息率+分红稳定性', nameEn: 'Dividend', description: '高股息+连续多年稳定分红', enabled: true, weight: 8, icon: 'Coin', color: '#FECA57' },
  { id: 'northbound_flow', name: '北向资金流入', nameEn: 'Northbound', description: '外资持续买入的标的', enabled: true, weight: 7, icon: 'Guide', color: '#48DBFB' },
  { id: 'sector_rotation', name: '行业轮动策略', nameEn: 'Rotation', description: '根据动量切换热门行业', enabled: true, weight: 7, icon: 'Refresh', color: '#FF9FF3' },
  { id: 'kdj_rsi_resonance', name: 'KDJ+RSI双指标共振', nameEn: 'KDJ+RSI', description: '两个超买超卖指标同时发出信号', enabled: true, weight: 5, icon: 'Aim', color: '#54A0FF' },
]

export const useStrategyStore = defineStore('strategy', () => {
  const strategies = ref<StrategyConfig[]>([...DEFAULT_STRATEGIES])
  const savedConfigs = ref<{ name: string; config: StrategyConfig[] }[]>([])

  function updateWeight(id: string, weight: number) {
    const s = strategies.value.find(s => s.id === id)
    if (s) s.weight = weight
  }

  function toggleStrategy(id: string) {
    const s = strategies.value.find(s => s.id === id)
    if (s) s.enabled = !s.enabled
  }

  function resetToDefault() {
    strategies.value = DEFAULT_STRATEGIES.map(s => ({ ...s }))
  }

  function saveConfig(name: string) {
    savedConfigs.value.push({
      name,
      config: strategies.value.map(s => ({ ...s })),
    })
    localStorage.setItem('savedStrategies', JSON.stringify(savedConfigs.value))
  }

  function loadConfig(name: string) {
    const cfg = savedConfigs.value.find(c => c.name === name)
    if (cfg) strategies.value = cfg.config.map(s => ({ ...s }))
  }

  function loadFromStorage() {
    const stored = localStorage.getItem('savedStrategies')
    if (stored) {
      try { savedConfigs.value = JSON.parse(stored) } catch {}
    }
  }

  function getEnabledStrategies() {
    return strategies.value.filter(s => s.enabled)
  }

  function getConfigMap(): Record<string, { enabled: boolean; weight: number }> {
    const map: Record<string, { enabled: boolean; weight: number }> = {}
    strategies.value.forEach(s => {
      map[s.id] = { enabled: s.enabled, weight: s.weight }
    })
    return map
  }

  return {
    strategies, savedConfigs,
    updateWeight, toggleStrategy, resetToDefault,
    saveConfig, loadConfig, loadFromStorage,
    getEnabledStrategies, getConfigMap,
  }
})
