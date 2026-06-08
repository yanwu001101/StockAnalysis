<template>
  <div class="page-container portfolio-page">
    <section class="portfolio-hero">
      <div class="hero-copy">
        <span class="eyebrow">Portfolio Control</span>
        <h2>持仓助手</h2>
        <p>先用规则引擎和策略共识给出可执行操作；配置 AI 后，再叠加大模型解释和复盘记忆。</p>
      </div>
      <div class="hero-actions">
        <label class="cash-control">
          <span>可用现金</span>
          <el-input-number v-model="cash" :min="0" :step="10000" controls-position="right" />
        </label>
        <label class="mode-control">
          <span>建议模式</span>
          <el-radio-group v-model="adviceMode" size="small" @change="loadAll">
            <el-radio-button value="balanced">均衡</el-radio-button>
            <el-radio-button value="aggressive">收益优先</el-radio-button>
            <el-radio-button value="conservative">稳健</el-radio-button>
          </el-radio-group>
        </label>
        <el-button :loading="loading" @click="loadAll">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button @click="openImportDialog">
          <el-icon><Upload /></el-icon>
          导入
        </el-button>
        <el-button type="primary" @click="openPositionDialog()">
          <el-icon><Plus /></el-icon>
          录入
        </el-button>
      </div>
    </section>

    <section class="portfolio-overview">
      <div class="metric-cell">
        <span>账户资产</span>
        <strong>{{ money(advice.totalAssets) }}</strong>
      </div>
      <div class="metric-cell">
        <span>持仓市值</span>
        <strong>{{ money(advice.totalMarketValue) }}</strong>
      </div>
      <div class="metric-cell">
        <span>策略均分</span>
        <strong>{{ fixed(insights.avgStrategyScore, 1) }}</strong>
      </div>
      <div class="metric-cell">
        <span>组合状态</span>
        <strong>{{ insights.riskLevel || '待录入' }}</strong>
      </div>
      <div class="metric-cell">
        <span>同步方式</span>
        <strong>{{ syncLabel }}</strong>
      </div>
      <div class="metric-cell">
        <span>建议模式</span>
        <strong>{{ advice.modeLabel || modeLabel }}</strong>
      </div>
    </section>

    <section class="rule-brief">
      <div>
        <h3>无 AI 规则体检</h3>
        <p>{{ ruleBrief }}</p>
      </div>
      <div class="brief-counts">
        <span><b>{{ insights.addCount || 0 }}</b> 可买/低吸</span>
        <span><b>{{ insights.tCount || 0 }}</b> 可做 T</span>
        <span><b>{{ insights.reduceCount || 0 }}</b> 需减仓</span>
      </div>
    </section>

    <div class="workspace-grid">
      <section class="panel positions-panel">
        <header class="panel-head">
          <div>
            <h3>我的持仓</h3>
            <p>手工录入或导入同花顺/券商导出表</p>
          </div>
          <div class="panel-actions">
            <el-button size="small" plain @click="openImportDialog">导入</el-button>
            <el-button size="small" type="primary" plain @click="openPositionDialog()">新增</el-button>
          </div>
        </header>

        <div v-if="positions.length" class="position-list">
          <article v-for="row in positions" :key="row.id" class="position-row">
            <div>
              <router-link class="stock-link" :to="`/stock/${row.code}`">{{ row.name || row.code }}</router-link>
              <span class="code">{{ row.code }} · {{ row.industry || '行业待同步' }}</span>
            </div>
            <div class="position-numbers">
              <b>{{ Number(row.shares || 0).toFixed(0) }} 股</b>
              <span>成本 {{ fixed(row.avgCost) }} / 现价 {{ fixed(row.price) }}</span>
            </div>
            <div class="row-actions">
              <el-button text size="small" @click="openPositionDialog(row)">编辑</el-button>
              <el-button text type="danger" size="small" @click="removePosition(row.id)">删除</el-button>
            </div>
          </article>
        </div>
        <el-empty v-else description="暂无持仓，先导入或录入一只股票" :image-size="88" />
      </section>

      <section class="panel action-panel">
        <header class="panel-head">
          <div>
            <h3>操作队列</h3>
            <p>按优先级排序，先处理风险，再考虑买入和做 T</p>
          </div>
          <span class="muted">策略引擎 v2</span>
        </header>

        <div v-if="actionablePositions.length" class="action-list">
          <article
            v-for="item in actionablePositions"
            :key="item.id"
            class="action-card"
            :class="`action-${item.actionType || 'info'}`"
          >
            <div class="action-top">
              <div>
                <h4>{{ item.name || item.code }} <span>{{ item.code }}</span></h4>
                <p>{{ item.ruleSummary }}</p>
              </div>
              <el-tag :type="tagType(item.actionType)" effect="light">{{ item.actionLabel }}</el-tag>
            </div>

            <div class="trade-ticket">
              <span>建议股数 <b>{{ item.suggestedShares || 0 }}</b></span>
              <span>预估金额 <b>{{ money(item.suggestedAmount) }}</b></span>
              <span>低吸线 <b>{{ fixed(item.buyBelow) }}</b></span>
              <span>高抛线 <b>{{ fixed(item.sellAbove) }}</b></span>
            </div>

            <div class="strategy-strip">
              <span>策略共识</span>
              <b>{{ consensusText(item) }}</b>
            </div>

            <div class="strategy-tags">
              <el-tag
                v-for="s in item.strategyConsensus?.topBullish || []"
                :key="`b-${item.id}-${s.id}`"
                type="success"
                effect="plain"
              >
                {{ s.name }} {{ fixed(s.score, 0) }}
              </el-tag>
              <el-tag
                v-for="s in item.strategyConsensus?.topBearish || []"
                :key="`r-${item.id}-${s.id}`"
                type="danger"
                effect="plain"
              >
                {{ s.name }} {{ fixed(s.score, 0) }}
              </el-tag>
            </div>

            <ul class="reason-list">
              <li v-for="r in item.reasons" :key="r">{{ r }}</li>
            </ul>
            <div class="step-box">
              <strong>新手操作</strong>
              <span v-for="s in item.steps" :key="s">{{ s }}</span>
            </div>
          </article>
        </div>
        <el-empty v-else description="录入持仓后生成买卖和做 T 建议" :image-size="90" />
      </section>

      <aside class="side-stack">
        <section class="panel ai-panel">
          <header class="panel-head">
            <div>
              <h3>AI 增强分析</h3>
              <p>可选项：用于解释、复盘和偏好记忆</p>
            </div>
            <el-tag :type="aiConfig.configured ? 'success' : 'info'">{{ aiConfig.configured ? '已配置' : '未配置' }}</el-tag>
          </header>

          <el-form label-position="top" class="ai-form">
            <el-form-item label="模型预设">
              <el-select v-model="selectedPreset" placeholder="选择主流模型" @change="applyPreset">
                <el-option v-for="p in presets" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
            <div class="form-row compact">
              <el-form-item label="Base URL">
                <el-input v-model="aiForm.baseUrl" placeholder="https://api.deepseek.com/v1" />
              </el-form-item>
              <el-form-item label="模型">
                <el-input v-model="aiForm.model" placeholder="deepseek-chat" />
              </el-form-item>
            </div>
            <el-form-item label="API Key">
              <el-input v-model="aiForm.apiKey" type="password" show-password :placeholder="aiConfig.apiKeyMask || '仅保存时填写，后端加密存储'" />
            </el-form-item>
            <div class="ai-actions">
              <el-switch v-model="aiForm.enabled" active-text="启用" />
              <el-slider v-model="aiForm.temperature" :min="0" :max="1" :step="0.05" />
            </div>
            <div class="button-row">
              <el-button :loading="savingAi" @click="saveConfig">保存配置</el-button>
              <el-button :loading="testingAi" @click="testConfig">测试</el-button>
            </div>
          </el-form>

          <el-input
            v-model="question"
            type="textarea"
            :rows="4"
            placeholder="例如：我现在仓位比较重，帮我判断哪些适合做T，哪些该减仓。"
          />
          <el-button class="analyze-btn" type="primary" :loading="analyzing" @click="runAiAnalysis">
            <el-icon><MagicStick /></el-icon>
            生成 AI 持仓分析
          </el-button>

          <div v-if="aiResult.content" class="ai-result">
            <div class="ai-result-head">
              <b>{{ aiResult.model }}</b>
              <span>#{{ aiResult.id }}</span>
            </div>
            <pre>{{ aiResult.content }}</pre>
            <div class="feedback-row">
              <el-button size="small" @click="sendFeedback(aiResult.id, 'useful')">有帮助</el-button>
              <el-button size="small" @click="sendFeedback(aiResult.id, 'too_aggressive')">太激进</el-button>
              <el-button size="small" @click="sendFeedback(aiResult.id, 'too_conservative')">太保守</el-button>
            </div>
          </div>
        </section>

        <section class="panel source-panel">
          <header class="panel-head">
            <div>
              <h3>策略来源</h3>
              <p>新增 A 股短反、保守公式、资金背离、RSRS、趋势止盈、日频T、成长加速</p>
            </div>
          </header>
          <div class="source-list">
            <span>经典动量 / 52 周新高</span>
            <span>质量、盈利能力、投资因子</span>
            <span>应计利润质量与现金含量</span>
            <span>A 股短期反转、低风险、交易类异象</span>
            <span>RSRS 支撑阻力、ATR 移动止盈</span>
            <span>日频动量反转、成长趋势加速</span>
          </div>
        </section>
      </aside>
    </div>

    <section class="panel history-panel" v-if="history.length">
      <header class="panel-head">
        <div>
          <h3>AI 分析历史</h3>
          <p>反馈会作为下次分析的偏好记忆</p>
        </div>
      </header>
      <div class="history-list">
        <article v-for="h in history" :key="h.id" class="history-item">
          <div class="history-head">
            <b>{{ h.model }}</b>
            <span>{{ h.createdAt }}</span>
          </div>
          <pre>{{ h.content }}</pre>
          <span v-if="h.feedback" class="feedback-chip">{{ feedbackLabel(h.feedback) }}</span>
        </article>
      </div>
    </section>

    <el-dialog v-model="positionDialog" title="录入持仓" width="520px">
      <el-form label-position="top">
        <div class="form-row">
          <el-form-item label="股票代码">
            <el-input v-model="positionForm.code" placeholder="600519" />
          </el-form-item>
          <el-form-item label="名称">
            <el-input v-model="positionForm.name" placeholder="可不填" />
          </el-form-item>
        </div>
        <div class="form-row">
          <el-form-item label="持仓股数">
            <el-input-number v-model="positionForm.shares" :min="0" :step="100" controls-position="right" />
          </el-form-item>
          <el-form-item label="可用股数">
            <el-input-number v-model="positionForm.availableShares" :min="0" :step="100" controls-position="right" />
          </el-form-item>
        </div>
        <div class="form-row">
          <el-form-item label="成本价">
            <el-input-number v-model="positionForm.avgCost" :min="0" :precision="3" :step="0.1" controls-position="right" />
          </el-form-item>
          <el-form-item label="目标仓位%">
            <el-input-number v-model="positionForm.targetWeight" :min="1" :max="100" :step="5" controls-position="right" />
          </el-form-item>
        </div>
        <el-form-item label="备注">
          <el-input v-model="positionForm.notes" placeholder="例如：底仓，不轻易卖" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="positionDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingPosition" @click="savePosition">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importDialog" title="导入持仓" width="680px">
      <el-alert
        class="import-alert"
        type="info"
        :closable="false"
        show-icon
        title="从同花顺或券商客户端复制持仓表，粘贴后即可同步到本地持仓；这里不会要求输入交易密码。"
      />
      <el-form label-position="top">
        <el-form-item label="持仓表内容">
          <el-input v-model="importText" type="textarea" :rows="9" :placeholder="importExample" />
        </el-form-item>
        <el-form-item label="默认目标仓位%">
          <el-input-number v-model="importTargetWeight" :min="1" :max="100" :step="5" controls-position="right" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importDialog = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="importPositions">导入并生成建议</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as portfolioApi from '@/api/portfolio'
