<template>
  <div class="portfolio-panel" :class="{ mobile: isMobile }">
    <AppCard class="hero-card">
      <div class="hero">
        <div class="hero-copy">
          <h3>持仓助手</h3>
          <p>先用规则引擎和策略共识给出可执行操作；配置 AI 后，再叠加大模型解释和复盘记忆。</p>
        </div>
        <div class="hero-actions">
          <label class="control">
            <span>可用现金</span>
            <el-input-number v-model="cash" :min="0" :step="10000" controls-position="right" size="small" />
          </label>
          <label class="control">
            <span>建议模式</span>
            <SegmentTabs v-model="adviceMode" :options="modeOptions" small @update:model-value="loadAll" />
          </label>
          <div class="hero-buttons">
            <el-button size="small" :loading="loading" @click="loadAll"><el-icon><Refresh /></el-icon>刷新</el-button>
            <el-button size="small" @click="importDialog = true"><el-icon><Upload /></el-icon>导入</el-button>
            <el-button size="small" type="primary" @click="openPositionDialog()"><el-icon><Plus /></el-icon>录入</el-button>
          </div>
        </div>
      </div>

      <StatGrid :items="overviewItems" :cols="isMobile ? 2 : 6" size="sm" class="overview" />

      <div class="rule-brief">
        <div>
          <h4>无 AI 规则体检</h4>
          <p>{{ ruleBrief }}</p>
        </div>
        <div class="brief-counts">
          <span><b>{{ insights.addCount || 0 }}</b> 可买/低吸</span>
          <span><b>{{ insights.tCount || 0 }}</b> 可做 T</span>
          <span><b>{{ insights.reduceCount || 0 }}</b> 需减仓</span>
        </div>
      </div>
    </AppCard>

    <div class="workspace-grid">
      <PositionList
        :positions="positions"
        @add="openPositionDialog()"
        @import="importDialog = true"
        @edit="openPositionDialog($event)"
        @remove="removePosition"
      />
      <ActionQueue :items="actionablePositions" />
      <aside class="side-stack">
        <AiAssistantPanel :cash="cash" />
        <AppCard title="策略来源" sub="新增 A 股短反、保守公式、资金背离、RSRS、趋势止盈、日频T、成长加速" compact>
          <div class="source-list">
            <span>经典动量 / 52 周新高</span>
            <span>质量、盈利能力、投资因子</span>
            <span>应计利润质量与现金含量</span>
            <span>A 股短期反转、低风险、交易类异象</span>
            <span>RSRS 支撑阻力、ATR 移动止盈</span>
            <span>日频动量反转、成长趋势加速</span>
          </div>
        </AppCard>
      </aside>
    </div>

    <PositionDialog v-model="positionDialog" :position="editing" @saved="loadAll" />
    <ImportDialog v-model="importDialog" @imported="loadAll" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as portfolioApi from '@/api/portfolio'
import { useRefreshable } from '@/composables/useRefreshable'
import { useDevice } from '@/composables/useDevice'
import { fixedOrDash, formatMoney } from '@/utils/format'
import type { StatItem, SegmentOption } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import StatGrid from '@/components/ui/StatGrid.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import PositionList from './PositionList.vue'
import ActionQueue from './ActionQueue.vue'
import AiAssistantPanel from './AiAssistantPanel.vue'
import PositionDialog from './PositionDialog.vue'
import ImportDialog from './ImportDialog.vue'

const { isMobile } = useDevice()

type Mode = 'balanced' | 'aggressive' | 'conservative'
const loading = ref(false)
const cash = ref(0)
const adviceMode = ref<Mode>('balanced')
const modeOptions: SegmentOption<Mode>[] = [
  { label: '均衡', value: 'balanced' }, { label: '收益优先', value: 'aggressive' }, { label: '稳健', value: 'conservative' },
]
const positions = ref<any[]>([])
const advice = ref<any>({ positions: [], totalMarketValue: 0, totalAssets: 0, insights: {} })
const sync = ref<any>({})

const positionDialog = ref(false)
const importDialog = ref(false)
const editing = ref<any | null>(null)

