<template>
  <div class="factor-mine" :class="{ mobile: isMobile }">
    <!-- ============ 配置列 ============ -->
    <div class="config-col">
      <AppCard title="因子挖掘" sub="原子因子 × 算子自动组合 → 快速筛选 → 完整验证 → 因子库">
        <el-form label-position="top" size="small" class="config-form">
          <el-form-item>
            <el-checkbox-group v-model="config.market" class="chip-group">
              <el-checkbox-button v-for="m in MARKETS" :key="m.value" :value="m.value">{{ m.label }}</el-checkbox-button>
            </el-checkbox-group>
          </el-form-item>
          <div class="filter-row">
            <el-checkbox v-model="config.exclude_st">排除ST</el-checkbox>
            <el-checkbox v-model="config.exclude_delisting">排除退市</el-checkbox>
            <el-checkbox v-model="config.exclude_suspended">排除停牌</el-checkbox>
          </div>
          <div class="date-row">
            <el-form-item label="开始日期">
              <el-date-picker v-model="config.start_date" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 100%;" :clearable="false" />
            </el-form-item>
            <el-form-item label="结束日期">
              <el-date-picker v-model="config.end_date" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 100%;" :clearable="false" />
            </el-form-item>
          </div>
          <el-form-item>
            <template #label>
              <span>预测周期（可多测）
                <el-tooltip content="因子值对未来 N 个交易日收益的预测力；多个周期同时测试可判断因子是短线还是中期" placement="top">
                  <el-icon class="q"><InfoFilled /></el-icon>
                </el-tooltip>
              </span>
            </template>
            <el-checkbox-group v-model="config.horizons" class="chip-group">
              <el-checkbox-button v-for="h in HORIZONS" :key="h" :value="h">{{ h }}日</el-checkbox-button>
            </el-checkbox-group>
          </el-form-item>
          <div class="date-row">
            <el-form-item>
              <template #label>
                <span>调仓周期
                  <el-tooltip content="每个调仓日重新计算因子截面；IC 统计按调仓周期滚动" placement="top">
                    <el-icon class="q"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-select v-model="config.rebalance" style="width: 100%;">
                <el-option v-for="r in REBALANCES" :key="r.value" :label="r.label" :value="r.value" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <template #label>
                <span>候选预算
                  <el-tooltip content="最多生成多少个候选因子；快速筛选只保留 |RankIC| 最优的前 20% 进入完整验证，防止计算爆炸" placement="top">
                    <el-icon class="q"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-select v-model="config.budget" style="width: 100%;">
                <el-option v-for="b in BUDGETS" :key="b" :label="b.toLocaleString() + ' 个'" :value="b" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item>
            <template #label>
              <span>搜索方式
                <el-tooltip content="随机=模板×原子随机采样；网格=系统枚举；束搜索=单因子→二因子→三因子逐轮按快速 IC 收窄" placement="top">
                  <el-icon class="q"><InfoFilled /></el-icon>
                </el-tooltip>
              </span>
            </template>
            <SegmentTabs v-model="config.method" :options="METHODS" small style="width: 100%;" />
          </el-form-item>

          <el-collapse class="adv">
            <el-collapse-item title="高级参数（判定的阈值全部公开）" name="adv">
              <div class="adv-grid">
                <div class="adv-item"><span class="k">宇宙股票数上限</span><el-input-number v-model="config.max_codes" :min="100" :max="800" :step="50" size="small" /></div>
                <div class="adv-item"><span class="k">分层数</span><el-input-number v-model="config.layers" :min="3" :max="10" size="small" /></div>
                <div class="adv-item"><span class="k">快速筛选保留比例</span><el-input-number v-model="config.keep_pct" :min="0.05" :max="0.5" :step="0.05" size="small" /></div>
                <div class="adv-item"><span class="k">去重相关阈值</span><el-input-number v-model="config.dedup_threshold" :min="0.5" :max="0.99" :step="0.05" size="small" /></div>
                <div class="adv-item"><span class="k">缺失率上限</span><el-input-number v-model="config.max_missing_rate" :min="0.2" :max="0.95" :step="0.05" size="small" /></div>
                <div class="adv-item"><span class="k">完整验证数量上限</span><el-input-number v-model="config.full_validate_limit" :min="10" :max="200" :step="10" size="small" /></div>
                <div class="adv-item"><span class="k">样本外比例</span><el-input-number v-model="config.oos_ratio" :min="0.1" :max="0.5" :step="0.05" size="small" /></div>
                <div class="adv-item"><span class="k">Walk Forward 因子数</span><el-input-number v-model="config.wf_top_k" :min="0" :max="30" :step="5" size="small" /></div>
              </div>
              <p class="caliber">
                PASS 判定（客观规则，非评分）：|t|≥2、期数≥12、|RankIC|≥0.02、|ICIR|≥0.3、样本外同号且 ≥0.01、20bps 成本后净多空 &gt; 0。
                观察对象用 WATCH 标注，不使用星级/字母评级。
              </p>
            </el-collapse-item>
          </el-collapse>

          <el-button type="primary" :loading="submitting" @click="start" style="width: 100%;">
            <el-icon><MagicStick /></el-icon>开始挖掘
          </el-button>
          <p class="method-note">
            流程：候选生成 → 表达式/未来函数静态检查 → 快速 IC 筛选 → 相关性去重 →
            完整检验（IC/分层/衰减/中性/样本内外/Walk Forward/成本）→ PASS/WATCH/REJECT → 因子库。
            任务在后台运行，可暂停/继续（断点续跑）。
          </p>
        </el-form>
      </AppCard>

      <AppCard title="原子因子与算子" sub="生成候选时的变量与运算符目录" compact>
        <div class="catalog-actions">
          <el-button size="small" @click="openCatalog('atoms')">原子因子库</el-button>
          <el-button size="small" @click="openCatalog('operators')">算子注册表</el-button>
        </div>
        <p class="caliber">标注「当前数据源不支持该因子」的原子不会参与挖掘；数据覆盖有限时缺失率检查会如实淘汰，绝不伪造。</p>
      </AppCard>
    </div>

    <!-- ============ 结果列 ============ -->
    <div class="result-area">
      <!-- 任务状态 -->
      <AppCard v-if="job" compact>
        <template #title>任务 {{ job.job_id }}</template>
        <template #actions>
          <span class="chip" :class="'job-' + job.status">{{ JOB_LABEL[job.status] || job.status }}</span>
          <span v-if="job.phase" class="phase">{{ PHASE_LABEL[job.phase] || job.phase }}</span>
          <span class="elapsed num" v-if="job.elapsed_s != null">{{ fmtElapsed(job.elapsed_s) }}</span>
        </template>
        <div class="job-body">
          <el-progress
            v-if="job.status === 'RUNNING' || job.status === 'QUEUED'"
            :percentage="jobProgressPct" :stroke-width="8" :format="() => jobProgressPct + '%'"
          />
          <div class="job-error" v-if="job.error">⚠ {{ job.error }}</div>
          <div class="job-note" v-else-if="job.note">{{ job.note }}</div>

          <!-- 研究过程漏斗 -->
          <div class="funnel">
            <div class="fun-row" v-for="f in funnelRows" :key="f.label">
              <span class="f-k">{{ f.label }}</span>
              <el-icon v-if="f.hint" class="q" size="12"><el-tooltip :content="f.hint" placement="top"><InfoFilled /></el-tooltip></el-icon>
              <span class="f-dots" />
              <span class="f-v num" :class="f.cls">{{ f.value }}</span>
            </div>
          </div>

          <div class="job-actions" v-if="['QUEUED', 'RUNNING', 'PAUSED', 'FAILED'].includes(job.status)">
            <el-button v-if="job.status === 'RUNNING'" size="small" @click="act('pause')">暂停</el-button>
            <el-button v-if="['PAUSED', 'FAILED'].includes(job.status)" size="small" type="primary" @click="act('resume')">从断点继续</el-button>
            <el-button v-if="['QUEUED', 'RUNNING', 'PAUSED'].includes(job.status)" size="small" @click="act('cancel')">取消任务</el-button>
          </div>
        </div>
      </AppCard>

      <!-- 候选因子结果 -->
      <AppCard compact>
        <template #title>因子挖掘结果</template>
        <template #actions>
          <SegmentTabs v-model="filter" :options="filterOptions" small />
        </template>
        <EmptyState
          v-if="!factors.length && !loadingFactors"
          :kind="job ? 'empty' : 'empty'"
          :title="job ? '该筛选下暂无因子' : '尚未运行挖掘任务——配置左侧参数后点击「开始挖掘」'"
        />
        <SkeletonRows v-else-if="loadingFactors && !factors.length" :rows="6" />
        <template v-else>
          <StockTable :rows="factors" :columns="factorColumns" :stock="false" :clickable="false" dense row-key="id">
            <template #cell-expression="{ row }">
              <span class="expr-cell mono" :title="row.expression" @click="openDetail(row.id)">{{ row.expression }}</span>
            </template>
            <template #cell-verdict="{ row }">
              <span v-if="row.verdict" class="chip" :class="'vd-' + row.verdict">{{ row.verdict }}</span>
              <span v-else-if="row.status === 'QUICK_PASS'" class="chip st-quick">通过初筛</span>
              <span v-else class="chip st-rej">淘汰</span>
            </template>
            <template #cell-reject="{ row }">
              <span v-if="row.reject_reason" class="reject-cell" :title="row.reject_detail || row.reject_reason">{{ row.reject_reason }}</span>
              <span v-else class="text-dim">—</span>
            </template>
            <template #actions="{ row }">
              <el-button link type="primary" size="small" @click="openDetail(row.id)">详情</el-button>
              <el-button v-if="row.status === 'VALIDATED'" link size="small" @click="quickLibrary(row)">
                {{ row.in_library ? '移出' : '入库' }}
              </el-button>
            </template>
          </StockTable>
          <div class="load-more" v-if="factors.length >= factorLimit">
            <el-button size="small" text @click="factorLimit += 100; loadFactors()">加载更多</el-button>
          </div>
        </template>
      </AppCard>

      <!-- 因子库 -->
      <AppCard title="因子库（已注册）" sub="通过完整验证后入库；表达式与参数随行保存，可复现、可追溯" compact>
        <template #actions>
          <span class="lib-meta num" v-if="libraryStats.lib_n != null">
            {{ libraryStats.lib_n }} 个入库 · PASS {{ libraryStats.pass_n || 0 }} · WATCH {{ libraryStats.watch_n || 0 }}
          </span>
        </template>
        <EmptyState v-if="!library.length" title="因子库为空——挖掘任务完成后，将 PASS 因子加入因子库" />
        <StockTable v-else :rows="library" :columns="factorColumns" :stock="false" :clickable="false" dense row-key="id">
          <template #cell-expression="{ row }">
            <span class="expr-cell mono" :title="row.expression" @click="openDetail(row.id)">{{ row.expression }}</span>
          </template>
          <template #cell-verdict="{ row }">
            <span v-if="row.verdict" class="chip" :class="'vd-' + row.verdict">{{ row.verdict }}</span>
          </template>
          <template #cell-reject="{ row }">
            <span class="text-dim">—</span>
          </template>
          <template #actions="{ row }">
            <el-button link type="primary" size="small" @click="openDetail(row.id)">详情</el-button>
            <el-button link size="small" @click="quickLibrary(row)">移出</el-button>
          </template>
        </StockTable>
      </AppCard>
    </div>

    <!-- 目录抽屉 -->
    <el-drawer v-model="catalogVisible" :title="catalogType === 'atoms' ? '原子因子库' : '算子注册表'" size="520px" :append-to-body="true">
      <div v-if="catalogType === 'atoms'" class="catalog-body">
        <p class="caliber" style="margin-top: 0;">{{ catalogNote }}</p>
        <div v-for="g in atomGroups" :key="g.category" class="cat-group">
          <div class="cat-title">{{ g.category }}</div>
          <div class="cat-item" v-for="a in g.items" :key="a.name">
            <div class="cat-head">
              <span class="mono cat-name">{{ a.name }}</span>
              <span class="chip" :class="'avail-' + a.status">
                {{ a.status === 'ok' ? '可用' : a.status === 'limited' ? '覆盖有限' : '数据源不支持' }}
              </span>
            </div>
            <div class="cat-desc">{{ a.desc }}</div>
            <div class="cat-note warn" v-if="a.status_note">{{ a.status_note }}</div>
          </div>
        </div>
      </div>
      <div v-else class="catalog-body">
        <p class="caliber" style="margin-top: 0;">{{ operatorNotes }}</p>
        <div class="cat-group" v-for="g in operatorGroups" :key="g.category">
          <div class="cat-title">{{ g.category }}</div>
          <div class="cat-item" v-for="o in g.items" :key="o.name">
            <div class="cat-head"><span class="mono cat-name">{{ o.name }}</span></div>
            <div class="cat-desc mono">{{ o.signature }}</div>
            <div class="cat-desc">{{ o.desc }}<span v-if="o.aliases.length" class="cat-alias">（别名 {{ o.aliases.join(' / ') }}）</span></div>
          </div>
        </div>
        <div class="cat-group">
          <div class="cat-title">四则与比较</div>
          <div class="cat-item" v-for="o in builtinOps" :key="o.name">
            <div class="cat-head"><span class="mono cat-name">{{ o.name }}</span></div>
            <div class="cat-desc">{{ o.desc }}</div>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 因子详情 -->
    <FactorMineDetail v-model="detailVisible" :factor-id="detailFactorId" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, InfoFilled } from '@element-plus/icons-vue'
