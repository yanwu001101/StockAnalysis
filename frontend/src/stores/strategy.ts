import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { StrategyConfig } from '@/types'

const DEFAULT_STRATEGIES: StrategyConfig[] = [
  { id: 'piotroski_f', name: 'Piotroski F-Score', nameEn: 'Piotroski', description: '9 项基本面打分筛优质低估股', enabled: true, weight: 12, icon: 'DataAnalysis', color: '#2AE8A4' },
  { id: 'magic_formula', name: '神奇公式 Magic Formula', nameEn: 'Magic Formula', description: 'ROC + 盈利收益率双排名', enabled: true, weight: 10, icon: 'Coin', color: '#FFC312' },
  { id: 'quality_factor', name: '质量因子 Quality', nameEn: 'Quality', description: '稳定高 ROE + 现金流质量 + 低杠杆', enabled: true, weight: 18, icon: 'Medal', color: '#00D4FF' },
  { id: 'momentum_12_1', name: '12-1 月动量', nameEn: 'Momentum 12-1', description: '过去 12 个月剔除最近 1 个月的累计收益', enabled: true, weight: 10, icon: 'Top', color: '#FF9F43' },
  { id: 'low_volatility', name: '低波动异象', nameEn: 'Low Volatility', description: '60 日波动率最低分位 + 正趋势确认', enabled: true, weight: 8, icon: 'Minus', color: '#A78BFA' },
  { id: 'pead', name: 'PEAD 盈余惊喜后漂移', nameEn: 'PEAD', description: '财报 YoY 增速跳变 + 近期公告事件触发', enabled: true, weight: 10, icon: 'Bell', color: '#FF6B81' },
  { id: 'northbound_smart_money', name: '北向资金追踪', nameEn: 'Northbound', description: '外资 5/10/20 日加仓 + 持股比例提升', enabled: true, weight: 8, icon: 'Guide', color: '#48DBFB' },
  { id: 'lhb_followup', name: '龙虎榜机构跟随', nameEn: 'LHB Followup', description: '机构席位净买 + 买入主导比', enabled: true, weight: 8, icon: 'User', color: '#FECA57' },
  { id: 'sector_rotation', name: '行业动量轮动', nameEn: 'Rotation', description: '行业排名前 20% + 个股相对强势', enabled: true, weight: 8, icon: 'Refresh', color: '#FF9FF3' },
  { id: 'technical_resonance', name: '技术共振', nameEn: 'Resonance', description: 'MACD 金叉 + 均线多头 + 量价 + 北向 5 日加仓', enabled: true, weight: 10, icon: 'TrendCharts', color: '#54A0FF' },
  { id: 'turtle_breakout', name: '海龟通道突破', nameEn: 'Turtle', description: '20 日 Donchian 通道突破 + ATR 确认', enabled: true, weight: 6, icon: 'TopRight', color: '#10B981' },
  { id: 'boll_kdj_resonance', name: '布林 + KDJ 共振', nameEn: 'Boll+KDJ', description: '下轨支撑 + J<20 金叉', enabled: true, weight: 6, icon: 'Aim', color: '#F472B6' },
  { id: 'macd_divergence', name: 'MACD 背离', nameEn: 'MACD Div', description: '顶背离 / 底背离反转信号', enabled: true, weight: 5, icon: 'CaretBottom', color: '#FB923C' },
  { id: 'max_reversal', name: '彩票异象反向', nameEn: 'MAX', description: '22 日最大单日涨幅高 → 看空', enabled: true, weight: 5, icon: 'WarningFilled', color: '#EC4899' },
  { id: 'hurst_trend', name: 'Hurst 趋势性', nameEn: 'Hurst', description: 'H>0.55 趋势 / H<0.45 反转', enabled: true, weight: 4, icon: 'DataLine', color: '#8B5CF6' },
  { id: 'turnover_dryup', name: '缩量企稳', nameEn: 'Dry-up', description: '换手低位 + 价格不破新低,A 股底部信号', enabled: true, weight: 4, icon: 'Bottom', color: '#06B6D4' },
  { id: 'fifty_two_week_high', name: '52 周新高效应', nameEn: '52WH', description: '接近 52 周高点 + 趋势确认', enabled: true, weight: 7, icon: 'TopRight', color: '#22C55E' },
  { id: 'accruals_quality', name: '应计利润质量', nameEn: 'Accruals', description: '低应计 / 高现金质量', enabled: true, weight: 6, icon: 'Money', color: '#0EA5E9' },
  { id: 'asset_growth', name: '资产增长异象', nameEn: 'Asset Growth', description: '扩张过快后续低收益', enabled: true, weight: 5, icon: 'PieChart', color: '#EAB308' },
  { id: 'chip_concentration', name: '筹码集中度', nameEn: 'Chip Conc', description: 'VWAP 带宽 + 价格在成本上方', enabled: true, weight: 5, icon: 'Discount', color: '#A855F7' },
  { id: 'ma_stack_breakout', name: '均线粘合突破', nameEn: 'MA Stack', description: '5/10/20/30/60 粘合后向上突破,主升浪', enabled: true, weight: 6, icon: 'Histogram', color: '#F43F5E' },
  { id: 'multi_horizon_momentum', name: '多维度动量', nameEn: 'MultiMom', description: '5/21/63/252-21 多窗口 + Sharpe + 一致性', enabled: true, weight: 10, icon: 'Promotion', color: '#0891B2' },
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
