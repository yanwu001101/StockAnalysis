<template>
  <div class="condition-screener">
    <AppCard title="筛选条件">
      <template #actions>
        <SegmentTabs v-model="logic" :options="logicOptions" small />
        <el-button size="small" @click="addCondition">
          <el-icon><Plus /></el-icon>添加条件
        </el-button>
        <el-button type="primary" size="small" :loading="loading" @click="runQuery">
          <el-icon><Search /></el-icon>开始选股
        </el-button>
      </template>

      <div class="conditions-list">
        <div v-for="(c, i) in conditions" :key="i" class="cond-row">
          <span class="cond-idx">{{ i + 1 }}</span>
          <el-select v-model="c.field" size="small" placeholder="选指标" class="cond-field" @change="onFieldChange(i)">
            <el-option-group v-for="g in groupedFields" :key="g.label" :label="g.label">
              <el-option v-for="f in g.fields" :key="f.id" :label="f.label" :value="f.id" />
            </el-option-group>
          </el-select>
          <el-select v-model="c.op" size="small" placeholder="运算" class="cond-op">
            <el-option v-for="op in opsFor(c.field)" :key="op" :label="opLabel(op)" :value="op" />
          </el-select>
          <template v-if="fieldType(c.field) === 'number'">
            <el-input-number v-if="c.op !== 'between'" v-model="c.value" size="small"
                             class="cond-value" :step="0.5" controls-position="right" />
            <template v-else>
              <el-input-number v-model="c.value[0]" size="small" :step="0.5" placeholder="最小" class="cond-value half" />
              <span class="cond-sep">~</span>
              <el-input-number v-model="c.value[1]" size="small" :step="0.5" placeholder="最大" class="cond-value half" />
            </template>
          </template>
          <template v-else-if="fieldType(c.field) === 'bool'">
            <el-select v-model="c.value" size="small" class="cond-value">
              <el-option label="是" :value="true" />
              <el-option label="否" :value="false" />
            </el-select>
          </template>
          <template v-else-if="fieldType(c.field) === 'industry'">
            <el-select v-model="c.value" multiple collapse-tags size="small" filterable
                       class="cond-value" placeholder="选择行业">
              <el-option v-for="ind in industries" :key="ind" :label="ind" :value="ind" />
            </el-select>
          </template>
          <el-button link size="small" type="danger" class="cond-del" @click="conditions.splice(i, 1)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
        <div v-if="!conditions.length" class="empty">
          <el-button @click="addCondition"><el-icon><Plus /></el-icon>添加第一个条件</el-button>
        </div>
      </div>

      <div class="presets">
        <span class="preset-label">快速模板</span>
        <el-button size="small" @click="applyPreset('value')">价值股</el-button>
        <el-button size="small" @click="applyPreset('growth')">成长股</el-button>
        <el-button size="small" @click="applyPreset('momentum')">动量突破</el-button>
        <el-button size="small" @click="applyPreset('mainfund')">主力流入</el-button>
        <el-button size="small" @click="applyPreset('lowvol')">低波动白马</el-button>
      </div>
    </AppCard>

    <AppCard v-if="results.length || loading" :title="`选股结果 (${results.length})`">
      <StockTable :rows="results" :columns="columns" rank :loading="loading" empty="没有股票满足条件" />
    </AppCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import { useRefreshable } from '@/composables/useRefreshable'
import type { StockColumn, SegmentOption } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import StockTable from '@/components/stock/StockTable.vue'

const loading = ref(false)
const logic = ref<'AND' | 'OR'>('AND')
const logicOptions: SegmentOption<'AND' | 'OR'>[] = [
  { label: '满足全部', value: 'AND' },
  { label: '满足任一', value: 'OR' },
]
const conditions = ref<any[]>([
  { field: 'roe', op: '>=', value: 15 },
])
const fields = ref<any[]>([])
const results = ref<any[]>([])

const columns: StockColumn[] = [
  { key: 'price', label: '最新价', type: 'price' },
  { key: 'changePercent', label: '涨跌幅', type: 'change' },
  { key: 'pe', label: 'PE', type: 'num', digits: 2 },
  { key: 'pb', label: 'PB', type: 'num', digits: 2 },
  { key: 'roe', label: 'ROE', type: 'percent', digits: 1 },
  { key: 'debtRatio', label: '负债率', type: 'percent', digits: 1 },
  { key: 'marketCap', label: '市值(亿)', type: 'num', digits: 0 },
]

const groupedFields = computed(() => [
  { label: '行情', fields: fields.value.filter(f => !f.source) },
  { label: '财务', fields: fields.value.filter(f => f.source === 'fund') },
  { label: '技术指标', fields: fields.value.filter(f => f.source === 'kline') },
  { label: '资金流', fields: fields.value.filter(f => f.source === 'flow') },
])

const industries = computed(() => {
  // populated by the backend response on first run (could also fetch separately)
  const set = new Set<string>()
  results.value.forEach(r => r.industry && set.add(r.industry))
  return Array.from(set).sort()
})