import {
  createMineJob, getMineJob, mineJobAction, listMineFactors, setFactorLibrary,
  getMineLibrary, getMineAtoms, getMineOperators,
} from '@/api/factormine'
import type { MineConfig, MineJob, MineFactorRow, AtomInfo, OperatorInfo } from '@/api/factormine'
import { useDevice } from '@/composables/useDevice'
import AppCard from '@/components/ui/AppCard.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import StockTable from '@/components/stock/StockTable.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import SkeletonRows from '@/components/ui/SkeletonRows.vue'
import FactorMineDetail from '@/components/screener/FactorMineDetail.vue'
import type { SegmentOption, StockColumn } from '@/types/ui'

const LAST_JOB_KEY = 'fm_last_job_v1'
const { isMobile } = useDevice()

const MARKETS = [
  { label: '沪深A股', value: 'hs' },
  { label: '创业板', value: 'cyb' },
  { label: '科创板', value: 'kcb' },
  { label: '北交所', value: 'bjs' },
]
const HORIZONS = [1, 3, 5, 10, 20, 60]
const REBALANCES = [
  { label: '1 日', value: '1d' }, { label: '3 日', value: '3d' }, { label: '5 日', value: '5d' },
  { label: '10 日', value: '10d' }, { label: '20 日', value: '20d' },
]
const BUDGETS = [100, 500, 1000, 5000, 10000]
const METHODS: SegmentOption<string>[] = [
  { label: '随机搜索', value: 'random' },
  { label: '网格搜索', value: 'grid' },
  { label: '束搜索', value: 'beam' },
]
const JOB_LABEL: Record<string, string> = {
  QUEUED: '排队中', RUNNING: '运行中', PAUSED: '已暂停',
  COMPLETED: '已完成', FAILED: '失败', CANCELLED: '已取消',
}
const PHASE_LABEL: Record<string, string> = {
  QUEUED: '排队', GENERATE: '生成候选', QUICK: '快速筛选', DEDUP: '相关性去重',
  VALIDATE: '完整验证', DONE: '完成', PAUSED: '已暂停', CANCELLED: '已取消',
}