const syncLabel = computed(() => sync.value?.canAutoSync ? '可同步' : '手工/导入')
const modeLabel = computed(() =>
  adviceMode.value === 'aggressive' ? '收益优先' : adviceMode.value === 'conservative' ? '稳健防守' : '均衡'
)
const insights = computed(() => advice.value?.insights || {})
const actionablePositions = computed(() =>
  [...(advice.value?.positions || [])].sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0))
)
const ruleBrief = computed(() => {
  const bullets = insights.value?.bullets || []
  return bullets.length ? bullets.join(' ') : '录入或导入持仓后，系统会先用策略引擎给出无 AI 操作建议。'
})

const overviewItems = computed<StatItem[]>(() => [
  { label: '账户资产', value: formatMoney(advice.value.totalAssets) },
  { label: '持仓市值', value: formatMoney(advice.value.totalMarketValue) },
  { label: '策略均分', value: fixedOrDash(insights.value.avgStrategyScore, 1) },
  { label: '组合状态', value: insights.value.riskLevel || '待录入' },
  { label: '同步方式', value: syncLabel.value },
  { label: '建议模式', value: advice.value.modeLabel || modeLabel.value },
])

async function loadAll() {
  loading.value = true
  try {
    const [pos, adv, ths] = await Promise.all([
      portfolioApi.getPortfolioPositions(),
      portfolioApi.getPortfolioAdvice(cash.value, adviceMode.value),
      portfolioApi.getThsSyncStatus(),
    ])
    positions.value = pos || []
    advice.value = adv || { positions: [], insights: {} }
    sync.value = ths || {}
  } finally {
    loading.value = false
  }
}

function openPositionDialog(row?: any) {
  editing.value = row || null
  positionDialog.value = true
}

async function removePosition(id: number) {
  try {
    await ElMessageBox.confirm('删除这条持仓记录？', '确认删除', { type: 'warning' })
  } catch { return }
  await portfolioApi.deletePortfolioPosition(id)
  ElMessage.success('已删除')
  await loadAll()
}

useRefreshable('持仓助手', loadAll, { autoRefresh: false })
</script>

<style scoped>
.portfolio-panel { display: flex; flex-direction: column; gap: 16px; }
.portfolio-panel.mobile { gap: 12px; }
.hero { display: flex; justify-content: space-between; gap: 18px; align-items: flex-end; margin-bottom: 14px; }
.hero-copy h3 { margin: 0; font-size: 18px; }
.hero-copy p { margin: 6px 0 0; color: var(--text-3); font-size: 13px; max-width: 620px; }
.hero-actions { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; justify-content: flex-end; }
.control { display: flex; flex-direction: column; gap: 6px; color: var(--text-3); font-size: 12px; }
.hero-buttons { display: flex; gap: 8px; }
.overview { margin-bottom: 12px; }
.rule-brief {
  display: flex; justify-content: space-between; gap: 16px;
  padding: 12px 14px;
  border-radius: var(--radius);
  background: var(--surface-2);
}
.rule-brief h4 { margin: 0 0 4px; font-size: 14px; }
.rule-brief p { margin: 0; color: var(--text-2); line-height: 1.7; font-size: 13px; }
.brief-counts { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; justify-content: flex-end; flex-shrink: 0; }
.brief-counts span { padding: 6px 10px; border-radius: 6px; background: var(--surface); color: var(--text-2); font-size: 12px; }
.brief-counts b { color: var(--brand); font-family: var(--font-num); }
.workspace-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.8fr) minmax(420px, 1.25fr) minmax(320px, 0.95fr);
  gap: 16px;
  align-items: start;
}
.side-stack { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.source-list { display: grid; gap: 8px; }
.source-list span {
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--text-2);
  font-size: 13px;
}
@media (max-width: 1280px) {
  .workspace-grid { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .hero, .rule-brief { flex-direction: column; align-items: stretch; }
  .hero-actions, .brief-counts { justify-content: flex-start; }
  .workspace-grid, .side-stack { gap: 12px; }
}
</style>