function fieldType(id: string) { return fields.value.find(f => f.id === id)?.type || 'number' }
function opsFor(id: string) { return fields.value.find(f => f.id === id)?.ops || ['>=', '<=', '>', '<'] }
function opLabel(op: string) {
  return ({ '>=': '≥', '<=': '≤', '>': '>', '<': '<', '==': '是', 'between': '介于', 'in': '属于', 'not_in': '不属于' } as Record<string, string>)[op] || op
}

function defaultValueFor(id: string) {
  const t = fieldType(id)
  if (t === 'bool') return true
  if (t === 'industry') return []
  return 10
}

function addCondition() {
  conditions.value.push({ field: 'pe', op: '<=', value: 30 })
}

function onFieldChange(i: number) {
  const c = conditions.value[i]
  const ops = opsFor(c.field)
  if (!ops.includes(c.op)) c.op = ops[0]
  c.value = defaultValueFor(c.field)
  if (c.op === 'between') c.value = [10, 30]
}

const PRESETS: Record<string, any> = {
  value: { logic: 'AND', conditions: [
    { field: 'pe', op: '<=', value: 25 },
    { field: 'pb', op: '<=', value: 3 },
    { field: 'roe', op: '>=', value: 12 },
    { field: 'debt_ratio', op: '<=', value: 60 },
  ]},
  growth: { logic: 'AND', conditions: [
    { field: 'revenue_yoy', op: '>=', value: 20 },
    { field: 'net_profit_yoy', op: '>=', value: 30 },
    { field: 'gross_margin', op: '>=', value: 30 },
  ]},
  momentum: { logic: 'AND', conditions: [
    { field: 'above_ma20', op: '==', value: true },
    { field: 'macd_golden_5d', op: '==', value: true },
    { field: 'volume_surge_2x', op: '==', value: true },
  ]},
  mainfund: { logic: 'AND', conditions: [
    { field: 'main_net_5d_strong', op: '==', value: true },
    { field: 'pct_change', op: '<=', value: 7 },
  ]},
  lowvol: { logic: 'AND', conditions: [
    { field: 'market_cap_yi', op: '>=', value: 500 },
    { field: 'roe', op: '>=', value: 15 },
    { field: 'above_ma60', op: '==', value: true },
  ]},
}

function applyPreset(name: string) {
  const p = PRESETS[name]
  if (!p) return
  logic.value = p.logic
  conditions.value = p.conditions.map((c: any) => ({ ...c }))
  ElMessage.success(`已应用「${name}」模板`)
}

async function loadFields() {
  try {
    const list: any = await request.get('/condition-fields')
    if (Array.isArray(list)) fields.value = list
  } catch {}
}

async function runQuery() {
  loading.value = true
  const cleaned = conditions.value
    .filter(c => c.field && c.op !== undefined && c.value !== undefined && c.value !== null)
    .filter(c => !(Array.isArray(c.value) && c.value.length === 0))
  if (!cleaned.length) {
    ElMessage.warning('请先添加至少一个条件')
    loading.value = false
    return
  }
  try {
    const data: any = await request.post('/screen/conditions', {
      logic: logic.value,
      conditions: cleaned,
      limit: 50,
    })
    results.value = Array.isArray(data) ? data : []
    if (results.value.length === 0) {
      ElMessage.info('没有股票满足条件，试试放宽参数或换个模板')
    } else {
      ElMessage.success(`找到 ${results.value.length} 只股票`)
    }
  } catch (e: any) {
    console.error('[conditions] query failed', e)
    ElMessage.error(`查询失败：${e?.message || e}`)
  } finally {
    loading.value = false
  }
}

onMounted(loadFields)
useRefreshable('条件选股', runQuery, { autoRefresh: false })
</script>

<style scoped>
.condition-screener { display: flex; flex-direction: column; gap: 16px; }
.conditions-list { display: flex; flex-direction: column; gap: 8px; }
.cond-row {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px;
  background: var(--surface-2);
  border-radius: 8px;
}
.cond-idx {
  width: 22px; height: 22px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: var(--brand-soft); color: var(--brand);
  font-size: 12px; font-weight: 600;
}
.cond-field { width: 200px; }
.cond-op { width: 100px; }
.cond-value { flex: 1; min-width: 120px; }
.cond-value.half { flex: 1; min-width: 90px; }
.cond-sep { color: var(--text-3); font-size: 12px; }
.empty { text-align: center; padding: 16px 0; color: var(--text-4); }
.presets {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--line);
}
.preset-label { color: var(--text-3); font-size: 13px; margin-right: 4px; }
@media (max-width: 768px) {
  .condition-screener { gap: 12px; }
  .cond-row { padding: 10px; }
  .cond-field { width: calc(100% - 34px); }
  .cond-op { width: 90px; }
  .cond-del { margin-left: auto; }
  .presets :deep(.el-button) { margin-left: 0; }
}
</style>