import * as aiApi from '@/api/ai'

const loading = ref(false)
const cash = ref(0)
const adviceMode = ref<'balanced' | 'aggressive' | 'conservative'>('balanced')
const positions = ref<any[]>([])
const advice = ref<any>({ positions: [], totalMarketValue: 0, totalAssets: 0, insights: {} })
const sync = ref<any>({})

const positionDialog = ref(false)
const savingPosition = ref(false)
const importDialog = ref(false)
const importing = ref(false)
const importText = ref('')
const importExample = '股票代码\t股票名称\t持仓数量\t可用数量\t成本价\n600519\t贵州茅台\t100\t100\t1688.50'
const importTargetWeight = ref(20)
const positionForm = reactive<any>({
  id: undefined,
  code: '',
  name: '',
  shares: 100,
  availableShares: 100,
  avgCost: 0,
  targetWeight: 20,
  notes: '',
})

const presets = ref<any[]>([])
const selectedPreset = ref('')
const aiConfig = ref<any>({})
const aiForm = reactive<any>({
  provider: 'deepseek',
  baseUrl: 'https://api.deepseek.com/v1',
  model: 'deepseek-chat',
  apiKey: '',
  temperature: 0.2,
  enabled: true,
})
const savingAi = ref(false)
const testingAi = ref(false)
const analyzing = ref(false)
const question = ref('请结合我的持仓，告诉我哪些适合买入/加仓，哪些应该卖出/减仓，哪些可以做T，并给新手能执行的步骤。')
const aiResult = ref<any>({})
const history = ref<any[]>([])

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

