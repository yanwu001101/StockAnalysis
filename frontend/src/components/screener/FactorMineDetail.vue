<template>
  <el-drawer
    v-model="visible"
    :title="detail ? detail.id : '因子详情'"
    size="720px"
    :append-to-body="true"
    class="fm-detail-drawer"
  >
    <div v-if="loading" class="detail-loading"><el-skeleton :rows="8" animated /></div>
    <EmptyState v-else-if="!detail" kind="error" title="因子不存在或加载失败" :retry="reload" />
    <div v-else class="detail-body">
      <!-- 基本信息 -->
      <section class="sec">
        <h4 class="sec-title">基本信息</h4>
        <div class="info-grid">
          <div class="info-item"><span class="k">Factor ID</span><span class="v mono">{{ detail.id }}</span></div>
          <div class="info-item"><span class="k">因子类别</span><span class="v">{{ detail.category || '—' }}</span></div>
          <div class="info-item"><span class="k">生成时间</span><span class="v">{{ fmtTime(detail.created_at) }}</span></div>
          <div class="info-item"><span class="k">数据版本</span><span class="v mono">{{ detail.data_version || '—' }}</span></div>
          <div class="info-item"><span class="k">数据范围</span><span class="v">{{ jobRange }}</span></div>
          <div class="info-item"><span class="k">方向</span><span class="v">{{ directionLabel }}</span></div>
          <div class="info-item wide">
            <span class="k">表达式</span>
            <span class="v mono expr">{{ detail.expression }}</span>
          </div>
          <div class="info-item wide" v-if="detail.source_factors">
            <span class="k">原子因子</span><span class="v mono">{{ detail.source_factors }}</span>
          </div>
        </div>
        <div class="verdict-line" v-if="detail.status === 'VALIDATED'">
          <span class="chip" :class="'vd-' + detail.verdict">{{ detail.verdict }}</span>
          <span class="chip dir" v-if="detail.direction === 'reverse'">反向因子 ↓</span>
          <span class="stab num" v-if="detail.stability">稳定年份 {{ detail.stability }}</span>
        </div>
        <div class="reject-line" v-else-if="detail.status === 'REJECTED'">
          <el-icon><WarningFilled /></el-icon>
          淘汰原因：<b>{{ detail.reject_reason }}</b>
          <span v-if="detail.reject_detail" class="reject-detail">· {{ detail.reject_detail }}</span>
        </div>
      </section>

      <!-- IC 指标 -->
      <section class="sec" v-if="detail.status === 'VALIDATED'">
        <h4 class="sec-title">IC 指标</h4>
        <StatGrid :items="icItems" :cols="isMobile ? 2 : 3" />
        <p class="sample-warn" v-if="periodsN < 12">⚠ 有效期数 {{ periodsN }} 期（&lt;12），统计结果稳定性有限，结论仅供参考</p>
        <p class="caliber">口径：RankIC = 每个调仓日因子截面与前瞻收益的 Spearman 秩相关；ICIR = mean(IC)/std(IC)；t 值 = mean/std×√n。因子值只用 t 日及以前数据。</p>
      </section>

      <!-- 样本内 / 样本外 -->
      <section class="sec" v-if="detail.status === 'VALIDATED' && stats">
        <h4 class="sec-title">样本内 / 样本外</h4>
        <div class="oos-row">
          <div class="oos-card">
            <div class="k">样本内 RankIC（{{ isRange }}）</div>
            <div class="num big" :class="isVal >= 0 ? 'pos' : 'neg'">{{ fmt4(isVal) }}</div>
            <div class="sub">t={{ stats.is_summary?.t_stat ?? '—' }} · ICIR {{ stats.is_summary?.icir ?? '—' }} · {{ stats.is_summary?.n ?? '—' }} 期</div>
          </div>
          <div class="oos-card">
            <div class="k">样本外 RankIC（{{ oosRange }}）</div>
            <div class="num big" :class="oosVal == null ? '' : oosVal >= 0 ? 'pos' : 'neg'">{{ oosVal == null ? '—' : fmt4(oosVal) }}</div>
            <div class="sub" v-if="stats.oos_summary">t={{ stats.oos_summary.t_stat }} · {{ stats.oos_summary.n }} 期</div>
            <div class="sub warn" v-else>样本外有效数据不足</div>
          </div>
        </div>
        <p class="caliber">样本外按交易日末段自动切分（切分日 {{ stats.oos_start || '—' }}）。样本内发现、样本外验证，未用样本外数据做任何重新优化。</p>
      </section>

      <!-- 多周期 IC（衰减） -->
      <section class="sec" v-if="decayRows.length">
        <h4 class="sec-title">IC 衰减（多预测周期）</h4>
        <div v-if="periodsN < 20" class="sample-warn">⚠ 有效样本较少，衰减分析为探索性参考</div>
        <StockTable :rows="decayRows" :columns="decayColumns" :stock="false" :clickable="false" dense row-key="h" />
      </section>

      <!-- 年度稳定性 -->
      <section class="sec" v-if="detail.stability_years?.length">
        <h4 class="sec-title">年度稳定性</h4>
        <StockTable :rows="yearRows" :columns="yearColumns" :stock="false" :clickable="false" dense row-key="year" />
      </section>

      <!-- IC 序列 / 分层净值 -->
      <section class="sec" v-if="detail.status === 'VALIDATED' && stats">
        <h4 class="sec-title">RankIC 序列</h4>
        <BaseChart :option="icOption" :height="200" />
      </section>
      <section class="sec" v-if="detail.status === 'VALIDATED' && stats">
        <h4 class="sec-title">分层净值</h4>
        <BaseChart :option="layerOption" :height="280" />
      </section>

      <!-- 中性化 -->
      <section class="sec" v-if="detail.status === 'VALIDATED' && stats">
        <h4 class="sec-title">中性化与牛熊</h4>
        <div class="neutral-grid">
          <div class="oos-card">
            <div class="k">原始 RankIC</div>
            <div class="num big" :class="rawIc >= 0 ? 'pos' : 'neg'">{{ fmt4(rawIc) }}</div>
          </div>
          <div class="oos-card">
            <div class="k">行业中性 RankIC</div>
            <div class="num big" :class="(stats.ic_neutral_summary?.mean ?? 0) >= 0 ? 'pos' : 'neg'">
              {{ stats.ic_neutral_summary ? fmt4(stats.ic_neutral_summary.mean) : '—' }}
            </div>
            <div class="sub" v-if="!stats.ic_neutral_summary">行业覆盖不足</div>
          </div>
          <div class="oos-card">
            <div class="k">市值中性 RankIC</div>
            <div class="num big na">—</div>
            <div class="sub warn">当前数据源不支持（无历史市值面板，不做伪造）</div>
          </div>
          <div class="oos-card" v-if="stats.regime">
            <div class="k">牛市 / 熊市 IC</div>
            <div class="num big">{{ fmt4(stats.regime.bull.ic_mean) }} / {{ fmt4(stats.regime.bear.ic_mean) }}</div>
            <div class="sub">{{ stats.regime.bull.n }} / {{ stats.regime.bear.n }} 期（沪深300 相对 MA60）</div>
          </div>
        </div>
        <p class="caliber" v-if="stats.ic_neutral_summary">行业中性保留度 {{ neutralRetention }}：衡量因子是自身有效还是主要暴露行业。行业分类为当前快照，存在轻微近似。</p>
      </section>

      <!-- 成本敏感性 -->
      <section class="sec" v-if="detail.status === 'VALIDATED' && stats?.cost_table?.length">
        <h4 class="sec-title">交易成本敏感性</h4>
        <p class="caliber">净多空年化 = 方向校正后毛多空年化 − 年化换手 × 单次成本（{{ stats.turnover_annualized ?? '—' }}x 换手）。分层为纸面组合，成本按换手线性扣除。</p>
        <StockTable :rows="costRows" :columns="costColumns" :stock="false" :clickable="false" dense row-key="bps" />
      </section>

      <!-- Walk Forward -->
      <section class="sec" v-if="stats?.walk_forward?.length">
        <h4 class="sec-title">Walk Forward（滚动验证）</h4>
        <div class="wf-summary" v-if="wfStableRatio !== null">稳定窗口 <b class="num">{{ wfStableRatio }}</b>（方向与样本内一致且 |RankIC| ≥ 0.02）</div>
        <StockTable :rows="stats.walk_forward" :columns="wfColumns" :stock="false" :clickable="false" dense row-key="test" />
      </section>

      <!-- 同簇相关因子（因子值相关性聚类的同簇成员） -->
      <section class="sec" v-if="clusterPeers.length">
        <h4 class="sec-title">同簇相关因子</h4>
        <p class="caliber" style="margin-top: 0;">因子值 Spearman |corr| ≥ {{ dedupThreshold }} 归为同一簇，每簇仅保留 |RankIC| 最优者参与完整验证；以下为同簇的其余成员。</p>
        <div class="rel-list">
          <div class="rel-item" v-for="p in clusterPeers" :key="String(p.id)">
            <span class="mono rel-id">{{ p.id }}</span>
            <span class="rel-expr mono">{{ p.expression }}</span>
            <span class="num" :class="Math.abs(Number(p.cluster_corr)) >= (dedupThreshold ?? 0.85) ? 'corr-high' : ''">
              {{ p.cluster_corr != null ? Number(p.cluster_corr).toFixed(2) : '—' }}
            </span>
          </div>
        </div>
      </section>

      <!-- 操作 -->
      <div class="actions">
        <template v-if="detail.status === 'VALIDATED'">
          <el-button v-if="!detail.in_library" type="primary" size="small" :loading="acting" @click="toggleLibrary(true)">加入因子库</el-button>
          <el-button v-else size="small" :loading="acting" @click="toggleLibrary(false)">移出因子库</el-button>
          <el-button size="small" :loading="acting" @click="doRevalidate">重新运行</el-button>
          <el-button size="small" @click="goScreen">用因子选股</el-button>
        </template>
        <el-button size="small" @click="go('factor')">去因子检验</el-button>
        <el-button size="small" @click="go('backtest')">去组合回测</el-button>
      </div>
      <p class="caliber" style="margin-top: 8px;">
        因子描述统计特征，不等于买点：这里只研究因子排序能力，不生成交易信号；实际买卖请回到选股与决策模块。
      </p>
    </div>

    <!-- 因子选股结果（排序名单，非买点） -->
    <el-dialog v-model="screenVisible" title="因子截面选股" width="560px" :append-to-body="true">
      <template v-if="screenResult">
        <p class="caliber" style="margin-top: 0;">
          {{ screenResult.direction_note }} · 截面日期 {{ screenResult.as_of }} · 宇宙 {{ screenResult.universe_size }} 只（流动性前 400）。
          因子值排序 ≠ 买点，交易决策请回到选股/决策模块。
        </p>
        <StockTable :rows="screenResult.items" :columns="screenColumns" :stock="true" :clickable="true" dense row-key="code" />
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import type { EChartsOption } from 'echarts'
import {
  getMineFactor, setFactorLibrary, revalidateFactor, screenWithFactor,
} from '@/api/factormine'
import type { MineFactorDetail } from '@/api/factormine'
import { useDevice } from '@/composables/useDevice'
import { useChartTokens, baseTooltip } from '@/composables/useEcharts'
import StatGrid from '@/components/ui/StatGrid.vue'
import StockTable from '@/components/stock/StockTable.vue'
import BaseChart from '@/components/charts/BaseChart.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import type { StatItem, StockColumn } from '@/types/ui'

