<template>
  <div class="page-container decision-page">
    <PageHeader title="今日决策" sub="从稳定候选池给出明确的交易决策:今天重点看哪 3 只 → 当前哪 1 只最适合买 → 什么价买 → 没到买点等什么 → 失效后看谁">
      <el-button size="small" :loading="loading" @click="load()">刷新</el-button>
      <el-button v-if="user.token" size="small" :loading="running" @click="rerun">重跑快照</el-button>
    </PageHeader>

    <SnapshotMetaBar :snapshot="data?.snapshot" :prev="prevHeader" :kline-date="klineDate" :note="data?.sample_note || (data?.status === 'no_snapshot' ? data?.message : null)">
      <span v-if="data?.window?.length" class="win">窗口:{{ data.window.map(w => w.slot).join(' · ') }}</span>
    </SnapshotMetaBar>

    <div v-if="loading && !data" class="skeleton-stack">
      <div class="skeleton-block" style="height: 180px" />
      <div class="skeleton-block" style="height: 120px" />
    </div>

    <template v-else-if="data && data.status === 'ok'">
      <!-- ① 当前最适合买入的一只 -->
      <AppCard class="hero-card" title="当前最适合买入" :sub="buyNowSub">
        <template #actions>
          <el-tag v-if="data.buy_now" type="success" effect="dark">进入买点</el-tag>
        </template>
        <template v-if="data.buy_now">
          <PriorityCard :entry="data.buy_now" rank-label="当前买入候选" hero :prev-slot="prevHeader?.slot">
            <el-button type="primary" size="small" @click="recordBuy(data.buy_now)">记录买入(今日 T+1 锁定)</el-button>
            <router-link :to="`/stock/${data.buy_now.code}?tab=t`"><el-button size="small">看分时 / 做T</el-button></router-link>
          </PriorityCard>
          <div class="failover" v-if="data.failover">
            <span class="fo-k">若第一选择失效</span>
            <span>{{ data.failover.trigger }} →</span>
            <template v-if="data.failover.next">
              转向 <router-link class="fo-link" :to="stockPath(data.failover.next.code)">{{ data.failover.next.name }}</router-link>
              ({{ data.failover.next.state }}<template v-if="data.failover.next.zone">,区间 {{ data.failover.next.zone[0] }}–{{ data.failover.next.zone[1] }}</template>)
            </template>
            <span v-else>暂无第二选择,空仓等待</span>
          </div>
          <div v-if="data.alternates.length" class="alts">
            <span class="fo-k">同样进入买点的备选</span>
            <span v-for="a in data.alternates" :key="a.code" class="alt">
              <router-link :to="stockPath(a.code)">{{ a.name }}</router-link>
              <span class="num">决策分 {{ a.decision.toFixed(0) }} · {{ a.buy_zone ? `${a.buy_zone[0]}–${a.buy_zone[1]}` : '' }} · 风险{{ a.risk_level }}</span>
            </span>
          </div>
        </template>
        <div v-else class="no-buy">
          <p class="no-buy-title">当前没有进入买点区的候选,不追高。</p>
          <ul v-if="data.waiting.length" class="wait-list">
            <li v-for="w in data.waiting" :key="w.code">
              <router-link :to="stockPath(w.code)">{{ w.name }}</router-link>
              <span class="num">现价 {{ w.price }}</span>
              <span>{{ w.wait_text || w.buy_label }}</span>
              <span class="num muted">决策分 {{ w.decision.toFixed(0) }}</span>
            </li>
          </ul>
          <p v-else class="muted">候选池内没有等待中的标的;等下一快照。</p>
        </div>
      </AppCard>

      <!-- ② 今日重点关注 3 只 -->
      <AppCard title="今日重点关注" sub="按综合决策分排序;评分高不等于现在可以买,买入与否看每张卡的状态">
        <div v-if="data.focus.length" class="focus-grid">
          <PriorityCard v-for="(e, i) in data.focus" :key="e.code" :entry="e" :rank-label="['第一优先', '第二优先', '第三优先'][i]" :prev-slot="prevHeader?.slot" :show-explain="false">
            <el-button v-if="e.is_actionable" type="primary" size="small" plain @click="recordBuy(e)">记录买入</el-button>
            <router-link :to="stockPath(e.code)"><el-button size="small">详情</el-button></router-link>
          </PriorityCard>
        </div>
        <EmptyState v-else variant="empty" title="候选池为空" description="等待更多快照后再看" hide-retry />
      </AppCard>

      <!-- ③ T+1 三类清单 -->
      <AppCard title="按 T+1 规则分类" sub="今日买入的仓位当日不可卖,不生成任何卖出信号">
        <template #actions>
          <SegmentTabs v-model="listTab" :options="listOptions" small />
        </template>

        <template v-if="listTab === 'new'">
          <StockTable :rows="data.new_entry_candidates" :columns="poolColumns" :loading="loading" empty="没有可新建仓的候选" :to="r => stockPath(r.code)">
            <template #cell-decision="{ row }"><span class="dec-cell"><span v-if="isMobile" class="dec-k">决策分</span><b class="num">{{ row.decision.toFixed(0) }}</b></span></template>
            <template #cell-buy_label="{ row }"><el-tag :type="BUY_STATE_TYPE[row.buy_state as BuyState]" size="small" effect="light">{{ row.buy_label }}</el-tag></template>
            <template #cell-buy_zone="{ row }"><span class="num">{{ row.buy_zone ? `${row.buy_zone[0]}–${row.buy_zone[1]}` : '—' }}</span></template>
            <template #cell-rank_stability="{ row }"><StabilityMeter :value="row.rank_stability" :grade="row.rank_stability_grade" :level="row.rank_stability_level" :series="row.rank_series" :show-series="!isMobile" /></template>
            <template #cell-risk_level="{ row }"><span :class="`risk-${row.risk_level}`">{{ row.risk_level }}</span></template>
            <template #cell-change="{ row }"><RankChangeCell :change="row.change" :rank="row.rank" :composite-now="row.composite" :price="row.price" :prev-slot="prevHeader?.slot" /></template>
          </StockTable>
        </template>

        <template v-else-if="listTab === 't'">
          <div v-if="!user.token" class="muted">登录并录入持仓后,这里列出有可卖底仓的做T候选。</div>
          <template v-else>
            <div v-if="data.t_candidates.length" class="t-list">
              <article v-for="t in data.t_candidates" :key="t.code" class="t-item">
                <div class="t-head">
                  <router-link class="t-name" :to="`/stock/${t.code}?tab=t`">{{ t.name }}</router-link>
                  <span class="mono muted">{{ t.code }}</span>
                  <span class="t-pos num">可卖 <b>{{ t.available }}</b> · 今日买入锁定 <b>{{ t.locked_today }}</b> · 总 <b>{{ t.shares }}</b></span>
                  <el-tag v-if="t.t_signal?.action_label" size="small" :type="tTagType(t.t_signal.action)">{{ t.t_signal.action_label }}</el-tag>
                </div>
                <div v-if="t.t_signal?.plan && t.t_signal.plan.mode !== 'wait'" class="t-plan num">
                  <template v-if="t.t_signal.plan.mode === 'sell_first'">
                    先卖 {{ z(t.t_signal.plan.sell_zone) }} → 接回 {{ z(t.t_signal.plan.buyback_zone) }}
                  </template>
                  <template v-else>
                    低吸 {{ z(t.t_signal.plan.buy_zone) }} → 反弹卖 {{ z(t.t_signal.plan.sellback_zone) }}
                  </template>
                  <span v-if="t.t_signal.plan.execution?.exec_text" class="t-exec">{{ t.t_signal.plan.execution.exec_text }}</span>
                </div>
                <div v-else-if="t.t_signal" class="t-plan muted">{{ t.t_signal.plan?.rules || t.t_signal.reasons?.[0] || '今日观望' }}</div>
                <div v-else class="t-plan muted">分时信号未计算(非交易时段或未开启)</div>
                <div v-if="t.pool" class="t-pool muted">
                  候选池:决策分 {{ t.pool.decision?.toFixed(0) }} · 排名 #{{ t.pool.rank }} · {{ t.pool.buy_label }}
                </div>
                <div v-if="t.t_note" class="t-note">{{ t.t_note }}</div>
              </article>
            </div>
            <div v-else class="muted">没有可卖底仓的持仓。</div>

            <div v-if="data.locked_today.length" class="locked-block">
              <div class="locked-title">今日新建仓(T+1 锁定,不生成卖出信号)</div>
              <div v-for="l in data.locked_today" :key="l.code" class="locked-item">
                <router-link :to="stockPath(l.code)">{{ l.name }}</router-link>
                <span class="mono muted">{{ l.code }}</span>
                <span class="num">锁定 {{ l.locked_today }} / 总 {{ l.shares }}</span>
                <span class="muted">{{ l.t_note }}</span>
              </div>
            </div>
          </template>
        </template>

        <template v-else>
          <StockTable :rows="data.watch_list" :columns="watchColumns" :loading="loading" empty="观察名单为空" :to="r => stockPath(r.code)">
            <template #cell-decision="{ row }"><span class="dec-cell"><span v-if="isMobile" class="dec-k">决策分</span><b class="num">{{ row.decision.toFixed(0) }}</b></span></template>
            <template #cell-buy_label="{ row }"><el-tag :type="BUY_STATE_TYPE[row.buy_state as BuyState]" size="small" effect="light">{{ row.buy_label }}</el-tag></template>
            <template #cell-wait_text="{ row }"><span class="wait-text">{{ row.wait_text || '—' }}</span></template>
            <template #cell-rank_stability="{ row }"><StabilityMeter :value="row.rank_stability" :grade="row.rank_stability_grade" :level="row.rank_stability_level" :series="row.rank_series" :show-series="!isMobile" /></template>
            <template #cell-risk_level="{ row }"><span :class="`risk-${row.risk_level}`">{{ row.risk_level }}</span></template>
            <template #cell-change="{ row }"><RankChangeCell :change="row.change" :rank="row.rank" :composite-now="row.composite" :price="row.price" :prev-slot="prevHeader?.slot" /></template>
          </StockTable>
          <div v-if="data.watch_extra_codes.length" class="muted extra">自选中不在候选池的:{{ data.watch_extra_codes.join('、') }}</div>
        </template>
      </AppCard>

      <!-- ④ 候选池全表 + 规则 -->
      <el-collapse class="pool-collapse">
        <el-collapse-item :title="`稳定候选池全表(${data.pool.length} 只,窗口 ${data.sample_n} 个快照)`" name="pool">
          <StockTable :rows="data.pool" :columns="fullColumns" :loading="loading" empty="候选池为空" :to="r => stockPath(r.code)" dense>
            <template #cell-decision="{ row }"><span class="dec-cell"><span v-if="isMobile" class="dec-k">决策分</span><b class="num">{{ row.decision.toFixed(0) }}</b></span></template>
            <template #cell-buy_label="{ row }"><el-tag :type="BUY_STATE_TYPE[row.buy_state as BuyState]" size="small" effect="light">{{ row.buy_label }}</el-tag></template>
            <template #cell-rank_series="{ row }"><span class="mono muted">{{ row.rank_series.map((r: number | null) => r == null ? '>150' : r).join('·') }}</span></template>
            <template #cell-rank_stability="{ row }"><StabilityMeter :value="row.rank_stability" :grade="row.rank_stability_grade" :level="row.rank_stability_level" :show-series="false" /></template>
            <template #cell-risk_level="{ row }"><span :class="`risk-${row.risk_level}`">{{ row.risk_level }}</span></template>
            <template #cell-change="{ row }"><RankChangeCell :change="row.change" :rank="row.rank" :composite-now="row.composite" :price="row.price" :prev-slot="prevHeader?.slot" /></template>
          </StockTable>
        </el-collapse-item>
        <el-collapse-item title="决策分怎么算 / 分类规则" name="rules">
          <ul class="rules">
            <li v-for="(r, i) in data.rules" :key="i">{{ r }}</li>
            <li>各分量权重:{{ Object.entries(data.weights).map(([k, v]) => `${PART_LABEL[k as keyof typeof PART_LABEL] || k} ${(v * 100).toFixed(0)}%`).join(' · ') }}</li>
            <li>综合评分为 29 个策略的加权平均(0-100),不是概率;指标之间存在相关性,评分不等于独立证据数量。</li>
          </ul>
        </el-collapse-item>
      </el-collapse>
    </template>

    <EmptyState
      v-else-if="data && data.status === 'no_snapshot'"
      variant="empty"
      title="尚无排名快照"
      :description="data.message || '交易时段每 15 分钟自动生成一次;也可以手动跑一次'"
      hide-retry
    >
      <el-button v-if="user.token" type="primary" size="small" :loading="running" @click="rerun">立即生成快照</el-button>
    </EmptyState>

    <EmptyState v-else-if="error" variant="error" title="决策数据加载失败" @retry="load()" />

    <PositionDialog v-model="dialogOpen" :position="dialogPreset" @saved="onSaved" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { getDecisionToday, runDecisionSnapshot, getDecisionSnapshots, BUY_STATE_TYPE, PART_LABEL, type BuyState, type DecisionToday, type PoolEntry, type SnapshotHeader } from '@/api/decision'