function money(v: any) {
  const n = Number(v || 0)
  return n.toLocaleString('zh-CN', { style: 'currency', currency: 'CNY', maximumFractionDigits: 2 })
}

function fixed(v: any, digits = 2) {
  const n = Number(v || 0)
  return Number.isFinite(n) && n !== 0 ? n.toFixed(digits) : '--'
}

function tagType(type: string) {
  if (type === 'danger') return 'danger'
  if (type === 'warning') return 'warning'
  if (type === 'success') return 'success'
  return 'info'
}

function feedbackLabel(v: string) {
  return v === 'useful' ? '有帮助' : v === 'too_aggressive' ? '太激进' : v === 'too_conservative' ? '太保守' : v
}

function consensusText(item: any) {
  const c = item.strategyConsensus || {}
  const effective = Number(c.effective || 0)
  if (!effective) return '暂无足够策略数据'
  return `${c.bullish || 0} 看多 / ${c.bearish || 0} 看空 / ${c.triggered || 0} 触发`
}

async function loadAll() {
  loading.value = true
  try {
    const [pos, adv, ths, cfg, presetResp, hist] = await Promise.all([
      portfolioApi.getPortfolioPositions(),
      portfolioApi.getPortfolioAdvice(cash.value, adviceMode.value),
      portfolioApi.getThsSyncStatus(),
      aiApi.getAiConfig(),
      aiApi.getAiPresets(),
      aiApi.getAiHistory(),
    ])
    positions.value = pos || []
    advice.value = adv || { positions: [], insights: {} }
    sync.value = ths || {}
    aiConfig.value = cfg || {}
    presets.value = presetResp?.items || []
    history.value = hist || []
    Object.assign(aiForm, {
      provider: cfg.provider || 'deepseek',
      baseUrl: cfg.baseUrl || 'https://api.deepseek.com/v1',
      model: cfg.model || 'deepseek-chat',
      apiKey: '',
      temperature: Number(cfg.temperature ?? 0.2),
      enabled: Boolean(cfg.enabled ?? true),
    })
  } finally {
    loading.value = false
  }
}

