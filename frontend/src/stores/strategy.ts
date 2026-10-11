import { defineStore } from 'pinia'
import { ref, watch, onScopeDispose } from 'vue'
import { useUserStore } from '@/stores/user'
import { getStrategyConfig, putStrategyConfig } from '@/api/strategyConfig'
import type { CloudStrategyConfig, WeightMap } from '@/api/strategyConfig'
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
  { id: 'ashare_short_reversal', name: 'A股短期反转', nameEn: 'A Reversal', description: '10 日超跌 + 质量锚定，规避追高过热', enabled: true, weight: 7, icon: 'RefreshLeft', color: '#14B8A6' },
  { id: 'conservative_formula', name: '保守公式', nameEn: 'Conservative', description: '低波动 + 质量 + 正趋势，偏稳健持仓', enabled: true, weight: 8, icon: 'Lock', color: '#64748B' },
  { id: 'fund_price_divergence', name: '资金价量背离', nameEn: 'Flow Divergence', description: '主力资金与价格背离，识别吸筹/派发', enabled: true, weight: 7, icon: 'Switch', color: '#0EA5E9' },
  { id: 'rsrs_timing', name: 'RSRS支撑阻力强度', nameEn: 'RSRS', description: '高低价回归强度，判断突破质量和支撑转弱', enabled: true, weight: 6, icon: 'Connection', color: '#2563EB' },
  { id: 'trend_pullback_stop', name: '趋势回撤止盈', nameEn: 'Trail Stop', description: '趋势内回撤低吸 + ATR 移动止盈/破位减仓', enabled: true, weight: 7, icon: 'SetUp', color: '#DC2626' },
  { id: 'daily_momentum_reversal_t', name: '日频动量反转T', nameEn: 'Daily T', description: '捕捉1-2日动量，过热后提示高抛/别追', enabled: true, weight: 8, icon: 'Lightning', color: '#F97316' },
  { id: 'growth_trend_accelerator', name: '成长趋势加速', nameEn: 'Growth Trend', description: '业绩加速 + 趋势确认，偏收益进攻', enabled: true, weight: 9, icon: 'Rocket', color: '#22C55E' },
]