function defaultStart(): string {
  const d = new Date(); d.setFullYear(d.getFullYear() - 2)
  return d.toISOString().slice(0, 10)
}
function defaultEnd(): string { return new Date().toISOString().slice(0, 10) }

const config = reactive({
  market: ['hs'],
  exclude_st: true, exclude_delisting: true, exclude_suspended: true,
  min_listed_days: 120,
  start_date: defaultStart(), end_date: defaultEnd(),
  horizons: [1, 5, 10, 20],
  rebalance: '5d',
  budget: 500,
  method: 'random',
  max_codes: 300, layers: 5, keep_pct: 0.2, dedup_threshold: 0.85,
  max_missing_rate: 0.6, full_validate_limit: 60, oos_ratio: 0.25,
  wf_top_k: 10,
})

// ---- 任务 ----
const job = ref<MineJob | null>(null)
const submitting = ref(false)
let pollTimer: number | null = null

const jobProgressPct = computed(() => {
  const f = job.value?.funnel
  if (!f?.generated) return 0
  const done = Math.min(f.tested + f.full_validated, f.generated)
  return Math.min(Math.round((done / f.generated) * 100), 99)
})

const funnelRows = computed(() => {
  const f = job.value?.funnel
  if (!f) return []
  const filtered = f.invalid_expr + f.leakage + f.data_missing + f.zero_variance
  return [
    { label: '候选因子生成', value: f.generated, cls: '', hint: '模板×原子组合生成，预算上限内，重复表达式已剔除' },
    { label: '表达式非法', value: f.invalid_expr, cls: f.invalid_expr ? 'warn' : '', hint: '语法错误或引用了不存在的字段/算子' },
    { label: '未来函数', value: f.leakage, cls: f.leakage ? 'bad' : '', hint: '负窗口等使用未来数据的表达式，静态检查直接淘汰（LEAKAGE）' },
    { label: '数据不足/零方差', value: filtered, cls: filtered ? 'warn' : '', hint: '数据缺失率过高、预热窗口不够或截面无区分度' },
    { label: '快速筛选淘汰', value: f.quick_rejected, cls: '', hint: `主 horizon |RankIC| 或 |ICIR| 未达门槛，或超出保留比例前 ${Math.round((config.keep_pct || 0.2) * 100)}%` },
    { label: '通过初筛（累计）', value: f.quick_passed, cls: '', hint: '历次通过透明门槛的候选总数（含后续被去重淘汰与完成验证者）' },
    { label: '相关性去重', value: f.dedup_removed, cls: '', hint: `因子值 Spearman |corr| ≥ ${config.dedup_threshold} 归簇，每簇只保留最优` },
    { label: '进入完整验证', value: f.dedup_kept, cls: '', hint: '去重后的簇代表，做 IC/分层/衰减/中性/样本内外/Walk Forward/成本检验' },
    { label: '完整验证完成', value: f.full_validated, cls: '', hint: '完成完整检验的簇代表' },
    { label: 'PASS（通过）', value: f.pass, cls: 'good', hint: '满足全部客观规则：显著性+强度+样本外一致+成本后仍为正' },
    { label: 'WATCH（观察）', value: f.watch, cls: 'warn', hint: '证据链不完整（如样本外失效），可在样本外改善后复检' },
    { label: 'REJECT（未通过）', value: f.reject, cls: '', hint: '未达 PASS/WATCH 口径，淘汰原因逐条可查' },
    { label: '已入库', value: f.library, cls: 'good', hint: '注册进因子库，可在检验/回测/选股中复用' },
  ]
})

