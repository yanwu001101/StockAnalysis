<template>
  <div class="strategy-weights">
    <AppCard title="策略权重" sub="自定义策略权重，打造专属选股模型；综合分按相对权重归一化">
      <template #actions>
        <el-button size="small" plain :disabled="allEnabled" :title="allEnabled ? '所有策略均已开启' : ''" @click="setAll(true)">全部开启</el-button>
        <el-button size="small" type="danger" plain :disabled="allDisabled" :title="allDisabled ? '所有策略均已关闭' : ''" @click="setAll(false)">全部关闭</el-button>
        <el-button size="small" @click="resetDefaults">恢复默认</el-button>

        <el-popover v-if="strategyStore.savedConfigs.length" trigger="click" placement="bottom-end" :width="260">
          <template #reference>
            <el-button size="small">
              我的方案 ({{ strategyStore.savedConfigs.length }})
              <el-icon><ArrowDown /></el-icon>
            </el-button>
          </template>
          <div class="scheme-list">
            <div v-for="c in strategyStore.savedConfigs" :key="c.name" class="scheme-row">
              <button class="scheme-load" :title="`载入方案「${c.name}」`" @click="loadScheme(c.name)">
                <span class="scheme-name">{{ c.name }}</span>
                <span class="scheme-meta num">{{ c.config.filter(s => s.enabled).length }} 策略</span>
              </button>
              <el-icon class="scheme-del" title="删除方案" @click="deleteScheme(c.name)"><Delete /></el-icon>
            </div>
          </div>
        </el-popover>

        <el-button size="small" @click="showSaveDialog = true">保存方案</el-button>
        <el-button type="primary" size="small" :loading="previewLoading" @click="openPreview">
          <el-icon><View /></el-icon>预览结果
        </el-button>
      </template>

      <div class="total-weight">
        <span class="tw-label">相对权重总和</span>
        <span class="tw-value num">{{ totalWeight }}%</span>
        <span class="tw-hint">总和不必等于 100</span>
        <el-button v-if="totalWeight !== 100 && totalWeight > 0" link size="small" @click="normalizeWeights">一键归一化为 100%</el-button>
      </div>

      <div class="strategy-list">
        <div class="strategy-card" v-for="s in strategyStore.strategies" :key="s.id" :class="{ off: !s.enabled }">
          <div class="strategy-top">
            <div class="strategy-info">
              <el-switch v-model="s.enabled" />
              <div class="strategy-meta">
                <span class="strategy-name">{{ s.name }}</span>
                <span class="strategy-desc">{{ s.description }}</span>
              </div>
            </div>
            <div class="strategy-actions">
              <span class="weight-value num" :style="{ color: s.color }">{{ s.weight }}%</span>
              <el-button v-if="paramsOf(s.id).length" link size="small" @click="toggleExpand(s.id)">
                {{ expanded[s.id] ? '收起' : '调参' }}
                <el-icon><component :is="expanded[s.id] ? 'ArrowUp' : 'ArrowDown'" /></el-icon>
              </el-button>
            </div>
          </div>
          <div class="weight-slider">
            <el-slider v-model="s.weight" :min="0" :max="50" :step="1" :disabled="!s.enabled" size="small" />
          </div>
          <div class="params-grid" v-if="expanded[s.id]">
            <div class="param-row" v-for="p in paramsOf(s.id)" :key="p.name">
              <div class="param-head">
                <span class="param-label">{{ p.label }}</span>
                <span class="param-value num">{{ getParam(s.id, p.name) ?? p.default }}</span>
              </div>
              <el-slider :model-value="getParam(s.id, p.name) ?? p.default"
                         @update:model-value="(v: any) => setParam(s.id, p.name, v)"
                         :min="p.min" :max="p.max" :step="p.step"
                         :disabled="!s.enabled" size="small" />
              <span class="param-desc" v-if="p.desc">{{ p.desc }}</span>
            </div>
          </div>
        </div>
      </div>
    </AppCard>

    <!-- 预览结果：弹窗承载（桌面对话框 / 手机底部抽屉），不再内联撑长页面 -->
    <AppDialog v-model="showPreview" title="预览结果" width="860px">
      <div class="preview-body">
        <p class="preview-sub">勾选要求触发的策略，AND 过滤</p>
        <div class="trigger-filter">
          <el-checkbox-group v-model="requireTriggered" size="small" :disabled="previewLoading" @change="previewResults">
            <el-checkbox v-for="s in strategyStore.strategies.filter(x => x.enabled)" :key="s.id" :value="s.id" :style="{ color: s.color }">
              {{ s.name }}
            </el-checkbox>
          </el-checkbox-group>
          <el-button v-if="requireTriggered.length" link size="small" @click="clearTriggered">清空</el-button>
        </div>
        <StockTable
          :rows="previewData"
          :columns="columns"
          :loading="previewLoading"
          :error="previewError"
          :empty="previewError ? '预览请求失败，请重试' : '没有股票同时触发所选策略，试试减少多选或降低筛选门槛'"
          rank
          @retry="previewResults"
        >
          <template #cell-triggered="{ row }">
            <el-tag size="small" type="info">{{ triggeredText(row) }}</el-tag>
          </template>
        </StockTable>
      </div>
    </AppDialog>

    <AppDialog v-model="showSaveDialog" title="保存策略方案" width="400px">
      <el-input v-model="saveName" placeholder="输入方案名称" @keyup.enter="doSave" />
      <template #footer>
        <el-button @click="showSaveDialog = false">取消</el-button>
        <el-button type="primary" @click="doSave">保存</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, Delete, View } from '@element-plus/icons-vue'