import { useUserStore } from '@/stores/user'
import { useDevice } from '@/composables/useDevice'
import { useRefreshable } from '@/composables/useRefreshable'
import { stockPath } from '@/utils/score'
import type { StockColumn, SegmentOption } from '@/types/ui'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppCard from '@/components/ui/AppCard.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import StockTable from '@/components/stock/StockTable.vue'
import SnapshotMetaBar from '@/components/decision/SnapshotMetaBar.vue'
import PriorityCard from '@/components/decision/PriorityCard.vue'
import StabilityMeter from '@/components/decision/StabilityMeter.vue'
import RankChangeCell from '@/components/decision/RankChangeCell.vue'
import PositionDialog from '@/components/my/PositionDialog.vue'

// 决策页:所有数字来自服务端快照与候选池,前端只做展示与"记录买入"回写持仓。
const user = useUserStore()
const { isMobile } = useDevice()

const loading = ref(false)
const running = ref(false)
const error = ref(false)
const data = ref<DecisionToday | null>(null)
const prevHeader = ref<SnapshotHeader | null>(null)

type ListTab = 'new' | 't' | 'watch'
const listTab = ref<ListTab>('new')
const listOptions = computed<SegmentOption<ListTab>[]>(() => [
  { label: `① 新建仓候选 ${data.value?.new_entry_candidates.length ?? 0}`, value: 'new' },
  { label: `② 做T候选 ${data.value?.t_candidates.length ?? 0}`, value: 't' },
  { label: `③ 观察 ${data.value?.watch_list.length ?? 0}`, value: 'watch' },
])

