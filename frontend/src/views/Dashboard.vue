<template>
  <div class="page-container dashboard">
    <header class="page-head rise rise-1">
      <h1>今日盘面</h1>
      <p class="dek">综合评分、北向资金与板块轮动一览</p>
    </header>

    <section class="indices rise rise-1" v-if="indices.length">
      <div class="index-card" v-for="idx in indices" :key="idx.code">
        <div class="index-name">{{ idx.name }}</div>
        <div class="index-price num" :class="idx.changePercent >= 0 ? 'price-up' : 'price-down'">
          {{ idx.price.toFixed(2) }}
        </div>
        <div class="index-change num" :class="idx.changePercent >= 0 ? 'price-up' : 'price-down'">
          {{ idx.changePercent >= 0 ? '+' : '' }}{{ idx.change.toFixed(2) }}
          ({{ idx.changePercent >= 0 ? '+' : '' }}{{ idx.changePercent.toFixed(2) }}%)
        </div>
      </div>
    </section>

    <section class="stats rise rise-2">
      <div class="stat-card" v-for="card in summaryCards" :key="card.label">
        <div class="stat-label">{{ card.label }}</div>
        <div class="stat-value num" :class="card.cls">{{ card.value }}</div>
        <div class="stat-foot">{{ card.foot }}</div>
      </div>
    </section>

    <section class="pro-signal-section rise rise-2">
      <article class="card pro-card">
        <header class="card-head">
          <div>
            <h3>专业预测 <span class="badge-pro">Leading Indicators · T+1~T+5</span></h3>
            <p class="card-sub">无滞后 leading 指标体系 · 输入代码 / 点击热门股查看完整九维矩阵</p>
          </div>
          <div class="pro-input">
            <el-input v-model="proCode" placeholder="输入 6 位股票代码" size="small" maxlength="6"
                      @keydown.enter="goProSignal(proCode)" style="width: 180px;" />
            <el-button type="success" size="small" @click="goProSignal(proCode)">
              <el-icon><Aim /></el-icon>专业预测
            </el-button>
          </div>
        </header>
        <div class="pro-quick">
          <div v-for="row in (topStocks || []).slice(0, 6)" :key="row.code"
               class="pro-tile" @click="router.push(`/pro-signal/${row.code}`)">
            <div class="pro-tile-head">
              <span class="pro-tile-name">{{ row.name }}</span>
              <span class="pro-tile-code">{{ row.code }}</span>
            </div>
            <div class="pro-tile-body">
              <template v-if="proCache[row.code]">
                <span class="pro-tile-label" :class="proCache[row.code].direction">{{ proCache[row.code].label }}</span>
                <span class="pro-tile-prob">{{ proCache[row.code].probabilityUp }}%</span>
              </template>
              <template v-else-if="proLoading[row.code]">
                <span class="pro-tile-loading">···</span>
              </template>
              <template v-else>
                <span class="pro-tile-loading">—</span>
              </template>
            </div>
            <div class="pro-tile-foot">
              <span class="num" :class="row.changePercent >= 0 ? 'price-up' : 'price-down'">
                {{ row.changePercent >= 0 ? '+' : '' }}{{ row.changePercent }}%
              </span>
            </div>
          </div>
        </div>
      </article>
    </section>

    <section class="main-grid">
      <article class="card top-card rise rise-3">
        <header class="card-head">
          <div>
            <h3>高分股票</h3>
            <p class="card-sub">综合评分排名前列</p>
          </div>
          <button class="link-btn" @click="$router.push('/screener')">查看全部 →</button>
        </header>

        <div class="table-wrap">
          <table class="t-table">
            <thead>
              <tr>
                <th class="t-rank">#</th>
                <th>名称</th>
                <th>代码</th>
                <th>行业</th>
                <th class="t-center">最新价</th>
                <th class="t-center">涨跌幅</th>
                <th class="t-center sortable" :class="{ active: sortBy === 'composite' }" @click="toggleSort('composite')">
                  评分 <span class="sort-arrow">{{ sortArrow('composite') }}</span>
                </th>
                <th class="t-center sortable" :class="{ active: sortBy === 'compositeV2' }" @click="toggleSort('compositeV2')">
                  综合策略分
                  <el-tooltip content="22 个策略加权综合分（v2）" placement="top">
                    <el-icon style="vertical-align: -2px;"><InfoFilled /></el-icon>
                  </el-tooltip>
                  <span class="sort-arrow">{{ sortArrow('compositeV2') }}</span>
                </th>
                <th class="t-center">
                  策略评分
                  <el-tooltip content="看多策略数 / 有效策略数 · 触发数" placement="top">
                    <el-icon style="vertical-align: -2px;"><InfoFilled /></el-icon>
                  </el-tooltip>
                </th>
                <th class="t-center">信号</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in sortedTopStocks" :key="row.code" class="row" @click="goStock(row)">
                <td class="t-rank num">{{ i + 1 }}</td>
                <td><span class="stock-name">{{ row.name }}</span></td>
                <td class="mono dim">{{ row.code }}</td>
                <td class="dim">{{ row.industry }}</td>
                <td class="t-center num" :class="row.change >= 0 ? 'price-up' : 'price-down'">{{ row.price }}</td>
                <td class="t-center num" :class="row.changePercent >= 0 ? 'price-up' : 'price-down'">
                  {{ row.changePercent >= 0 ? '+' : '' }}{{ row.changePercent }}%
                </td>
                <td class="t-center">
                  <span class="score-pill" :class="scoreCls(row.compositeScore)">{{ row.compositeScore }}</span>
                </td>
                <td class="t-center">
                  <span v-if="row.compositeScoreV2 !== undefined" class="score-pill" :class="scoreCls(row.compositeScoreV2)">
                    {{ row.compositeScoreV2 }}
                  </span>
                  <span v-else class="dim-load">···</span>
                </td>
                <td class="t-center">
                  <span v-if="row.strategyStats" class="strat-pill" :class="stratCls(row.strategyStats)">
                    {{ row.strategyStats.bullish }}/{{ row.strategyStats.effective }}
                    <span class="strat-trig">· {{ row.strategyStats.triggered }}</span>
                  </span>
                  <span v-else class="dim-load">···</span>
                </td>
                <td class="t-center">
                  <span class="sig" :class="row.signal">{{ sigText(row.signal) }}</span>
                </td>
              </tr>
              <tr v-if="!topStocks.length">
                <td colspan="10" class="empty">暂无数据 · 请确认后端服务已启动</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <aside class="side-stack">
        <div class="card rise rise-3">
          <header class="card-head compact">
            <h3>市场涨跌榜</h3>
            <el-radio-group v-model="activeRank" size="small">
              <el-radio-button value="gainers">涨幅</el-radio-button>
              <el-radio-button value="losers">跌幅</el-radio-button>
              <el-radio-button value="active">活跃</el-radio-button>
            </el-radio-group>
          </header>
          <div class="rank-list">
            <div v-for="(r, i) in currentRank.slice(0, 10)" :key="r.code" class="rank-row" @click="goStock(r)">
              <span class="rank-i num">{{ i + 1 }}</span>
              <span class="rank-name">{{ r.name }}</span>
              <span class="rank-code mono dim">{{ r.code }}</span>
              <span class="rank-change num" :class="r.changePercent >= 0 ? 'price-up' : 'price-down'">
                {{ r.changePercent >= 0 ? '+' : '' }}{{ r.changePercent }}%
              </span>
            </div>
            <div v-if="!currentRank.length" class="empty">暂无数据</div>
          </div>
        </div>
        <div class="card chart-card rise rise-3">
          <header class="card-head compact">
            <h3>北向资金</h3>
          </header>
          <div ref="northboundChartRef" style="height: 200px;"></div>
        </div>
        <div class="card chart-card rise rise-4">
          <header class="card-head compact">
            <h3>板块涨跌</h3>
          </header>
          <div ref="sectorChartRef" style="height: 240px;"></div>
        </div>
      </aside>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, reactive, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Aim, InfoFilled } from '@element-plus/icons-vue'