async function start() {
  if (!config.horizons.length) { ElMessage.warning('请至少选择一个预测周期'); return }
  if (!config.market.length) { ElMessage.warning('请至少选择一个市场板块'); return }
  submitting.value = true
  try {
    const res = await createMineJob({ ...config, method: config.method as MineConfig['method'] })
    localStorage.setItem(LAST_JOB_KEY, res.job_id)
    ElMessage.success('任务已创建，后台运行中')
    await refreshJob(res.job_id)
    schedulePoll()
  } catch { /* request 层已 toast */ } finally { submitting.value = false }
}

async function refreshJob(jobId: string) {
  try {
    job.value = await getMineJob(jobId)
    if (job.value.status === 'RUNNING' || job.value.status === 'QUEUED') {
      if (job.value.funnel.generated) loadFactors()
    } else {
      loadFactors()
      loadLibrary()
    }
  } catch { /* job 不存在等 */ }
}

function schedulePoll() {
  stopPoll()
  pollTimer = window.setTimeout(async () => {
    if (!job.value) return
    await refreshJob(job.value.job_id)
    if (job.value && ['QUEUED', 'RUNNING'].includes(job.value.status)) schedulePoll()
  }, 2000)
}
function stopPoll() { if (pollTimer) { clearTimeout(pollTimer); pollTimer = null } }