const klineDate = computed(() => {
  const dates = (data.value?.pool || []).map(e => e.kline_date).filter(Boolean) as string[]
  if (!dates.length) return null
  const mx = dates.reduce((a, b) => (a > b ? a : b))
  const mn = dates.reduce((a, b) => (a < b ? a : b))
  return mn === mx ? mx : `${mn}~${mx}`
})

const buyNowSub = computed(() => {
  if (!data.value) return ''
  if (data.value.buy_now) return '进入买点区且风险非高的候选中决策分最高的一只;评分高但已远离买点的不在此列'
  return '评分高 ≠ 现在可以买。下面是等待回踩的候选及等待价格'
})

const baseCols: StockColumn[] = [
  { key: 'decision', label: '决策分', align: 'center', mobile: 'primary', sortable: true },
  { key: 'price', label: '现价', type: 'price', by: 'pct_change', mobile: 'primary' },
  { key: 'pct_change', label: '涨跌幅', type: 'change', mobile: 'secondary' },
  { key: 'buy_label', label: '当前状态', align: 'center', mobile: 'secondary' },
]
const poolColumns: StockColumn[] = [
  ...baseCols,
  { key: 'buy_zone', label: '买入/等待区间', align: 'center', mobile: 'secondary' },
  { key: 'invalid_level', label: '失效位', type: 'num', digits: 2, mobile: 'secondary' },
  { key: 'rank_stability', label: '排名稳定度', align: 'left', mobile: 'secondary' },
  { key: 'risk_level', label: '风险', align: 'center', mobile: 'secondary' },
  { key: 'rank', label: '排名', type: 'num', digits: 0, align: 'center', mobile: 'hidden' },
  { key: 'change', label: 'Δ排名', align: 'center', tooltip: '相对上一快照的排名变化,点开看各因子组贡献', mobile: 'secondary' },
]
const watchColumns: StockColumn[] = [
  ...baseCols,
  { key: 'wait_text', label: '等什么', align: 'left', mobile: 'secondary' },
  { key: 'rank_stability', label: '排名稳定度', align: 'left', mobile: 'secondary' },
  { key: 'risk_level', label: '风险', align: 'center', mobile: 'secondary' },
  { key: 'change', label: 'Δ排名', align: 'center', mobile: 'secondary' },
]
const fullColumns: StockColumn[] = [
  { key: 'decision', label: '决策分', align: 'center', mobile: 'primary', sortable: true },
  { key: 'composite', label: '综合评分', type: 'score', align: 'center', mobile: 'secondary', sortable: true },
  { key: 'rank', label: '排名', type: 'num', digits: 0, align: 'center', mobile: 'secondary' },
  { key: 'rank_series', label: '排名序列', align: 'left', mobile: 'secondary' },
  { key: 'rank_stability', label: '稳定度', align: 'left', mobile: 'secondary' },
  { key: 'trend_stability', label: '趋势稳定', type: 'num', digits: 0, align: 'center', mobile: 'hidden' },
  { key: 'buy_quality', label: '买点质量', type: 'num', digits: 0, align: 'center', mobile: 'hidden' },
  { key: 'sector_strength', label: '板块强度', type: 'num', digits: 0, align: 'center', mobile: 'hidden' },
  { key: 'risk_level', label: '风险', align: 'center', mobile: 'secondary' },
  { key: 'buy_label', label: '状态', align: 'center', mobile: 'primary' },
  { key: 'price', label: '现价', type: 'price', by: 'pct_change', mobile: 'secondary' },
  { key: 'change', label: 'Δ排名', align: 'center', mobile: 'secondary' },
]

