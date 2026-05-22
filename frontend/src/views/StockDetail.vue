<template>
  <div class="page-container">
    <div class="stock-header glass-card">
      <div class="header-left">
        <h2 class="stock-title">
          <span class="stock-name">{{ stockInfo.name }}</span>
          <span class="stock-code">{{ stockInfo.code }}</span>
          <el-tag size="small" type="info">{{ stockInfo.industry }}</el-tag>
        </h2>
        <div class="price-row">
          <span class="current-price" :class="stockInfo.change >= 0 ? 'price-up' : 'price-down'">
            {{ stockInfo.price }}
          </span>
          <span class="price-change" :class="stockInfo.change >= 0 ? 'price-up' : 'price-down'">
            {{ stockInfo.change >= 0 ? '+' : '' }}{{ stockInfo.change }}
            ({{ stockInfo.changePercent >= 0 ? '+' : '' }}{{ stockInfo.changePercent }}%)
          </span>
        </div>
      </div>
      <div class="header-right">
        <ScoreGauge :score="compositeScore" :size="90" />
        <div class="action-btns">
          <el-button type="success" size="small" @click="$router.push(`/pro-signal/${code}`)">
            <el-icon><Aim /></el-icon>专业预测
          </el-button>
          <el-button v-if="!isInWatchlist" type="primary" plain size="small" @click="addToWatchlist">
            <el-icon><Star /></el-icon>加自选
          </el-button>
          <el-button v-else type="warning" plain size="small" @click="removeFromWatchlistAction">
            <el-icon><StarFilled /></el-icon>已自选 · 移除
          </el-button>
          <el-button size="small" @click="$router.back()">返回</el-button>
        </div>
      </div>
    </div>

    <div class="content-grid">
      <div class="glass-card kline-card">
        <div class="card-header">
          <h3>K线图</h3>
          <el-radio-group v-model="klinePeriod" size="small">
            <el-radio-button value="daily">日K</el-radio-button>
            <el-radio-button value="weekly">周K</el-radio-button>
          </el-radio-group>
        </div>
        <KLineChart :data="klineData" :height="480" />
      </div>

      <div class="strategy-panel">
        <div class="glass-card radar-card">
          <h3>策略评分雷达</h3>
          <RadarChart :indicators="radarIndicators" :values="radarValues" :height="420" />
        </div>

        <div class="glass-card detail-card">
          <h3>核心指标</h3>
          <div class="metrics-grid">
            <div class="metric-item" v-for="m in coreMetrics" :key="m.label">
              <span class="metric-label">{{ m.label }}</span>
              <span class="metric-value" :style="{ color: m.color }">{{ m.value }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="glass-card strategies-card">
      <h3>多策略评分详情</h3>
      <div class="strategy-grid">
        <div class="strategy-item glass-card" v-for="(score, id) in strategyScores" :key="id">
          <div class="strategy-header">
            <span class="strategy-name">{{ getStrategyName(id) }}</span>
            <el-tag :type="getScoreType(score)" size="small" effect="dark">{{ score }}</el-tag>
          </div>
          <el-progress :percentage="score" :color="getProgressColor(score)" :show-text="false" :stroke-width="6" />
        </div>
      </div>
    </div>

    <PredictionPanel v-if="prediction" :prediction="prediction" />

    <div class="glass-card f10-card" v-loading="f10Loading">
      <div class="card-header">
        <h3>F10 公司资料</h3>
        <el-radio-group v-model="f10Tab" size="small">
          <el-radio-button value="profile">公司概况</el-radio-button>
          <el-radio-button value="holders">十大股东</el-radio-button>
          <el-radio-button value="dividend">分红送转</el-radio-button>
          <el-radio-button value="peers">同业比较</el-radio-button>
        </el-radio-group>
      </div>

      <div v-if="f10Tab === 'profile'" class="f10-profile">
        <div class="profile-grid" v-if="f10Data?.profile && Object.keys(f10Data.profile).length">
          <div class="profile-item" v-for="(v, k) in f10Data.profile" :key="k">
            <span class="profile-label">{{ k }}</span>
            <span class="profile-value">{{ v }}</span>
          </div>
        </div>
        <el-empty v-else description="暂无公司概况数据" :image-size="80" />
      </div>

      <el-table v-else-if="f10Tab === 'holders'" :data="f10Data?.topHolders || []" size="small" stripe
                empty-text="暂无股东数据">
        <el-table-column prop="rank" label="名次" width="60" align="center" />
        <el-table-column prop="name" label="股东名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="type" label="股东性质" width="120" />
        <el-table-column label="持股数量(万)" align="right">
          <template #default="{ row }">{{ (row.shares / 10000).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="ratio" label="持股比例(%)" width="120" align="right">
          <template #default="{ row }">{{ row.ratio?.toFixed(2) || '—' }}</template>
        </el-table-column>
        <el-table-column prop="change" label="持股变动" width="100" />
      </el-table>

      <el-table v-else-if="f10Tab === 'dividend'" :data="f10Data?.dividends || []" size="small" stripe
                empty-text="暂无分红数据">
        <el-table-column prop="annDate" label="公告日" width="110" />
        <el-table-column prop="exDate" label="除权日" width="110" />
        <el-table-column label="现金分红(每10股/元)" align="right">
          <template #default="{ row }">{{ row.cashPer10 ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="送股(每10股)" align="right">
          <template #default="{ row }">{{ row.sharePer10 ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="转增(每10股)" align="right">
          <template #default="{ row }">{{ row.transferPer10 ?? '—' }}</template>
        </el-table-column>
      </el-table>

      <div v-else-if="f10Tab === 'peers'">
        <div class="peer-ranks" v-if="f10Data?.peers?.ranks">
          <div class="rank-chip">
            <span class="rank-label">行业</span>
            <span class="rank-value">{{ f10Data.peers.ranks.industry }} ({{ f10Data.peers.ranks.industrySize }} 家)</span>
          </div>
          <div class="rank-chip" v-if="f10Data.peers.ranks.peByRank">
            <span class="rank-label">PE 排名</span>
            <span class="rank-value">{{ f10Data.peers.ranks.peByRank }} / {{ f10Data.peers.ranks.industrySize }}</span>
          </div>
          <div class="rank-chip" v-if="f10Data.peers.ranks.pbByRank">
            <span class="rank-label">PB 排名</span>
            <span class="rank-value">{{ f10Data.peers.ranks.pbByRank }} / {{ f10Data.peers.ranks.industrySize }}</span>
          </div>
          <div class="rank-chip" v-if="f10Data.peers.ranks.roeRank">
            <span class="rank-label">ROE 排名</span>
            <span class="rank-value">{{ f10Data.peers.ranks.roeRank }} / {{ f10Data.peers.ranks.industrySize }}</span>
          </div>
          <div class="rank-chip" v-if="f10Data.peers.ranks.marketCapRank">
            <span class="rank-label">市值排名</span>
            <span class="rank-value">{{ f10Data.peers.ranks.marketCapRank }} / {{ f10Data.peers.ranks.industrySize }}</span>
          </div>
        </div>
        <el-table :data="f10Data?.peers?.peers || []" size="small" stripe
                  empty-text="暂无同业数据"
                  :row-class-name="(o: any) => o?.row?.isTarget ? 'peer-target' : ''"
                  @row-click="(r: any) => !r.isTarget && $router.push(`/stock/${r.code}`)"
                  :row-style="{ cursor: 'pointer' }">
          <el-table-column prop="name" label="名称" width="100" />
          <el-table-column prop="code" label="代码" width="80" />
          <el-table-column label="最新价" width="80" align="right">
            <template #default="{ row }">{{ row.price.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="涨跌幅" width="90" align="right">
            <template #default="{ row }">
              <span :class="row.changePercent >= 0 ? 'price-up' : 'price-down'">
                {{ row.changePercent >= 0 ? '+' : '' }}{{ row.changePercent }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="pe" label="PE" width="80" align="right">
            <template #default="{ row }">{{ row.pe > 0 ? row.pe.toFixed(2) : '—' }}</template>
          </el-table-column>
          <el-table-column prop="pb" label="PB" width="80" align="right">
            <template #default="{ row }">{{ row.pb > 0 ? row.pb.toFixed(2) : '—' }}</template>
          </el-table-column>
          <el-table-column label="ROE(%)" width="90" align="right">
            <template #default="{ row }">{{ row.roe ? row.roe.toFixed(2) : '—' }}</template>
          </el-table-column>
          <el-table-column label="市值(亿)" width="100" align="right">
            <template #default="{ row }">{{ row.marketCap }}</template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getStockDetail, getStockKLine, getStockStrategies, getStockF10, getStockPrediction } from '@/api/stock'
import { addToWatchlist as addWatchlistApi, removeFromWatchlist as removeWatchlistApi } from '@/api/user'
import { useUserStore } from '@/stores/user'
import { useStrategyStore } from '@/stores/strategy'
import { useRefreshable } from '@/composables/useRefreshable'
import KLineChart from '@/components/charts/KLineChart.vue'
import RadarChart from '@/components/charts/RadarChart.vue'
import ScoreGauge from '@/components/charts/ScoreGauge.vue'
import PredictionPanel from '@/components/charts/PredictionPanel.vue'
import { Star, StarFilled, Aim } from '@element-plus/icons-vue'
import type { KLineData, PredictionResult } from '@/types'

const route = useRoute()
const userStore = useUserStore()
const strategyStore = useStrategyStore()

const code = computed(() => route.params.code as string)
const stockInfo = ref<any>({})
const klineData = ref<KLineData[]>([])
const klinePeriod = ref('daily')
const compositeScore = ref(0)
const strategyScores = ref<Record<string, number>>({})
const prediction = ref<PredictionResult | null>(null)

// F10 state
const f10Tab = ref<'profile' | 'holders' | 'dividend' | 'peers'>('profile')
const f10Data = ref<any>(null)
const f10Loading = ref(false)

// Watchlist membership tracker for the header button
const isInWatchlist = computed(() => {
  const lists = userStore.watchlists || []
  for (const g of lists) {
    if ((g.stocks || []).some((s: any) => String(s.code).padStart(6, '0') === code.value)) {
      return true
    }
  }
  return false
})
const currentGroupId = computed(() => {
  const lists = userStore.watchlists || []
  for (const g of lists) {
    if ((g.stocks || []).some((s: any) => String(s.code).padStart(6, '0') === code.value)) {
      return g.id
    }
  }
  return lists[0]?.id
})

let abortCtrl: AbortController | null = null

const radarIndicators = computed(() =>
  strategyStore.strategies.map(s => ({ name: s.name, max: 100 }))
)
const radarValues = computed(() =>
  strategyStore.strategies.map(s => strategyScores.value[s.id] || 0)
)

const coreMetrics = computed(() => [
  { label: 'ROE', value: (stockInfo.value.roe ?? '--') + '%', color: '#00D4FF' },
  { label: '负债率', value: (stockInfo.value.debtRatio ?? '--') + '%', color: '#FFC312' },
  { label: '现金流', value: stockInfo.value.cashFlowPerShare ?? '--', color: '#2AE8A4' },
  { label: '营收增长', value: (stockInfo.value.revenueGrowth ?? '--') + '%', color: '#A78BFA' },
  { label: '净利润增长', value: (stockInfo.value.profitGrowth ?? '--') + '%', color: '#FF9F43' },
  { label: '毛利率', value: (stockInfo.value.grossMargin ?? '--') + '%', color: '#FF6B81' },
  { label: 'PE', value: stockInfo.value.pe ?? '--', color: '#48DBFB' },
  { label: 'PB', value: stockInfo.value.pb ?? '--', color: '#FECA57' },
])

function getStrategyName(id: string) {
  return strategyStore.strategies.find(s => s.id === id)?.name || id
}
function getScoreType(score: number) {
  return score >= 80 ? 'success' : score >= 60 ? 'warning' : 'danger'
}
function getProgressColor(score: number) {
  return score >= 80 ? '#2AE8A4' : score >= 60 ? '#FFC312' : '#FF4757'
}

async function addToWatchlist() {
  try {
    await addWatchlistApi(0, code.value)
    ElMessage.success('已加入自选股')
    await userStore.fetchWatchlists()
  } catch {}
}

async function removeFromWatchlistAction() {
  try {
    const gid = currentGroupId.value
    await removeWatchlistApi(gid || 0, code.value)
    ElMessage.success('已从自选股移除')
    await userStore.fetchWatchlists()
  } catch {}
}

async function loadData() {
  const c = code.value
  if (!c) return
  abortCtrl?.abort()
  abortCtrl = new AbortController()
  const signal = abortCtrl.signal
  try {
    const [detail, kline, strategies, pred] = await Promise.allSettled([
      getStockDetail(c, signal),
      getStockKLine(c, klinePeriod.value, 250, signal),
      getStockStrategies(c, signal),
      getStockPrediction(c, signal),
    ])
    if (detail.status === 'fulfilled') stockInfo.value = detail.value
    if (kline.status === 'fulfilled') klineData.value = kline.value
    if (strategies.status === 'fulfilled') {
      const s = strategies.value as any
      compositeScore.value = s.total || 0
      strategyScores.value = {}
      Object.entries(s.strategies || {}).forEach(([k, v]: [string, any]) => {
        strategyScores.value[k] = v.score || 0
      })
    }
    if (pred.status === 'fulfilled') prediction.value = pred.value
  } catch {}
  // F10 loads in parallel (slower akshare path).
  loadF10()
}

async function loadF10() {
  const c = code.value
  if (!c) return
  f10Loading.value = true
  try {
    f10Data.value = await getStockF10(c, abortCtrl?.signal)
  } catch {} finally {
    f10Loading.value = false
  }
}

watch(() => code.value, loadData)
watch(klinePeriod, () => {
  if (!code.value) return
  getStockKLine(code.value, klinePeriod.value, 250, abortCtrl?.signal).then(d => klineData.value = d).catch(() => {})
})

useRefreshable('个股详情', loadData)
onMounted(() => {
  // Pull the user's watchlists so the header button reflects "已自选" state
  if (userStore.isLoggedIn) userStore.fetchWatchlists()
})
onBeforeUnmount(() => abortCtrl?.abort())
</script>

<style scoped>
.f10-card { padding: 18px 20px; margin-top: 16px; }
.f10-card .card-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 14px;
}
.f10-card h3 { margin: 0; font-size: 15px; color: var(--text); }
.profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px 24px;
}
.profile-item {
  display: flex; justify-content: space-between; align-items: baseline;
  border-bottom: 1px dashed var(--line);
  padding-bottom: 6px;
}
.profile-label { color: var(--text-3); font-size: 13px; }
.profile-value { color: var(--text); font-size: 14px; font-weight: 500; text-align: right; }
.peer-ranks {
  display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap;
}
.rank-chip {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--brand-soft);
  border-radius: var(--radius-pill);
  padding: 4px 12px;
  font-size: 12px;
}
.rank-label { color: var(--text-3); }
.rank-value { color: var(--brand); font-weight: 600; }
:deep(.peer-target) { background: var(--brand-soft) !important; }
:deep(.peer-target td) { font-weight: 600; }