async function act(action: 'pause' | 'resume' | 'cancel') {
  if (!job.value) return
  if (action === 'cancel') {
    try { await ElMessageBox.confirm('取消后已完成的候选结果仍保留，但任务不再继续。确认取消？', '取消任务', { type: 'warning' }) }
    catch { return }
  }
  try {
    await mineJobAction(job.value.job_id, action)
    await refreshJob(job.value.job_id)
    schedulePoll()
  } catch { /* request 层已 toast */ }
}

// ---- 候选列表 ----
type Filter = 'pass' | 'watch' | 'quick' | 'rejected' | 'all'
const filter = ref<Filter>('pass')
const filterOptions: SegmentOption<Filter>[] = [
  { label: 'PASS', value: 'pass' }, { label: 'WATCH', value: 'watch' },
  { label: '通过初筛', value: 'quick' },
  { label: '已淘汰', value: 'rejected' }, { label: '全部', value: 'all' },
]
const factors = ref<MineFactorRow[]>([])
const loadingFactors = ref(false)
const factorLimit = ref(100)

async function loadFactors() {
  if (!job.value) return
  loadingFactors.value = true
  const params: Record<string, unknown> = { job_id: job.value.job_id, limit: factorLimit.value, order: 'rank_ic' }
  if (filter.value === 'pass') { params.verdict = 'PASS' }
  else if (filter.value === 'watch') { params.verdict = 'WATCH' }
  else if (filter.value === 'quick') { params.status = 'QUICK_PASS' }
  else if (filter.value === 'rejected') { params.status = 'REJECTED' }
  try { factors.value = await listMineFactors(params) } catch { factors.value = [] } finally { loadingFactors.value = false }
}
watch(filter, () => { factorLimit.value = 100; loadFactors() })