import { useMarketStore } from '@/stores/market'
import { useRefreshable } from '@/composables/useRefreshable'
import { getStockProSignal, getStockStrategies } from '@/api/stock'
import * as echarts from 'echarts'

const router = useRouter()
const marketStore = useMarketStore()

const proCode = ref('')
const proCache = reactive<Record<string, any>>({})
const proLoading = reactive<Record<string, boolean>>({})

function goProSignal(code: string) {
  const c = (code || '').trim()
  if (!/^\d{6}$/.test(c)) {
    ElMessage.warning('请输入 6 位股票代码')
    return
  }
  router.push(`/pro-signal/${c}`)
}

async function preloadProSignals() {
  const codes = (marketStore.topStocks || []).slice(0, 6).map((s: any) => s.code)
  await Promise.all(codes.map(async (code) => {
    if (proCache[code] || proLoading[code]) return
    proLoading[code] = true
    try {
      proCache[code] = await getStockProSignal(code)
    } catch {
      proCache[code] = null
    } finally {
      proLoading[code] = false
    }
  }))
}

async function preloadStrategyDetails() {
  const concurrency = 6
  const list = marketStore.topStocks || []
  let idx = 0
  const worker = async () => {
    while (idx < list.length) {
      const i = idx++
      const row: any = list[i]
      if (row.compositeScoreV2 !== undefined) continue
      try {
        const d: any = await getStockStrategies(row.code)
        row.compositeScoreV2 = Math.round(d.total ?? d.composite_score ?? 0)
        row.strategyStats = d.aggregate || null
      } catch {
        row.strategyStats = null
      }
    }
  }
  await Promise.all(Array(concurrency).fill(0).map(() => worker()))
}