function z(zone?: [number, number] | null) { return zone ? `${zone[0]}~${zone[1]}` : '—' }
function tTagType(action?: string) {
  return action === 'negative_t' ? 'success' : action === 'positive_t' ? 'danger' : 'info'
}

async function load() {
  loading.value = true
  error.value = false
  try {
    const d = await getDecisionToday(true)
    data.value = d
    prevHeader.value = null
    if (d.prev_snapshot_id) {
      try {
        const s = await getDecisionSnapshots()
        prevHeader.value = s.snapshots.find(x => x.snapshot_id === d.prev_snapshot_id) || null
      } catch { /* 上一快照头仅用于显示 slot */ }
    }
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

async function rerun() {
  running.value = true
  try {
    const r = await runDecisionSnapshot()
    if (r.status === 'ok') {
      ElMessage.success(`快照 ${r.snapshot?.snapshot_id} 已生成`)
      await load()
    } else {
      ElMessage.warning(r.message || '快照未生成')
    }
  } catch {
    ElMessage.error('快照生成失败')
  } finally {
    running.value = false
  }
}

// 记录买入:把决策落到持仓表,今日买入部分自动 T+1 锁定
const dialogOpen = ref(false)
const dialogPreset = ref<any>(null)
function recordBuy(e: PoolEntry) {
  if (!user.token) { ElMessage.warning('登录后才能记录持仓'); return }
  dialogPreset.value = { code: e.code, name: e.name, shares: 0, avgCost: e.price || 0, todayBought: 100, buyPrice: e.price || 0, recordMode: true }
  dialogOpen.value = true
}
function onSaved() { load() }

useRefreshable('今日决策', load, { immediate: true, autoRefresh: false })
</script>

<style scoped>
.decision-page { display: flex; flex-direction: column; gap: 16px; }
.win { color: var(--text-4); }
.skeleton-stack { display: flex; flex-direction: column; gap: 12px; }
.hero-card :deep(.pc) { margin-bottom: 10px; }
.failover, .alts {
  display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center;
  font-size: 13px; color: var(--text-2); padding: 8px 12px; background: var(--surface-2); border-radius: var(--radius); margin-top: 8px;
}
.fo-k { font-size: 12px; color: var(--text-3); font-weight: 600; }
.fo-link, .alts a, .wait-list a, .t-name, .locked-item a { color: var(--brand); text-decoration: none; font-weight: 600; }
.alt { display: inline-flex; gap: 6px; align-items: baseline; }
.alt .num { font-size: 12px; color: var(--text-3); }
.no-buy-title { font-size: 15px; font-weight: 600; color: var(--text); margin: 0 0 8px; }
.wait-list { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--text-2); }
.wait-list li { display: flex; gap: 10px; flex-wrap: wrap; align-items: baseline; }
.muted { color: var(--text-3); font-size: 12px; }
.focus-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.t-list { display: flex; flex-direction: column; gap: 10px; }
.t-item { border: 1px solid var(--line); border-radius: var(--radius); padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; }
.t-head { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.t-pos { font-size: 12px; color: var(--text-3); }
.t-pos b { color: var(--text); }
.t-plan { font-size: 14px; color: var(--text); }
.t-exec { display: block; font-size: 12px; color: var(--text-2); margin-top: 2px; }
.t-pool { font-size: 12px; }
.t-note { font-size: 12px; color: var(--warn-text); }
.locked-block { margin-top: 14px; border-top: 1px dashed var(--line); padding-top: 10px; }
.locked-title { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 6px; }
.locked-item { display: flex; gap: 10px; flex-wrap: wrap; font-size: 13px; align-items: baseline; }
.extra { margin-top: 8px; }
.wait-text { font-size: 12px; color: var(--text-2); }
.dec-cell { display: inline-flex; gap: 4px; align-items: baseline; }
.dec-k { font-size: 11px; color: var(--text-3); }
.dec-cell b { font-size: 15px; }
.risk-低 { color: var(--up); } .risk-中 { color: var(--warn-text); } .risk-高 { color: var(--down); }
.rules { margin: 0; padding-left: 18px; font-size: 12px; color: var(--text-2); line-height: 1.8; }
.pool-collapse { background: var(--surface); border-radius: var(--radius-lg); padding: 0 16px; box-shadow: var(--shadow-card); }
@media (max-width: 1100px) { .focus-grid { grid-template-columns: 1fr; } }
@media (max-width: 768px) {
  .decision-page { gap: 12px; }
  .pool-collapse { padding: 0 12px; }
}
</style>