const fmtNum = (v: number | null | undefined, d = 4): string =>
  v == null || Number.isNaN(v) ? '—' : (v >= 0 ? '+' : '') + v.toFixed(d)

const factorColumns: StockColumn[] = [
  { key: 'id', label: '因子', width: 150, mobile: 'title' },
  { key: 'expression', label: '表达式', tooltip: '点击查看因子详情：公式/AST/IC/分层/衰减/中性化' },
  { key: 'quick_rank_ic', label: 'RankIC', type: 'num', digits: 4, width: 96,
    format: (r: any) => fmtNum(r.rank_ic ?? r.quick_rank_ic),
    tooltip: '调仓周期前向收益的 Spearman 秩相关均值；已验证因子显示完整检验的样本内值' },
  { key: 'quick_icir', label: 'ICIR', type: 'num', digits: 3, width: 80,
    tooltip: 'IC 均值/标准差，衡量稳定性；数值高代表 IC 稳定，但不能单独作为判断依据' },
  { key: 'oos_rank_ic', label: 'OOS RankIC', type: 'num', digits: 4, width: 110,
    tooltip: '样本外（时间窗末段）RankIC：样本内发现、样本外验证，未用样本外重新优化' },
  { key: 'stability', label: '稳定性', width: 84, tooltip: '方向与全样本一致且 |IC|≥0.01 的年份数 / 总年份数' },
  { key: 'verdict', label: '状态', width: 96, tooltip: 'PASS=满足全部客观规则；WATCH=观察；REJECT=未通过（原因可查）' },
  { key: 'reject', label: '淘汰原因', width: 150 },
]

