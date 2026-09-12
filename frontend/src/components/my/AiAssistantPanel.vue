<template>
  <AppCard title="AI 增强分析" sub="可选项：用于解释、复盘和偏好记忆">
    <template #actions>
      <el-tag :type="aiConfig.configured ? 'success' : 'info'" size="small">{{ aiConfig.configured ? '已配置' : '未配置' }}</el-tag>
    </template>

    <!-- 配置表单：桌面直接展开；手机默认折叠 -->
    <el-collapse v-model="openPanels" class="ai-collapse">
      <el-collapse-item name="config" title="模型配置">
        <el-form label-position="top" class="ai-form" size="small">
          <el-form-item label="模型预设">
            <el-select v-model="selectedPreset" placeholder="选择主流模型" @change="applyPreset">
              <el-option v-for="p in presets" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>
          <div class="form-row">
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
            <div class="temp"><span class="temp-label">温度 {{ aiForm.temperature }}</span><el-slider v-model="aiForm.temperature" :min="0" :max="1" :step="0.05" size="small" /></div>
          </div>
          <div class="button-row">
            <el-button size="small" :loading="savingAi" @click="saveConfig">保存配置</el-button>
            <el-button size="small" :loading="testingAi" @click="testConfig">测试</el-button>
          </div>
        </el-form>
      </el-collapse-item>
    </el-collapse>

    <el-input
      v-model="question"
      type="textarea"
      :rows="3"
      class="question"
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

    <el-collapse v-if="history.length" class="history-collapse">
      <el-collapse-item name="history" :title="`分析历史 (${history.length}) · 反馈会作为下次分析的偏好记忆`">
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
      </el-collapse-item>
    </el-collapse>
  </AppCard>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as aiApi from '@/api/ai'
import { useDevice } from '@/composables/useDevice'
import AppCard from '@/components/ui/AppCard.vue'

const props = defineProps<{ cash: number }>()
const { isMobile } = useDevice()

const openPanels = ref<string[]>(isMobile.value ? [] : ['config'])
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

function feedbackLabel(v: string) {
  return v === 'useful' ? '有帮助' : v === 'too_aggressive' ? '太激进' : v === 'too_conservative' ? '太保守' : v
}

async function load() {
  const [cfg, presetResp, hist] = await Promise.all([
    aiApi.getAiConfig(),
    aiApi.getAiPresets(),
    aiApi.getAiHistory(),
  ])
  aiConfig.value = cfg || {}
  presets.value = presetResp?.items || []
  history.value = hist || []
  Object.assign(aiForm, {
    provider: cfg?.provider || 'deepseek',
    baseUrl: cfg?.baseUrl || 'https://api.deepseek.com/v1',
    model: cfg?.model || 'deepseek-chat',
    apiKey: '',
    temperature: Number(cfg?.temperature ?? 0.2),
    enabled: Boolean(cfg?.enabled ?? true),
  })
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
    aiResult.value = await aiApi.analyzePortfolio({ cash: props.cash, question: question.value })
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

onMounted(() => { load().catch(() => {}) })
defineExpose({ reload: load })
</script>

<style scoped>
.ai-collapse, .history-collapse { border: 0; margin-bottom: 12px; }
.ai-collapse :deep(.el-collapse-item__header),
.history-collapse :deep(.el-collapse-item__header) {
  font-size: 13px; color: var(--text-2); background: transparent; border-color: var(--line); height: 40px; line-height: 40px;
}
.ai-collapse :deep(.el-collapse-item__wrap),
.history-collapse :deep(.el-collapse-item__wrap) { background: transparent; border-color: var(--line); }
.ai-collapse :deep(.el-collapse-item__content),
.history-collapse :deep(.el-collapse-item__content) { padding: 10px 0 6px; }
.ai-form :deep(.el-form-item) { margin-bottom: 10px; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ai-actions { display: grid; grid-template-columns: auto 1fr; gap: 14px; align-items: center; margin-bottom: 8px; }
.temp { display: flex; flex-direction: column; }
.temp-label { font-size: 12px; color: var(--text-3); }
.button-row, .feedback-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.question { margin-top: 4px; }
.analyze-btn { width: 100%; margin-top: 10px; }
.ai-result, .history-item {
  margin-top: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
}
.ai-result-head, .history-head { display: flex; justify-content: space-between; color: var(--text-3); margin-bottom: 8px; font-size: 12px; }
pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: var(--font-sans);
  line-height: 1.7;
  font-size: 13px;
  color: var(--text-2);
}
.history-list { display: flex; flex-direction: column; gap: 10px; }
.history-item { margin-top: 0; }
.feedback-chip {
  display: inline-block;
  margin-top: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 12px;
}
@media (max-width: 768px) {
  .form-row { grid-template-columns: 1fr; gap: 0; }
}
</style>