function openPositionDialog(row?: any) {
  Object.assign(positionForm, {
    id: row?.id,
    code: row?.code || '',
    name: row?.name || '',
    shares: Number(row?.shares || 100),
    availableShares: Number(row?.availableShares || row?.shares || 100),
    avgCost: Number(row?.avgCost || 0),
    targetWeight: Number(row?.targetWeight || 20),
    notes: row?.notes || '',
  })
  positionDialog.value = true
}

function openImportDialog() {
  importDialog.value = true
}

async function savePosition() {
  savingPosition.value = true
  try {
    await portfolioApi.savePortfolioPosition(positionForm)
    ElMessage.success('持仓已保存')
    positionDialog.value = false
    await loadAll()
  } finally {
    savingPosition.value = false
  }
}

async function removePosition(id: number) {
  await ElMessageBox.confirm('删除这条持仓记录？', '确认删除', { type: 'warning' })
  await portfolioApi.deletePortfolioPosition(id)
  ElMessage.success('已删除')
  await loadAll()
}

async function importPositions() {
  if (!importText.value.trim()) {
    ElMessage.warning('请先粘贴同花顺或券商导出的持仓表内容')
    return
  }
  importing.value = true
  try {
    const result = await portfolioApi.importPortfolioText({
      text: importText.value,
      targetWeight: importTargetWeight.value,
      source: 'ths_export',
    })
    const imported = Number(result?.imported || 0)
    const skipped = Number(result?.skipped || 0)
    ElMessage.success(skipped ? `已导入 ${imported} 条，跳过 ${skipped} 条` : `已导入 ${imported} 条持仓`)
    importDialog.value = false
    importText.value = ''
    await loadAll()
  } finally {
    importing.value = false
  }
}