const props = defineProps<{ factorId: string | null }>()
const model = defineModel<boolean>({ default: false })

const visible = computed({
  get: () => model.value,
  set: (v: boolean) => { model.value = v },
})
const router = useRouter()
const { isMobile } = useDevice()
const tokens = useChartTokens()

const loading = ref(false)
const acting = ref(false)
const detail = ref<MineFactorDetail | null>(null)

watch(() => props.factorId, (id) => {
  if (id && model.value) reload()
  else if (!id) detail.value = null
})
watch(model, (v) => { if (v && props.factorId) reload() })

async function reload() {
  if (!props.factorId) return
  loading.value = true
  try {
    detail.value = await getMineFactor(props.factorId)
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

const stats = computed(() => detail.value?.stats || null)
const clusterPeers = computed(() => {
  const d = detail.value
  if (!d?.cluster_peers?.length || d.cluster_id == null || d.cluster_id < 0) return []
  return d.cluster_peers
})
const dedupThreshold = computed(() => {
  const peers = clusterPeers.value
  const corr = peers.map(p => Math.abs(Number(p.cluster_corr))).filter(v => !Number.isNaN(v) && v > 0)
  if (!corr.length) return 0.85
  return Math.max(...corr)
})
const periodsN = computed(() => stats.value?.ic_summary?.n ?? 0)
const isVal = computed(() => stats.value?.is_summary?.mean ?? detail.value?.rank_ic ?? 0)
const oosVal = computed(() => stats.value?.oos_summary?.mean ?? null)
const rawIc = computed(() => stats.value?.ic_summary?.mean ?? 0)
const isRange = computed(() => stats.value ? `${stats.value.start} ~ ${stats.value.oos_start || stats.value.end}` : '—')
const oosRange = computed(() => stats.value ? `${stats.value.oos_start || '—'} ~ ${stats.value.end}` : '—')
const neutralRetention = computed(() => {
  const raw = Math.abs(stats.value?.ic_summary?.mean ?? 0)
  const neu = Math.abs(stats.value?.ic_neutral_summary?.mean ?? 0)
  if (raw <= 0) return '—'
  return `${Math.round(neu / raw * 100)}%`
})
const jobRange = computed(() => stats.value ? `${stats.value.start} ~ ${stats.value.end} · 调仓 ${stats.value.rebalance}` : '—')
const directionLabel = computed(() => {
  const d = detail.value?.direction
  return d === 'reverse' ? '反向（值低者历史排序收益优）' : d === 'positive' ? '正向（值高者历史排序收益优）' : '中性'
})
const wfStableRatio = computed(() => {
  const wf = stats.value?.walk_forward
  if (!wf?.length) return null
  return `${wf.filter(w => w.stable).length}/${wf.length}`
})

const icItems = computed<StatItem[]>(() => {
  const s = stats.value
  return [
    { label: '全样本 RankIC', value: s?.ic_summary ? fmt4(s.ic_summary.mean) : '—', foot: '全区间（含样本外）的 Spearman 秩相关均值' },
    { label: 'ICIR', value: s?.ic_summary ? String(s.ic_summary.icir) : '—', foot: 'IC 均值/标准差，衡量稳定性；不能单独作为判断依据' },
    { label: 't 值', value: s?.ic_summary ? String(s.ic_summary.t_stat) : '—', foot: '|t|≥2 通常认为统计上显著，需结合样本量' },
    { label: 'IC > 0', value: s?.ic_summary ? `${Math.round(s.ic_summary.positive_ratio * 100)}%` : '—', foot: 'IC 为正的调仓期占比' },
    { label: 'Pearson IC', value: s?.ic_pearson_summary ? fmt4(s.ic_pearson_summary.mean) : '—', foot: '线性相关口径的 IC（RankIC 的补充视角）' },
    { label: '有效期数', value: String(periodsN.value), foot: '参与统计的调仓期数量' },
  ]
})

const decayColumns: StockColumn[] = [
  { key: 'h', label: '预测周期', width: 90 },
  { key: 'ic_mean', label: 'RankIC', type: 'num', digits: 4, colored: true, tooltip: '该 horizon 前向收益的 RankIC 均值' },
  { key: 'icir', label: 'ICIR', type: 'num', digits: 3, colored: true, tooltip: '该 horizon 的 IC 稳定性' },
  { key: 'n', label: '期数', type: 'num' },
]
const decayRows = computed(() => (stats.value?.decay || []).map(d => ({ h: `${d.horizon}日`, ic_mean: d.ic_mean, icir: d.icir, n: d.n })))

const yearColumns: StockColumn[] = [
  { key: 'year', label: '年份', width: 70 },
  { key: 'ic_mean', label: 'RankIC', type: 'num', digits: 4, colored: true },
  { key: 'n', label: '期数', type: 'num' },
  { key: 'positive_ratio', label: 'IC>0', type: 'num', digits: 2, format: (r: any) => `${Math.round(r.positive_ratio * 100)}%` },
  { key: 'match', label: '方向一致', width: 90, format: (r: any) => (r.match ? '✓' : '✗') },
]
const yearRows = computed(() => (detail.value?.stability_years || []).map(y => ({
  year: y.year, ic_mean: y.ic_mean, n: y.n, positive_ratio: y.positive_ratio, match: y.dir_match,
})))

const costColumns: StockColumn[] = [
  { key: 'bps', label: '单次成本', width: 100, format: (r: any) => `${r.bps} bps` },
  { key: 'net_spread_ann', label: '净多空年化', type: 'num', digits: 4, colored: true, tooltip: '方向校正后毛多空年化 − 年化换手×单次成本' },
  { key: 'note', label: '说明', width: 160 },
]
const costRows = computed(() => (stats.value?.cost_table || []).map(c => ({
  bps: c.bps, net_spread_ann: c.net_spread_ann,
  note: c.bps === 0 ? '无摩擦（毛收益）' : c.bps === 20 ? '常用口径' : '',
})))

const wfColumns: StockColumn[] = [
  { key: 'test', label: '验证窗口', width: 190, format: (r: any) => r.test.split('~')[0] + ' 起' },
  { key: 'ic_mean', label: 'RankIC', type: 'num', digits: 4, colored: true },
  { key: 'icir', label: 'ICIR', type: 'num', digits: 2 },
  { key: 'spread_ann', label: '多空年化', type: 'num', digits: 4, colored: true },
  { key: 'top_max_drawdown', label: '最高层回撤', type: 'num', digits: 2, colored: true, format: (r: any) => (r.top_max_drawdown == null ? '—' : `${(r.top_max_drawdown * 100).toFixed(1)}%`) },
  { key: 'stable', label: '稳定', width: 70, format: (v: boolean) => (v ? '✓' : '✗') },
]

const screenColumns: StockColumn[] = [
  { key: 'rank', label: '#', width: 48 },
  { key: 'code', label: '代码', width: 90 },
  { key: 'name', label: '名称' },
  { key: 'factor_value', label: '因子值', type: 'num', digits: 4 },
]

const icOption = computed<EChartsOption | null>(() => {
  const rows = stats.value?.ic_series
  if (!rows?.length) return null
  const t = tokens.value
  return {
    backgroundColor: 'transparent', textStyle: { fontFamily: t.font },
    grid: { left: 56, right: 20, top: 16, bottom: 36 },
    xAxis: { type: 'category', data: rows.map(r => r.date), axisLabel: { color: t.text3, fontSize: 10 }, axisLine: { lineStyle: { color: t.line } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: t.line } }, axisLabel: { color: t.text3 } },
    series: [{ type: 'bar', data: rows.map(r => ({ value: r.ic, itemStyle: { color: r.ic >= 0 ? t.up : t.down } })) }],
    tooltip: { trigger: 'axis', ...baseTooltip(t) },
  }
})

const layerOption = computed<EChartsOption | null>(() => {
  const rows = stats.value?.layer_curves
  if (!rows?.length) return null
  const t = tokens.value
  const keys = Object.keys(rows[0]).filter(k => k !== 'date')
  return {
    backgroundColor: 'transparent', textStyle: { fontFamily: t.font },
    legend: { data: keys, top: 0, right: 8, textStyle: { color: t.text3, fontSize: 11 }, itemWidth: 14 },
    grid: { left: 56, right: 20, top: 32, bottom: 36 },
    xAxis: { type: 'category', data: rows.map(r => String(r.date)), axisLabel: { color: t.text3, fontSize: 10 }, axisLine: { lineStyle: { color: t.line } } },
    yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: t.line } }, axisLabel: { color: t.text3 } },
    series: keys.map((k, i) => ({
      type: 'line', name: k, data: rows.map(r => r[k]), symbol: 'none', smooth: true,
      lineStyle: { color: t.series[i % t.series.length], width: k === `L${keys.length}` ? 2.2 : 1.4 },
    })),
    tooltip: { trigger: 'axis', ...baseTooltip(t) },
  }
})