import { useStrategyStore } from '@/stores/strategy'
import { runScreener } from '@/api/strategy'
import request from '@/api/request'
import type { StockColumn } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import AppDialog from '@/components/ui/AppDialog.vue'
import StockTable from '@/components/stock/StockTable.vue'

const strategyStore = useStrategyStore()
const previewData = ref<any[]>([])
const showSaveDialog = ref(false)
const showPreview = ref(false)
const previewLoading = ref(false)
const previewError = ref(false)
const saveName = ref('')
const requireTriggered = ref<string[]>([])

const columns: StockColumn[] = [
  { key: 'compositeScore', label: '综合分', type: 'score', align: 'center', mobile: 'primary' },
  { key: 'triggered', label: '触发', align: 'center' },
  { key: 'signal', label: '信号', type: 'signal', align: 'center' },
]

function triggeredText(row: any) {
  const t = row.triggered || {}
  return `${Object.values(t).filter(Boolean).length}/${Object.keys(t).length}`
}

// Per-strategy params spec (loaded from backend)
const paramSpecs = ref<Record<string, any[]>>({})
const strategyParams = reactive<Record<string, Record<string, any>>>({})
const expanded = reactive<Record<string, boolean>>({})

function paramsOf(id: string) { return paramSpecs.value[id] || [] }
function toggleExpand(id: string) { expanded[id] = !expanded[id] }
function getParam(sid: string, name: string) {
  return strategyParams[sid]?.[name]
}
function setParam(sid: string, name: string, v: any) {
  if (!strategyParams[sid]) strategyParams[sid] = {}
  strategyParams[sid][name] = v
}

async function loadParamSpecs() {
  try {
    const list: any = await request.get('/strategies-meta')
    if (Array.isArray(list)) {
      const map: Record<string, any[]> = {}
      for (const s of list) {
        if (s.params?.length) map[s.id] = s.params
      }
      paramSpecs.value = map
    }
  } catch {}
}

const totalWeight = computed(() =>
  strategyStore.strategies.filter(s => s.enabled).reduce((sum, s) => sum + s.weight, 0)
)
const allEnabled = computed(() => strategyStore.strategies.every(s => s.enabled))
const allDisabled = computed(() => strategyStore.strategies.every(s => !s.enabled))

function setAll(enabled: boolean) {
  strategyStore.setAllStrategiesEnabled(enabled)
  if (!enabled) {
    requireTriggered.value = []
    previewData.value = []
  }
  ElMessage.success(enabled ? '已开启全部策略' : '已关闭全部策略')
}

function resetDefaults() {
  strategyStore.resetToDefault()
  requireTriggered.value = []
  previewData.value = []
  ElMessage.success('已恢复默认权重')
}

// Scale enabled strategy weights so they sum to exactly 100 while preserving
// proportions. Values are rounded to integers; the residue (max ±N) is
// absorbed by the heaviest weight so the total lands on a clean 100.
function normalizeWeights() {
  const enabled = strategyStore.strategies.filter(s => s.enabled)
  const sum = enabled.reduce((acc, s) => acc + s.weight, 0)
  if (sum <= 0) return
  const snapshot = enabled.map(s => ({ id: s.id, original: s.weight }))
  const heaviestId = snapshot.reduce((a, b) => (b.original > a.original ? b : a)).id

  const factor = 100 / sum
  let running = 0
  for (const item of snapshot) {
    const v = Math.max(1, Math.round(item.original * factor))
    strategyStore.updateWeight(item.id, v)
    running += v
  }
  const diff = 100 - running
  if (diff !== 0) {
    const cur = strategyStore.strategies.find(s => s.id === heaviestId)
    if (cur) strategyStore.updateWeight(heaviestId, Math.max(1, cur.weight + diff))
  }
  ElMessage.success('已等比归一化为 100%')
}