export const useStrategyStore = defineStore('strategy', () => {
  const user = useUserStore()
  const strategies = ref<StrategyConfig[]>(DEFAULT_STRATEGIES.map(s => ({ ...s })))
  const savedConfigs = ref<{ name: string; config: StrategyConfig[] }[]>([])
  const syncStatus = ref<'local' | 'loading' | 'synced' | 'saving' | 'error' | 'conflict'>('local')
  const syncMessage = ref('仅保存在本机')
  const hasLegacy = ref(!!localStorage.getItem('savedStrategies'))
  let owner: number | null = null
  let generation = 0
  let version = 0
  let revision = 0
  let dirty = false
  let ready = false
  let applying = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let saveFlight: Promise<void> | null = null
  const key = () => `strategy-config-v1:${owner ?? 'guest'}`

  function withWeights(map: WeightMap | null | undefined): StrategyConfig[] {
    return DEFAULT_STRATEGIES.map(s => {
      const item = map?.[s.id]
      return { ...s, ...(item && typeof item.enabled === 'boolean' && Number.isFinite(item.weight)
        && item.weight >= 0 && item.weight <= 1000 ? item : {}) }
    })
  }
  function toMap(items: StrategyConfig[]): WeightMap {
    return Object.fromEntries(items.map(s => [s.id, { enabled: s.enabled, weight: s.weight }]))
  }
  function snapshot(): CloudStrategyConfig {
    return { version, config: toMap(strategies.value),
      presets: savedConfigs.value.map(s => ({ name: s.name, config: toMap(s.config) })) }
  }
  function persist() {
    try { localStorage.setItem(key(), JSON.stringify({ ...snapshot(), dirty })) }
    catch { syncMessage.value = '本地空间不足，配置未保存；请导出或释放存储空间' }
  }
  function apply(data: CloudStrategyConfig) {
    applying = true
    try {
      strategies.value = withWeights(data.config)
      savedConfigs.value = (Array.isArray(data.presets) ? data.presets : []).slice(0, 20)
        .filter(p => typeof p.name === 'string' && p.name.trim())
        .map(p => ({ name: p.name, config: withWeights(p.config) }))
      version = Number.isSafeInteger(data.version) && data.version >= 0 ? data.version : 0
    } finally { applying = false }
  }
  function loadFromStorage() {
    try {
      const data = JSON.parse(localStorage.getItem(key()) || 'null')
      if (data) { apply(data); dirty = data.dirty === true; return }
    } catch { /* Malformed storage is kept for recovery; use defaults in memory. */ }
    apply({ version: 0, config: null, presets: [] }); dirty = false
  }
  function schedule() {
    clearTimeout(timer)
    if (owner != null && ready) timer = setTimeout(() => { void saveToCloud() }, 500)
  }
  watch([strategies, savedConfigs], () => {
    if (applying) return
    revision++; dirty = true; persist(); schedule()
    if (owner == null) { syncStatus.value = 'local'; syncMessage.value = '仅保存在本机' }
  }, { deep: true, flush: 'sync' })

  async function hydrateCloud(replaceLocal = false) {
    if (owner == null) return
    const ticket = generation
    const localRevision = revision
    ready = false
    syncStatus.value = 'loading'; syncMessage.value = '正在读取云端配置'
    try {
      const cloud = await getStrategyConfig()
      if (ticket !== generation) return
      // Editing during a GET is not permission to overwrite those new local edits.
      if ((dirty || revision !== localRevision) && cloud.version !== version && !replaceLocal) {
        syncStatus.value = 'conflict'; syncMessage.value = '云端版本已变化，本地改动已保留；可加载云端后重新调整'
        return
      }
      if (replaceLocal && revision !== localRevision) {
        syncStatus.value = 'conflict'; syncMessage.value = '加载期间有新修改，本地改动已保留'; return
      }
      if (!dirty || replaceLocal) {
        if (cloud.config != null || replaceLocal) apply(cloud)
        dirty = false
      }
      version = cloud.version
      ready = true; persist()
      syncStatus.value = cloud.config ? 'synced' : 'local'
      syncMessage.value = cloud.config ? `已同步云端 v${version}` : '本地默认配置，修改后自动同步'
      if (dirty) schedule()
    } catch (error: any) {
      if (ticket !== generation) return
      syncStatus.value = 'error'; syncMessage.value = error?.message || '云端不可用，本地配置仍可使用'
    }
  }

  async function saveToCloud(): Promise<void> {
    clearTimeout(timer)
    if (saveFlight) return saveFlight
    if (owner == null || !dirty) return
    if (!ready) { await hydrateCloud(); return }
    const ticket = generation, editing = revision, payload = snapshot()
    syncStatus.value = 'saving'; syncMessage.value = '正在保存云端配置'
    const promise = (async () => {
      try {
        const cloud = await putStrategyConfig(payload)
        if (ticket !== generation) return
        version = cloud.version
        dirty = revision !== editing
        persist()
        syncStatus.value = 'synced'; syncMessage.value = `已同步云端 v${version}`
        if (dirty) schedule()
      } catch (error: any) {
        if (ticket !== generation) return
        const conflict = error?.response?.status === 409 || error?.response?.data?.code === 409 || error?.code === 409
        syncStatus.value = conflict ? 'conflict' : 'error'
        syncMessage.value = conflict ? '云端版本已变化，本地改动已保留；请加载云端后重新调整' : '同步失败，本地改动已保留'
        if (conflict) ready = false
        persist()
      }
    })()
    saveFlight = promise
    try { await promise } finally { if (saveFlight === promise) saveFlight = null }
  }

  watch(() => [user.token, user.userInfo?.id] as const, ([token, id]) => {
    clearTimeout(timer)
    generation++; saveFlight = null; ready = false
    owner = token && id != null ? id : null
    version = 0; revision = 0
    loadFromStorage()
    syncStatus.value = 'local'; syncMessage.value = '仅保存在本机'
    if (owner != null) void hydrateCloud()
  }, { immediate: true })
  onScopeDispose(() => clearTimeout(timer))

  function updateWeight(id: string, weight: number) {
    const item = strategies.value.find(s => s.id === id)
    if (item && Number.isFinite(weight)) item.weight = Math.max(0, Math.min(1000, weight))
  }
  function setAllStrategiesEnabled(enabled: boolean) { strategies.value.forEach(s => { s.enabled = enabled }) }
  function resetToDefault() { strategies.value = DEFAULT_STRATEGIES.map(s => ({ ...s })) }
  function saveConfig(name: string) {
    name = name.trim().slice(0, 80)
    if (!name) return
    const preset = { name, config: strategies.value.map(s => ({ ...s })) }
    const index = savedConfigs.value.findIndex(s => s.name === name)
    if (index >= 0) savedConfigs.value[index] = preset
    else if (savedConfigs.value.length < 20) savedConfigs.value.push(preset)
    else { syncMessage.value = '最多保存20个方案，请先删除旧方案'; return }
  }
  function deleteConfig(name: string) { savedConfigs.value = savedConfigs.value.filter(c => c.name !== name) }
  function loadConfig(name: string) {
    const cfg = savedConfigs.value.find(c => c.name === name)
    if (cfg) strategies.value = cfg.config.map(s => ({ ...s }))
  }
  function importLegacyConfigs() {
    // Explicit opt-in migration: never upload a shared browser's legacy data into another account silently.
    try {
      const old = JSON.parse(localStorage.getItem('savedStrategies') || '[]')
      if (!Array.isArray(old)) return
      for (const item of old.slice(0, 20)) {
        if (typeof item.name !== 'string' || !Array.isArray(item.config)) continue
        const map = toMap(item.config.filter((s: StrategyConfig) => typeof s?.id === 'string'))
        if (!savedConfigs.value.some(p => p.name === item.name) && savedConfigs.value.length < 20)
          savedConfigs.value.push({ name: item.name.trim().slice(0, 80), config: withWeights(map) })
      }
    } catch { syncMessage.value = '旧方案格式异常，原始备份已保留' }
  }
  function getConfigMap(): WeightMap { return toMap(strategies.value) }
  return { strategies, savedConfigs, syncStatus, syncMessage, hasLegacy,
    updateWeight, setAllStrategiesEnabled, resetToDefault, saveConfig, deleteConfig, loadConfig,
    loadFromStorage, getConfigMap, hydrateCloud, saveToCloud, importLegacyConfigs }
})
