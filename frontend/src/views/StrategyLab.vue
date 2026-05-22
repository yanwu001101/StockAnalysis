<template>
  <div class="page-container">
    <div class="lab-header glass-card">
      <div class="header-info">
        <h2>策略实验室</h2>
        <p class="desc">自定义策略权重，打造专属选股模型</p>
      </div>
      <div class="header-actions">
        <el-button size="small" @click="strategyStore.resetToDefault()">恢复默认</el-button>
        <el-button size="small" @click="showSaveDialog = true">保存方案</el-button>
        <el-button type="primary" size="small" @click="previewResults">
          <el-icon><View /></el-icon>预览结果
        </el-button>
      </div>
    </div>

    <div class="strategy-list">
      <div class="strategy-card glass-card" v-for="s in strategyStore.strategies" :key="s.id">
        <div class="strategy-top">
          <div class="strategy-info">
            <el-switch v-model="s.enabled" @change="strategyStore.toggleStrategy(s.id)" />
            <div class="strategy-meta">
              <span class="strategy-name">{{ s.name }}</span>
              <span class="strategy-desc">{{ s.description }}</span>
            </div>
          </div>
          <div class="strategy-actions">
            <span class="weight-label">权重</span>
            <span class="weight-value" :style="{ color: s.color }">{{ s.weight }}%</span>
            <el-button v-if="paramsOf(s.id).length" link size="small"
                       @click="toggleExpand(s.id)">
              {{ expanded[s.id] ? '收起' : '调参' }}
              <el-icon><component :is="expanded[s.id] ? 'ArrowUp' : 'ArrowDown'" /></el-icon>
            </el-button>
          </div>
        </div>
        <div class="weight-slider">
          <el-slider v-model="s.weight" :min="0" :max="50" :step="1" :disabled="!s.enabled" @change="(v: number) => strategyStore.updateWeight(s.id, v)" />
        </div>
        <div class="params-grid" v-if="expanded[s.id]">
          <div class="param-row" v-for="p in paramsOf(s.id)" :key="p.name">
            <div class="param-head">
              <span class="param-label">{{ p.label }}</span>
              <span class="param-value">{{ getParam(s.id, p.name) ?? p.default }}</span>
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

    <div class="glass-card total-weight-card">
      <span>总权重: </span>
      <span :class="totalWeight === 100 ? 'weight-ok' : totalWeight > 100 ? 'weight-over' : 'weight-under'">
        {{ totalWeight }}%
      </span>
      <span class="weight-hint" v-if="totalWeight !== 100">(建议调整至 100%)</span>
    </div>

    <div class="glass-card preview-card" v-if="previewData.length">
      <h3>预览结果 (Top 20)</h3>
      <el-table :data="previewData" stripe size="small" @row-click="$router.push(`/stock/${$event.code}`)" :row-style="{ cursor: 'pointer' }">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="name" label="名称" width="100" />
        <el-table-column prop="code" label="代码" width="80" />
        <el-table-column prop="compositeScore" label="综合分" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.compositeScore >= 80 ? 'success' : 'warning'" size="small" effect="dark">{{ row.compositeScore }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="signal" label="信号" width="70" align="center">
          <template #default="{ row }">
            <span :class="['signal', row.signal]">{{ ({ bullish: '看多', bearish: '看空', neutral: '中性' } as Record<string, string>)[row.signal] }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="showSaveDialog" title="保存策略方案" width="400px">
      <el-input v-model="saveName" placeholder="输入方案名称" />
      <template #footer>
        <el-button @click="showSaveDialog = false">取消</el-button>
        <el-button type="primary" @click="doSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useStrategyStore } from '@/stores/strategy'
import { runScreener } from '@/api/strategy'
import request from '@/api/request'
import { useRefreshable } from '@/composables/useRefreshable'

const strategyStore = useStrategyStore()
const previewData = ref<any[]>([])
const showSaveDialog = ref(false)
const saveName = ref('')

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

async function previewResults() {
  try {
    previewData.value = await runScreener({
      strategies: strategyStore.getConfigMap(),
      strategyParams: strategyParams,
      filters: { minScore: 30, minMarketCap: 100, maxDebtRatio: 60, minRoe: 10, industries: [] },
      limit: 20,
    } as any)
    ElMessage.success(`预览完成，共 ${previewData.value.length} 只`)
  } catch {
    ElMessage.error('预览失败')
  }
}

function doSave() {
  if (!saveName.value.trim()) {
    ElMessage.warning('请输入方案名称')
    return
  }
  strategyStore.saveConfig(saveName.value.trim())
  showSaveDialog.value = false
  saveName.value = ''
  ElMessage.success('方案已保存')
}

onMounted(loadParamSpecs)
useRefreshable('策略实验室', previewResults, { immediate: false, autoRefresh: false })
</script>

<style scoped>
.lab-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  margin-bottom: 16px;
}
.lab-header h2 { margin: 0; font-size: 20px; color: var(--text-primary); }
.desc { margin: 4px 0 0; font-size: 13px; color: var(--text-muted); }
.header-actions { display: flex; gap: 8px; }
.strategy-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.strategy-card {
  padding: 16px;
  transition: all 0.3s;
}
.strategy-card:hover {
  border-color: var(--glass-border-hover);
}
.strategy-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}
.strategy-info {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.strategy-meta { display: flex; flex-direction: column; }
.strategy-name { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.strategy-desc { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.strategy-weight { text-align: right; }
.weight-label { font-size: 12px; color: var(--text-muted); display: block; }
.weight-value { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
.weight-slider { padding: 0 4px; }
.strategy-actions {
  display: flex; align-items: center; gap: 8px;
}
.params-grid {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--line);
  display: flex; flex-direction: column; gap: 8px;
}
.param-row { display: flex; flex-direction: column; gap: 2px; }
.param-head { display: flex; justify-content: space-between; }
.param-label { font-size: 12px; color: var(--text-3); }
.param-value { font-size: 12px; color: var(--text); font-weight: 600; font-variant-numeric: tabular-nums; }
.param-desc { font-size: 11px; color: var(--text-4); }
.total-weight-card {
  padding: 16px 24px;
  margin-bottom: 16px;
  font-size: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.weight-ok { color: #2AE8A4; font-weight: 700; }
.weight-over { color: #FF4757; font-weight: 700; }
.weight-under { color: #FFC312; font-weight: 700; }
.weight-hint { font-size: 13px; color: var(--text-muted); }
.preview-card { padding: 20px; }
.preview-card h3 { margin: 0 0 12px; font-size: 16px; color: var(--text-primary); }
.signal { font-size: 12px; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
.signal.bullish { background: rgba(255,71,87,0.15); color: #FF4757; }
.signal.bearish { background: rgba(42,232,164,0.15); color: #2AE8A4; }
.signal.neutral { background: rgba(136,146,164,0.15); color: #8892A4; }
@media (max-width: 900px) { .strategy-list { grid-template-columns: 1fr; } }
</style>