function openPreview() {
  showPreview.value = true
  previewResults()
}

async function previewResults() {
  previewLoading.value = true
  previewError.value = false
  try {
    previewData.value = await runScreener({
      strategies: strategyStore.getConfigMap(),
      strategyParams: strategyParams,
      filters: { minScore: 30, minMarketCap: 100, maxDebtRatio: 60, minRoe: 10, industries: [] },
      limit: 20,
      requireTriggered: requireTriggered.value,
    } as any)
  } catch {
    previewError.value = true
  } finally {
    previewLoading.value = false
  }
}

function clearTriggered() {
  requireTriggered.value = []
  previewResults()
}

function doSave() {
  if (!saveName.value.trim()) {
    ElMessage.warning('请输入方案名称')
    return
  }
  strategyStore.saveConfig(saveName.value.trim())
  showSaveDialog.value = false
  saveName.value = ''
  ElMessage.success(`方案已保存，可在「我的方案」中载入`)
}

function loadScheme(name: string) {
  strategyStore.loadConfig(name)
  ElMessage.success(`已载入方案「${name}」`)
}

function deleteScheme(name: string) {
  strategyStore.deleteConfig(name)
  ElMessage.success(`已删除方案「${name}」`)
}

onMounted(loadParamSpecs)
</script>

<style scoped>
.strategy-weights { display: flex; flex-direction: column; gap: 16px; }
.total-weight {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 14px; margin-bottom: 14px;
  background: var(--bg-2); border-radius: var(--radius);
}
.tw-label { font-size: 13px; color: var(--text-3); }
.tw-value { font-size: 18px; font-weight: 700; color: var(--text); }
.tw-hint { font-size: 12px; color: var(--text-4); flex: 1; }
.strategy-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.strategy-card {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  min-width: 0;
}
.strategy-card.off { opacity: 0.7; }
.strategy-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 4px;
}
.strategy-info { display: flex; gap: 12px; align-items: flex-start; min-width: 0; }
.strategy-meta { display: flex; flex-direction: column; min-width: 0; }
.strategy-name { font-size: 14px; font-weight: 600; color: var(--text); }
.strategy-desc { font-size: 12px; color: var(--text-3); margin-top: 2px; }
.weight-value { font-size: 20px; font-weight: 700; }
.weight-slider { padding: 0 4px; }
.strategy-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.params-grid {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--line);
  display: flex; flex-direction: column; gap: 8px;
}
.param-row { display: flex; flex-direction: column; gap: 2px; }
.param-head { display: flex; justify-content: space-between; }
.param-label { font-size: 12px; color: var(--text-3); }
.param-value { font-size: 12px; color: var(--text); font-weight: 600; }
.param-desc { font-size: 11px; color: var(--text-4); }

.preview-body { max-height: 68vh; overflow-y: auto; }
.preview-sub { margin: 0 0 10px; font-size: 12px; color: var(--text-3); }
.trigger-filter {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 10px 12px; margin-bottom: 12px;
  background: var(--bg-2); border-radius: 6px;
  border: 1px dashed var(--line);
}
.trigger-filter :deep(.el-checkbox) { margin-right: 12px; }

.scheme-list { display: flex; flex-direction: column; }
.scheme-row {
  display: flex; align-items: center; gap: 6px;
  border-bottom: 1px solid var(--line);
  padding: 2px 0;
}
.scheme-row:last-child { border-bottom: 0; }
.scheme-load {
  flex: 1; min-width: 0;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  border: 0; background: transparent; cursor: pointer;
  padding: 9px 6px;
  color: var(--text); font-size: 13px; text-align: left;
  border-radius: var(--radius-sm);
}
.scheme-load:hover { background: var(--surface-hover); }
.scheme-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scheme-meta { font-size: 11px; color: var(--text-4); flex-shrink: 0; }
.scheme-del { color: var(--text-4); cursor: pointer; flex-shrink: 0; }
.scheme-del:hover { color: var(--color-red); }
@media (max-width: 900px) {
  .strategy-list { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .strategy-weights { gap: 12px; }
}
</style>