function stratCls(stats: any) {
  if (!stats || !stats.effective) return 'low'
  const ratio = stats.bullish / stats.effective
  if (ratio >= 0.5) return 'high'
  if (ratio >= 0.3) return 'mid'
  return 'low'
}

watch(() => marketStore.topStocks, (v) => {
  if (v?.length) {
    preloadProSignals()
    preloadStrategyDetails()
  }
}, { immediate: true })

const northboundChartRef = ref<HTMLElement>()
const sectorChartRef = ref<HTMLElement>()
const topStocks = computed(() => marketStore.topStocks || [])
const indices = computed(() => marketStore.indices || [])
const activeRank = ref<'gainers' | 'losers' | 'active'>('gainers')

const sortBy = ref<'composite' | 'compositeV2'>('composite')
const sortDir = ref<'desc' | 'asc'>('desc')

function toggleSort(field: 'composite' | 'compositeV2') {
  if (sortBy.value === field) {
    sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortBy.value = field
    sortDir.value = 'desc'
  }
}

function sortArrow(field: 'composite' | 'compositeV2') {
  if (sortBy.value !== field) return '⇅'
  return sortDir.value === 'desc' ? '↓' : '↑'
}

const sortedTopStocks = computed(() => {
  const arr = [...topStocks.value]
  arr.sort((a, b) => {
    const va = sortBy.value === 'composite' ? (a.compositeScore ?? -1) : (a.compositeScoreV2 ?? -1)
    const vb = sortBy.value === 'composite' ? (b.compositeScore ?? -1) : (b.compositeScoreV2 ?? -1)
    const diff = vb - va
    return sortDir.value === 'desc' ? diff : -diff
  })
  return arr
})
const currentRank = computed(() => {
  if (activeRank.value === 'gainers') return marketStore.gainers || []
  if (activeRank.value === 'losers') return marketStore.losers || []
  return marketStore.mostActive || []
})

