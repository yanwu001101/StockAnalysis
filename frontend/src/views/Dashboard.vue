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
                <th class="t-right">最新价</th>
                <th class="t-right">涨跌幅</th>
                <th class="t-center">评分</th>
                <th class="t-center">信号</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in topStocks" :key="row.code" class="row" @click="goStock(row)">
                <td class="t-rank num">{{ i + 1 }}</td>
                <td><span class="stock-name">{{ row.name }}</span></td>
                <td class="mono dim">{{ row.code }}</td>
                <td class="dim">{{ row.industry }}</td>
                <td class="t-right num" :class="row.change >= 0 ? 'price-up' : 'price-down'">{{ row.price }}</td>
                <td class="t-right num" :class="row.changePercent >= 0 ? 'price-up' : 'price-down'">
                  {{ row.changePercent >= 0 ? '+' : '' }}{{ row.changePercent }}%
                </td>
                <td class="t-center">
                  <span class="score-pill" :class="scoreCls(row.compositeScore)">{{ row.compositeScore }}</span>
                </td>
                <td class="t-center">
                  <span class="sig" :class="row.signal">{{ sigText(row.signal) }}</span>
                </td>
              </tr>
              <tr v-if="!topStocks.length">
                <td colspan="8" class="empty">暂无数据 · 请确认后端服务已启动</td>
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
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useMarketStore } from '@/stores/market'
import { useSettingsStore } from '@/stores/settings'
import * as echarts from 'echarts'

const router = useRouter()
const marketStore = useMarketStore()
const settings = useSettingsStore()

const northboundChartRef = ref<HTMLElement>()
const sectorChartRef = ref<HTMLElement>()
const topStocks = computed(() => marketStore.topStocks || [])
const indices = computed(() => marketStore.indices || [])
const activeRank = ref<'gainers' | 'losers' | 'active'>('gainers')
const currentRank = computed(() => {
  if (activeRank.value === 'gainers') return marketStore.gainers || []
  if (activeRank.value === 'losers') return marketStore.losers || []
  return marketStore.mostActive || []
})

const summaryCards = computed(() => {
  const s: any = marketStore.summary
  return [
    { label: '上涨家数', foot: `下跌 ${s?.downCount ?? '—'}`, value: s?.upCount ?? '—', cls: 'price-up' },
    { label: '涨停家数', foot: `跌停 ${s?.downLimit ?? '—'}`, value: s?.upLimit ?? '—', cls: 'price-up' },
    { label: '平均涨跌', foot: '全市场算术平均',
      value: s ? ((s.avgChange >= 0 ? '+' : '') + s.avgChange + '%') : '—',
      cls: s && s.avgChange >= 0 ? 'price-up' : 'price-down' },
    { label: '领涨板块', foot: '日涨幅第一', value: s?.hotSectors?.[0]?.name ?? '—', cls: '' },
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

let refreshTimer: number | null = null

onMounted(async () => {
  await marketStore.fetchAll()
  refreshTimer = window.setInterval(() => marketStore.fetchAll(), settings.refreshInterval * 1000)
  nextTick(() => {
    const t = chartTokens()
    if (northboundChartRef.value && marketStore.northboundFlow.length) {
      const chart = echarts.init(northboundChartRef.value)
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
      const chart = echarts.init(sectorChartRef.value)
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
  })
})

onBeforeUnmount(() => {
  if (refreshTimer !== null) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
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
</style>