// ---- 因子库 ----
const library = ref<MineFactorRow[]>([])
const libraryStats = ref<Record<string, number>>({})

async function loadLibrary() {
  try {
    const res = await getMineLibrary()
    library.value = res.items
    libraryStats.value = res.stats || {}
  } catch { library.value = [] }
}

async function quickLibrary(row: MineFactorRow) {
  const toLib = !row.in_library
  try {
    await setFactorLibrary(row.id, toLib)
    row.in_library = toLib ? 1 : 0
    ElMessage.success(toLib ? '已加入因子库' : '已移出因子库')
    loadLibrary()
  } catch { /* request 层已 toast */ }
}

// ---- 目录 ----
const catalogVisible = ref(false)
const catalogType = ref<'atoms' | 'operators'>('atoms')
const catalogNote = ref('')
const operatorNotes = ref('')
const atomItems = ref<AtomInfo[]>([])
const operatorItems = ref<OperatorInfo[]>([])
const builtinOps = ref<{ name: string; kind: string; desc: string }[]>([])

const atomGroups = computed(() => {
  const groups: { category: string; items: AtomInfo[] }[] = []
  for (const a of atomItems.value) {
    let g = groups.find(x => x.category === a.category)
    if (!g) { g = { category: a.category, items: [] }; groups.push(g) }
    g.items.push(a)
  }
  return groups
})
const operatorGroups = computed(() => {
  const order = { ts: '时间序列', cross: '横截面', math: '数学', cond: '条件' } as const
  const groups: { category: string; items: OperatorInfo[] }[] = []
  for (const o of operatorItems.value) {
    const cat = order[o.kind]
    let g = groups.find(x => x.category === cat)
    if (!g) { g = { category: cat, items: [] }; groups.push(g) }
    g.items.push(o)
  }
  return groups
})

async function openCatalog(type: 'atoms' | 'operators') {
  catalogType.value = type
  catalogVisible.value = true
  try {
    if (type === 'atoms') {
      const res = await getMineAtoms()
      atomItems.value = res.atoms
      catalogNote.value = res.note
    } else {
      const res = await getMineOperators()
      operatorItems.value = res.operators
      builtinOps.value = res.builtin
      operatorNotes.value = res.notes.join(' ')
    }
  } catch { /* request 层已 toast */ }
}

// ---- 详情 ----
const detailVisible = ref(false)
const detailFactorId = ref<string | null>(null)
function openDetail(id: string) { detailFactorId.value = id; detailVisible.value = true }