const summaryCards = computed(() => {
  const s: any = marketStore.summary
  const top = marketStore.topStocks || []
  const highCount = top.filter((r: any) => (r.compositeScore || 0) >= 60).length
  const bullishCount = top.filter((r: any) => r.signal === 'bullish').length
  return [
    { label: '上涨家数', foot: `下跌 ${s?.downCount ?? '—'}`, value: s?.upCount ?? '—', cls: 'price-up' },
    { label: '涨停家数', foot: `跌停 ${s?.downLimit ?? '—'}`, value: s?.upLimit ?? '—', cls: 'price-up' },
    { label: '平均涨跌', foot: '全市场算术平均',
      value: s ? ((s.avgChange >= 0 ? '+' : '') + s.avgChange + '%') : '—',
      cls: s && s.avgChange >= 0 ? 'price-up' : 'price-down' },
    { label: '领涨板块', foot: '日涨幅第一', value: s?.hotSectors?.[0]?.name ?? '—', cls: '' },
    { label: '高分股票', foot: `综合分≥60`, value: top.length ? `${highCount}/${top.length}` : '—', cls: highCount >= top.length / 2 ? 'price-up' : '' },
    { label: '看多策略', foot: `Top 列表中`, value: top.length ? `${bullishCount}/${top.length}` : '—', cls: bullishCount >= top.length / 2 ? 'price-up' : '' },
  ]
})

function goStock(row: any) { router.push(`/stock/${row.code}`) }
function sigText(s: string) {
  return s === 'bullish' ? '看多' : s === 'bearish' ? '看空' : '中性'
}
function scoreCls(s: number) {
  if (s >= 80) return 'high'
  if (s >= 60) return 'mid'
  return 'low'
}

function chartTokens() {
  const cs = getComputedStyle(document.documentElement)
  return {
    text: cs.getPropertyValue('--text').trim(),
    text3: cs.getPropertyValue('--text-3').trim(),
    line: cs.getPropertyValue('--line').trim(),
    up: cs.getPropertyValue('--up').trim(),
    down: cs.getPropertyValue('--down').trim(),
    bg: cs.getPropertyValue('--surface').trim(),
  }
}

function renderCharts() {
  const t = chartTokens()
  if (northboundChartRef.value && marketStore.northboundFlow.length) {
    const chart = echarts.getInstanceByDom(northboundChartRef.value) || echarts.init(northboundChartRef.value)
    chart.setOption({
      backgroundColor: 'transparent',
      textStyle: { fontFamily: 'system-ui, -apple-system, sans-serif', color: t.text },
      grid: { left: 48, right: 12, top: 12, bottom: 24 },
      xAxis: { type: 'category', data: marketStore.northboundFlow.map((d: any) => d.date),
        axisLabel: { color: t.text3, fontSize: 10 },
        axisLine: { lineStyle: { color: t.line } },
        axisTick: { show: false } },
      yAxis: { type: 'value',
        splitLine: { lineStyle: { color: t.line, type: 'dashed' } },
        axisLabel: { color: t.text3, fontSize: 10 },
        axisLine: { show: false }, axisTick: { show: false } },
      series: [{
        type: 'bar',
        data: marketStore.northboundFlow.map((d: any) => ({
          value: d.netFlow,
          itemStyle: { color: d.netFlow >= 0 ? t.up : t.down, borderRadius: [3, 3, 0, 0] },
        })),
        barWidth: '60%',
      }],
      tooltip: { trigger: 'axis', backgroundColor: t.bg,
        borderColor: t.line, borderWidth: 1, textStyle: { color: t.text } },
    })
  }
  if (sectorChartRef.value && marketStore.sectors.length) {
    const chart = echarts.getInstanceByDom(sectorChartRef.value) || echarts.init(sectorChartRef.value)
    const sorted = [...marketStore.sectors].sort((a, b) => b.change - a.change).slice(0, 10)
    chart.setOption({
      backgroundColor: 'transparent',
      textStyle: { fontFamily: 'system-ui, -apple-system, sans-serif', color: t.text },
      grid: { left: 80, right: 24, top: 8, bottom: 16 },
      xAxis: { type: 'value',
        splitLine: { lineStyle: { color: t.line, type: 'dashed' } },
        axisLabel: { color: t.text3, fontSize: 10 },
        axisLine: { show: false }, axisTick: { show: false } },
      yAxis: { type: 'category', data: sorted.map(s => s.name).reverse(),
        axisLabel: { color: t.text, fontSize: 12 },
        axisLine: { show: false }, axisTick: { show: false } },
      series: [{
        type: 'bar',
        data: sorted.map(s => s.change).reverse(),
        itemStyle: {
          color: (params: any) => {
            const val = sorted[sorted.length - 1 - params.dataIndex]?.change || 0
            return val >= 0 ? t.up : t.down
          },
          borderRadius: [0, 3, 3, 0],
        },
        barWidth: 12,
      }],
      tooltip: { trigger: 'axis', backgroundColor: t.bg,
        borderColor: t.line, borderWidth: 1, textStyle: { color: t.text } },
    })
  }
}

