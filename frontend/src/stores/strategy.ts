import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { StrategyConfig } from '@/types'

const DEFAULT_STRATEGIES: StrategyConfig[] = [
  { id: 'piotroski_f', name: 'Piotroski F-Score', nameEn: 'Piotroski', description: '9项基本面打分筛优质低估股 (Piotroski 2000)', enabled: true, weight: 12, icon: 'DataAnalysis', color: '#2AE8A4' },
  { id: 'magic_formula', name: '神奇公式 Magic Formula', nameEn: 'Magic Formula', description: 'ROC + 盈利收益率双排名 (Greenblatt)', enabled: true, weight: 10, icon: 'Coin', color: '#FFC312' },
  { id: 'quality_factor', name: '质量因子 Quality', nameEn: 'Quality', description: '稳定高ROE + 现金流质量 + 低杠杆', enabled: true, weight: 18, icon: 'Medal', color: '#00D4FF' },
  { id: 'momentum_12_1', name: '12-1月动量', nameEn: 'Momentum 12-1', description: '过去12月剔近1月累计收益 (Jegadeesh-Titman)', enabled: true, weight: 10, icon: 'Top', color: '#FF9F43' },
  { id: 'low_volatility', name: '低波动异象', nameEn: 'Low Volatility', description: '60日波动率最低分位 + 正趋势确认 (BAB)', enabled: true, weight: 8, icon: 'Minus', color: '#A78BFA' },
  { id: 'pead', name: 'PEAD 盈余惊喜后漂移', nameEn: 'PEAD', description: '财报YoY增速跳变 + 近期公告事件触发', enabled: true, weight: 10, icon: 'Bell', color: '#FF6B81' },
  { id: 'northbound_smart_money', name: '北向资金追踪', nameEn: 'Northbound', description: '外资 5/10/20 日加仓 + 持股比例提升', enabled: true, weight: 8, icon: 'Guide', color: '#48DBFB' },
  { id: 'lhb_followup', name: '龙虎榜机构跟随', nameEn: 'LHB Followup', description: '机构席位净买 + 买入主导比', enabled: true, weight: 8, icon: 'User', color: '#FECA57' },
  { id: 'sector_rotation', name: '行业动量轮动', nameEn: 'Rotation', description: '行业排名前 20% + 个股相对强势', enabled: true, weight: 8, icon: 'Refresh', color: '#FF9FF3' },
  { id: 'technical_resonance', name: '技术共振', nameEn: 'Resonance', description: 'MACD金叉 + 均线多头 + 量价 + 北向5日加仓', enabled: true, weight: 10, icon: 'TrendCharts', color: '#54A0FF' },
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