.stock-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  margin-bottom: 16px;
}
.stock-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 8px 0;
}
.stock-name { font-size: 20px; color: var(--text-primary); }
.stock-code { font-size: 14px; color: var(--text-muted); }
.current-price { font-size: 28px; font-weight: 700; margin-right: 12px; }
.price-change { font-size: 15px; }
.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}
.action-btns { display: flex; flex-direction: column; gap: 8px; }
.content-grid {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  margin-bottom: 16px;
}
.kline-card { padding: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.card-header h3 { font-size: 15px; color: var(--text-primary); margin: 0; }
.strategy-panel { display: flex; flex-direction: column; gap: 16px; }
.radar-card { padding: 16px; }
.radar-card h3 { font-size: 15px; color: var(--text-primary); margin: 0 0 8px 0; }
.detail-card { padding: 16px; }
.detail-card h3 { font-size: 15px; color: var(--text-primary); margin: 0 0 12px 0; }
.metrics-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.metric-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid rgba(0,212,255,0.06); }
.metric-label { font-size: 13px; color: var(--text-secondary); }
.metric-value { font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; }
.strategies-card { padding: 20px; }
.strategies-card h3 { font-size: 16px; color: var(--text-primary); margin: 0 0 16px 0; }
.prediction-panel { margin-bottom: 16px; }
.strategy-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.strategy-item { padding: 14px; }
.strategy-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.strategy-name { font-size: 13px; color: var(--text-secondary); }
@media (max-width: 1200px) { .content-grid { grid-template-columns: 1fr; } }
</style>