useRefreshable('今日盘面', async () => {
  await marketStore.fetchAll()
  await nextTick()
  renderCharts()
})
</script>

<style scoped>
.page-head { margin-bottom: 18px; }
.page-head h1 { font-size: 22px; font-weight: 600; }
.page-head .dek { margin-top: 4px; color: var(--text-3); font-size: 13px; }

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  padding: 16px 18px;
  box-shadow: var(--shadow-card);
}
.stat-label {
  font-size: 13px;
  color: var(--text-3);
}
.stat-value {
  font-size: 26px;
  font-weight: 600;
  margin-top: 6px;
  letter-spacing: -0.01em;
  color: var(--text);
  line-height: 1.2;
}
.stat-foot {
  font-size: 12px;
  color: var(--text-4);
  margin-top: 4px;
}

.main-grid {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 16px;
}

.card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 18px 20px 8px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
}
.card-head.compact { margin-bottom: 8px; }
.card-head h3 { font-size: 16px; font-weight: 600; }
.card-sub { color: var(--text-3); font-size: 12px; margin-top: 2px; }

.link-btn {
  background: transparent;
  border: 0;
  color: var(--brand);
  font-size: 13px;
  cursor: pointer;
  padding: 4px 0;
}
.link-btn:hover { color: var(--brand-press); }

.table-wrap { margin: 0 -8px; }
.t-table {
  width: 100%;
  border-collapse: collapse;
}
.t-table th {
  text-align: left;
  font-weight: 500;
  font-size: 12px;
  color: var(--text-3);
  padding: 10px 8px;
  border-bottom: 1px solid var(--line);
}
.t-table td {
  padding: 13px 8px;
  font-size: 14px;
  color: var(--text-2);
  border-bottom: 1px solid var(--line);
  vertical-align: middle;
}
.t-table tbody tr:last-child td { border-bottom: 0; }
.row { cursor: pointer; transition: background 0.15s ease; }
.row:hover { background: var(--surface-hover); }
.t-rank { width: 28px; color: var(--text-4); }
.t-right { text-align: right; }
.t-center { text-align: center; }
.stock-name { font-weight: 500; color: var(--text); }
.dim { color: var(--text-3); font-size: 13px; }