function fmtElapsed(s: number): string {
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m${s % 60}s`
  return `${Math.floor(s / 3600)}h${Math.floor((s % 3600) / 60)}m`
}

onMounted(() => {
  const last = localStorage.getItem(LAST_JOB_KEY)
  if (last) {
    refreshJob(last).then(() => {
      if (job.value && ['QUEUED', 'RUNNING'].includes(job.value.status)) schedulePoll()
    })
  }
  loadLibrary()
})
onUnmounted(stopPoll)
</script>

<style scoped>
.factor-mine { display: grid; grid-template-columns: 340px 1fr; gap: 16px; align-items: start; }
.factor-mine.mobile { grid-template-columns: 1fr; gap: 12px; }
.config-col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.config-form :deep(.el-form-item) { margin-bottom: 12px; }
.date-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.filter-row { display: flex; flex-wrap: wrap; gap: 2px 10px; margin-bottom: 12px; }
.chip-group { display: flex; flex-wrap: wrap; gap: 4px; }
.method-note { margin: 8px 0 0; font-size: 11px; color: var(--text-4); line-height: 1.6; }
.caliber { font-size: 11px; color: var(--text-4); line-height: 1.6; margin: 6px 0 0; }
.q { color: var(--text-4); vertical-align: -2px; margin-left: 2px; cursor: help; }

.adv { border: none; }
.adv :deep(.el-collapse-item__header) { font-size: 12px; color: var(--text-3); height: 34px; }
.adv-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.adv-item { display: flex; flex-direction: column; gap: 4px; }
.adv-item .k { font-size: 11px; color: var(--text-3); }

.result-area { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.job-body { display: flex; flex-direction: column; gap: 10px; }
.job-error { font-size: 12px; color: var(--color-red, var(--color-red)); line-height: 1.5; }
.job-note { font-size: 12px; color: var(--text-3); }
.job-actions { display: flex; gap: 8px; }
.chip { font-size: 11px; padding: 2px 10px; border-radius: var(--radius-pill); font-weight: 600; white-space: nowrap; }
.chip.job-RUNNING { background: var(--brand-soft); color: var(--brand); }
.chip.job-COMPLETED { background: var(--color-green-soft); color: var(--color-green); }
.chip.job-FAILED, .chip.job-CANCELLED { background: var(--color-red-soft); color: var(--color-red); }
.chip.job-PAUSED, .chip.job-QUEUED { background: var(--warn-soft); color: var(--warn-text); }
.chip.vd-PASS { background: var(--color-green-soft); color: var(--color-green); }
.chip.vd-WATCH { background: var(--warn-soft); color: var(--warn-text); }
.chip.vd-REJECT { background: var(--color-red-soft); color: var(--color-red); }
.chip.st-quick { background: var(--brand-soft); color: var(--brand); font-weight: 500; }
.chip.st-rej { background: var(--bg-2); color: var(--text-3); font-weight: 500; }
.chip.avail-ok { background: var(--color-green-soft); color: var(--color-green); font-weight: 500; }
.chip.avail-limited { background: var(--warn-soft); color: var(--warn-text); font-weight: 500; }
.chip.avail-unsupported { background: var(--bg-2); color: var(--text-4); font-weight: 500; }
.phase { font-size: 12px; color: var(--text-3); }
.elapsed { font-size: 12px; color: var(--text-4); }

.funnel { display: flex; flex-direction: column; gap: 4px; }
.fun-row { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.f-k { color: var(--text-3); flex-shrink: 0; }
.f-dots { flex: 1; border-bottom: 1px dashed var(--line); }
.f-v { font-variant-numeric: tabular-nums; color: var(--text); font-weight: 600; }
.f-v.warn { color: var(--warn-text); }
.f-v.bad { color: var(--color-red); }
.f-v.good { color: var(--color-green); }

.expr-cell { font-size: 12px; cursor: pointer; max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; vertical-align: bottom; }
.expr-cell:hover { color: var(--brand); }
.reject-cell { font-size: 12px; color: var(--warn-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; max-width: 140px; vertical-align: bottom; }
.text-dim { color: var(--text-4); }
.load-more { text-align: center; padding-top: 8px; }
.lib-meta { font-size: 12px; color: var(--text-3); }

.catalog-actions { display: flex; gap: 8px; margin-bottom: 4px; }
.catalog-body { display: flex; flex-direction: column; gap: 14px; }
.cat-group { display: flex; flex-direction: column; gap: 8px; }
.cat-title { font-size: 12px; font-weight: 600; color: var(--text); padding-bottom: 4px; border-bottom: 1px solid var(--line); }
.cat-item { display: flex; flex-direction: column; gap: 2px; }
.cat-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cat-name { font-size: 12px; font-weight: 600; color: var(--text); }
.cat-desc { font-size: 11px; color: var(--text-3); line-height: 1.5; }
.cat-alias { color: var(--text-4); }
.cat-note.warn { font-size: 11px; color: var(--warn-text); }
</style>