function applyPreset(id: string) {
  const p = presets.value.find(x => x.id === id)
  if (!p) return
  aiForm.provider = p.id
  aiForm.baseUrl = p.baseUrl
  aiForm.model = p.model
}

async function saveConfig() {
  savingAi.value = true
  try {
    aiConfig.value = await aiApi.saveAiConfig(aiForm)
    aiForm.apiKey = ''
    ElMessage.success('AI 配置已保存')
  } finally {
    savingAi.value = false
  }
}

async function testConfig() {
  testingAi.value = true
  try {
    const res = await aiApi.testAiConfig()
    ElMessage.success(res.reply || '连接成功')
  } finally {
    testingAi.value = false
  }
}

async function runAiAnalysis() {
  analyzing.value = true
  try {
    aiResult.value = await aiApi.analyzePortfolio({ cash: cash.value, question: question.value })
    history.value = await aiApi.getAiHistory()
  } finally {
    analyzing.value = false
  }
}

async function sendFeedback(id: number, feedback: string) {
  const note = feedbackLabel(feedback)
  await aiApi.saveAiFeedback(id, feedback, note)
  ElMessage.success('反馈已记录，下次分析会参考')
  history.value = await aiApi.getAiHistory()
}

onMounted(loadAll)
</script>

<style scoped>
.portfolio-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.portfolio-hero {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-end;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: var(--shadow-card);
}
.eyebrow {
  display: block;
  color: var(--brand);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  margin-bottom: 6px;
}
.hero-copy h2 { margin: 0; font-size: 24px; }
.hero-copy p { margin: 8px 0 0; color: var(--text-3); max-width: 680px; }
.hero-actions {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.cash-control, .mode-control {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--text-3);
  font-size: 12px;
}
.portfolio-overview {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 1px;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  background: var(--line);
}
.metric-cell {
  padding: 16px;
  background: var(--surface);
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.metric-cell span, .muted { color: var(--text-3); font-size: 13px; }
.metric-cell strong {
  font-size: 18px;
  font-family: var(--font-num);
  overflow-wrap: anywhere;
}
.rule-brief {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-2);
}
.rule-brief h3 { margin: 0 0 6px; }
.rule-brief p { margin: 0; color: var(--text-2); line-height: 1.7; }
.brief-counts {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.brief-counts span {
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--surface);
  color: var(--text-2);
}
.brief-counts b { color: var(--brand); font-family: var(--font-num); }
.workspace-grid {
  display: grid;
  grid-template-columns: minmax(300px, 0.8fr) minmax(460px, 1.25fr) minmax(360px, 0.95fr);
  gap: 16px;
  align-items: start;
}
.panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow-card);
  padding: 16px;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 14px;
}
.panel-head h3 { margin: 0; font-size: 16px; }
.panel-head p { margin: 4px 0 0; color: var(--text-3); font-size: 13px; }
.panel-actions, .button-row, .feedback-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.position-list, .action-list, .history-list, .side-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.position-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
}
.stock-link {
  color: var(--text);
  font-weight: 700;
  text-decoration: none;
}
.code {
  display: block;
  color: var(--text-3);
  font-size: 12px;
  font-family: var(--font-num);
  margin-top: 4px;
}
.position-numbers {
  grid-column: 1 / -1;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: var(--text-3);
  font-size: 13px;
}
.position-numbers b { color: var(--text); font-family: var(--font-num); }
.row-actions {
  display: flex;
  justify-content: flex-end;
  grid-column: 1 / -1;
}
.action-card {
  border: 1px solid var(--line);
  border-left: 4px solid var(--brand);
  border-radius: 8px;
  padding: 14px;
  background: var(--surface);
}
.action-danger { border-left-color: var(--down); }
.action-warning { border-left-color: var(--warn); }
.action-success { border-left-color: var(--up); }
.action-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}
.action-top h4 { margin: 0; font-size: 16px; }
.action-top h4 span { color: var(--text-3); font-size: 12px; font-family: var(--font-num); }
.action-top p { margin: 6px 0 0; color: var(--text-2); line-height: 1.6; }
.trade-ticket {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: 12px 0;
}
.trade-ticket span {
  background: var(--surface-2);
  border-radius: 6px;
  padding: 9px;
  color: var(--text-3);
  font-size: 12px;
  min-width: 0;
}
.trade-ticket b {
  display: block;
  color: var(--text);
  margin-top: 3px;
  font-family: var(--font-num);
  overflow-wrap: anywhere;
}
.strategy-strip {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 6px;
  background: var(--brand-soft);
  color: var(--text-2);
  margin-bottom: 10px;
}
.strategy-strip b { color: var(--brand); }
.strategy-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.reason-list {
  margin: 0 0 10px 18px;
  padding: 0;
  color: var(--text-2);
  line-height: 1.7;
}
.step-box {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  border-radius: 8px;
  background: var(--surface-2);
}
.step-box strong { color: var(--text); }
.ai-form { margin-bottom: 12px; }
.ai-actions {
  display: grid;
  grid-template-columns: 80px 1fr;
  gap: 12px;
  align-items: center;
}
.analyze-btn { width: 100%; margin-top: 10px; }
.ai-result, .history-item {
  margin-top: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
}
.ai-result-head, .history-head {
  display: flex;
  justify-content: space-between;
  color: var(--text-3);
  margin-bottom: 8px;
}
pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: var(--font-sans);
  line-height: 1.7;
}
.source-list {
  display: grid;
  gap: 8px;
}
.source-list span {
  padding: 9px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--text-2);
  background: var(--surface);
}
.history-panel { margin-bottom: 20px; }
.feedback-chip {
  display: inline-block;
  margin-top: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--brand-soft);
  color: var(--brand);
}
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.form-row.compact { gap: 10px; }
.import-alert { margin-bottom: 14px; }

@media (max-width: 1280px) {
  .workspace-grid { grid-template-columns: 1fr; }
  .portfolio-overview { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .portfolio-hero, .rule-brief { flex-direction: column; align-items: stretch; }
  .hero-actions, .brief-counts { justify-content: flex-start; }
  .portfolio-overview { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metric-cell { min-height: 86px; }
  .trade-ticket, .form-row { grid-template-columns: 1fr; }
}
@media (max-width: 420px) {
  .portfolio-overview { grid-template-columns: 1fr; }
}
</style>