.score-pill {
  display: inline-block;
  font-size: 12px; font-weight: 600;
  padding: 2px 9px;
  border-radius: var(--radius-pill);
  font-variant-numeric: tabular-nums;
}
.score-pill.high { background: var(--brand-soft); color: var(--brand); }
.score-pill.mid  { background: var(--warn-soft); color: #B88800; }
.score-pill.low  { background: var(--up-soft); color: var(--up); }

.sig {
  font-size: 12px; font-weight: 500;
  padding: 2px 9px;
  border-radius: var(--radius-pill);
}
.sig.bullish { background: var(--up-soft); color: var(--up); }
.sig.bearish { background: var(--down-soft); color: var(--down); }
.sig.neutral { background: var(--surface-2); color: var(--text-3); }

.empty {
  text-align: center; padding: 60px 0 !important;
  color: var(--text-4) !important;
  font-size: 13px;
}

.side-stack { display: flex; flex-direction: column; gap: 16px; }
.chart-card { padding: 16px 18px; }

.indices {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.index-card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  padding: 12px 14px;
  box-shadow: var(--shadow-card);
}
.index-name { font-size: 12px; color: var(--text-3); }
.index-price { font-size: 18px; font-weight: 600; margin-top: 4px; letter-spacing: -0.01em; }
.index-change { font-size: 12px; margin-top: 2px; }

.rank-list { display: flex; flex-direction: column; }
.rank-row {
  display: grid;
  grid-template-columns: 22px 1fr 50px 60px;
  gap: 8px;
  align-items: center;
  padding: 8px 4px;
  font-size: 13px;
  cursor: pointer;
  border-bottom: 1px solid var(--line);
}
.rank-row:last-child { border-bottom: 0; }
.rank-row:hover { background: var(--surface-hover); }
.rank-i { color: var(--text-4); font-size: 12px; }
.rank-name { font-weight: 500; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank-code { font-size: 11px; }
.rank-change { text-align: right; font-weight: 500; }
.rank-list .empty { padding: 30px 0; text-align: center; color: var(--text-4); font-size: 12px; }

@media (max-width: 1100px) {
  .main-grid { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
  .stats { grid-template-columns: repeat(2, 1fr); }
  .indices { grid-template-columns: repeat(2, 1fr); }
}

.pro-signal-section { margin-bottom: 16px; }
.pro-card { padding: 18px 20px 16px; }

.strat-pill {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 12px; font-weight: 700;
  padding: 2px 9px;
  border-radius: var(--radius-pill);
  font-variant-numeric: tabular-nums;
  line-height: 1.4;
}
.strat-pill.high { background: var(--up-soft); color: var(--up); }
.strat-pill.mid { background: var(--warn-soft); color: #B88800; }
.strat-pill.low { background: var(--surface-2); color: var(--text-3); }
.strat-trig { font-size: 10px; font-weight: 600; opacity: 0.75; }
.dim-load { color: var(--text-4); font-size: 13px; letter-spacing: 1px; }
.pro-card .badge-pro {
  display: inline-block;
  font-size: 11px;
  font-weight: 500;
  margin-left: 8px;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  background: linear-gradient(90deg, rgba(16,185,129,0.12), rgba(8,145,178,0.12));
  color: #0891B2;
  letter-spacing: 0.3px;
}
.pro-input { display: flex; align-items: center; gap: 8px; }
.pro-quick {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 10px;
  margin-top: 12px;
}
.pro-tile {
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
  width: 100%;
  box-sizing: border-box;
}
.pro-tile:hover {
  border-color: var(--brand);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.06);
}
.pro-tile > * { width: 100%; text-align: center; }
.pro-tile-head { margin-bottom: 4px; }
.pro-tile-body { margin: 6px 0; min-height: 24px; }
.pro-tile-foot { margin-top: 2px; }
.pro-tile-name {
  display: block;
  font-size: 13px; font-weight: 600; color: var(--text);
  text-align: center;
}
.pro-tile-code {
  display: block;
  font-size: 11px; color: var(--text-4);
  font-variant-numeric: tabular-nums;
  text-align: center;
  margin-top: 2px;
}
.pro-tile-label {
  display: inline-block;
  font-size: 13px; font-weight: 700;
  padding: 2px 10px; border-radius: var(--radius-pill);
}
.pro-tile-label.up { background: var(--up-soft); color: var(--up); }
.pro-tile-label.down { background: var(--down-soft); color: var(--down); }
.pro-tile-label.flat { background: var(--surface-2); color: var(--text-3); }
.pro-tile-prob {
  display: block;
  font-size: 12px; font-weight: 600; color: var(--text-2);
  font-variant-numeric: tabular-nums;
  margin-top: 3px;
  text-align: center;
}
.pro-tile-loading { display: block; color: var(--text-4); font-size: 12px; text-align: center; }

@media (max-width: 1100px) { .pro-quick { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 600px) { .pro-quick { grid-template-columns: repeat(2, 1fr); } }
</style>