function fmt4(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(4)}`
}
function fmtTime(s: string | null): string {
  return s ? s.replace('T', ' ').slice(0, 19) : '—'
}

async function toggleLibrary(inLib: boolean) {
  if (!detail.value) return
  acting.value = true
  try {
    const updated = await setFactorLibrary(detail.value.id, inLib)
    detail.value.in_library = updated.in_library
    ElMessage.success(inLib ? '已加入因子库' : '已移出因子库')
  } catch { /* request 层已 toast */ } finally { acting.value = false }
}

async function doRevalidate() {
  if (!detail.value) return
  acting.value = true
  try {
    await ElMessageBox.confirm(
      '以相同表达式、相同配置、当前数据版本重新运行完整检验。数据版本变化时结果可能不同（会如实反映新数据）。',
      '重新运行', { type: 'info' })
    await revalidateFactor(detail.value.id)
    await reload()
    ElMessage.success('重新检验完成')
  } catch { /* 取消或失败 */ } finally { acting.value = false }
}

function go(target: 'factor' | 'backtest') {
  if (!detail.value) return
  router.push({ path: '/lab', query: { sub: target, expr: detail.value.expression } })
  model.value = false
}

const screenVisible = ref(false)
const screenResult = ref<Awaited<ReturnType<typeof screenWithFactor>> | null>(null)
async function goScreen() {
  if (!detail.value) return
  try {
    screenResult.value = await screenWithFactor(detail.value.id, 20)
    screenVisible.value = true
  } catch { /* request 层已 toast */ }
}
</script>

<style scoped>
.detail-body { display: flex; flex-direction: column; gap: 18px; }
.sec-title { font-size: 13px; font-weight: 600; color: var(--text); margin: 0 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--line); }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
.info-item { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.info-item.wide { grid-column: 1 / -1; }
.info-item .k { font-size: 11px; color: var(--text-3); }
.info-item .v { font-size: 12px; color: var(--text); }
.info-item .expr { word-break: break-all; line-height: 1.5; }
.mono { font-family: var(--font-num, monospace); }
.verdict-line { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
.chip { font-size: 11px; padding: 2px 10px; border-radius: var(--radius-pill); font-weight: 600; }
.chip.vd-PASS { background: var(--color-green-soft); color: var(--color-green); }
.chip.vd-WATCH { background: var(--warn-soft); color: var(--warn-text); }
.chip.vd-REJECT { background: var(--color-red-soft); color: var(--color-red); }
.chip.dir { background: var(--warn-soft); color: var(--warn-text); font-weight: 500; }
.stab { font-size: 12px; color: var(--text-3); }
.reject-line { display: flex; align-items: baseline; gap: 4px; margin-top: 10px; font-size: 12px; color: var(--warn-text); line-height: 1.6; }
.reject-detail { color: var(--text-3); }
.oos-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.neutral-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.oos-card { padding: 10px 12px; border-radius: var(--radius); background: var(--bg-2); min-width: 0; }
.oos-card .k { font-size: 11px; color: var(--text-3); margin-bottom: 4px; }
.oos-card .big { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
.oos-card .sub { font-size: 11px; color: var(--text-4); margin-top: 2px; }
.oos-card .sub.warn { color: var(--warn-text); }
.oos-card .big.na { color: var(--text-4); }
.pos { color: var(--up); }
.neg { color: var(--down); }
.caliber { font-size: 11px; color: var(--text-4); line-height: 1.6; margin: 8px 0 0; }
.sample-warn { font-size: 12px; color: var(--warn-text); margin: 8px 0 0; }
.wf-summary { font-size: 12px; color: var(--text-2); margin-bottom: 8px; }
.rel-title { font-size: 12px; color: var(--text-3); margin-bottom: 6px; }
.rel-list { display: flex; flex-direction: column; gap: 4px; }
.rel-item { display: flex; align-items: center; gap: 10px; font-size: 12px; }
.rel-id { color: var(--text-3); flex-shrink: 0; }
.rel-expr { color: var(--text-2); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.corr-high { color: var(--warn-text); font-weight: 600; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
@media (max-width: 768px) {
  .info-grid, .oos-row, .neutral-grid { grid-template-columns: 1fr; }
}
</style>
