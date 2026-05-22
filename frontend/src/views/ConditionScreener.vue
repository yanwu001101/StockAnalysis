<template>
  <div class="page-container">
    <header class="page-head">
      <h1>条件选股</h1>
      <p class="dek">表单式条件构造器 · 财务/技术/资金多维 AND / OR 组合 · 类同花顺问财</p>
    </header>

    <div class="builder card glass-card">
      <div class="builder-head">
        <span class="builder-title">筛选条件</span>
        <el-radio-group v-model="logic" size="small">
          <el-radio-button value="AND">满足全部 (AND)</el-radio-button>
          <el-radio-button value="OR">满足任一 (OR)</el-radio-button>
        </el-radio-group>
        <div style="flex: 1;" />
        <el-button size="small" @click="addCondition">
          <el-icon><Plus /></el-icon>添加条件
        </el-button>
        <el-button type="primary" size="small" :loading="loading" @click="runQuery">
          <el-icon><Search /></el-icon>开始选股
        </el-button>
      </div>

      <div class="conditions-list">
        <div v-for="(c, i) in conditions" :key="i" class="cond-row">
          <span class="cond-idx">{{ i + 1 }}</span>
          <el-select v-model="c.field" size="small" placeholder="选指标" style="width: 200px;" @change="onFieldChange(i)">
            <el-option-group v-for="g in groupedFields" :key="g.label" :label="g.label">
              <el-option v-for="f in g.fields" :key="f.id" :label="f.label" :value="f.id" />
            </el-option-group>
          </el-select>
          <el-select v-model="c.op" size="small" placeholder="运算" style="width: 100px;">
            <el-option v-for="op in opsFor(c.field)" :key="op" :label="opLabel(op)" :value="op" />
          </el-select>
          <template v-if="fieldType(c.field) === 'number'">
            <el-input-number v-if="c.op !== 'between'" v-model="c.value" size="small"
                             style="flex: 1; min-width: 120px;" :step="0.5" controls-position="right" />
            <template v-else>
              <el-input-number v-model="c.value[0]" size="small" :step="0.5" placeholder="最小" />
              <span class="cond-sep">~</span>
              <el-input-number v-model="c.value[1]" size="small" :step="0.5" placeholder="最大" />
            </template>
          </template>
          <template v-else-if="fieldType(c.field) === 'bool'">
            <el-select v-model="c.value" size="small" style="flex: 1;">
              <el-option label="是" :value="true" />
              <el-option label="否" :value="false" />
            </el-select>
          </template>
          <template v-else-if="fieldType(c.field) === 'industry'">
            <el-select v-model="c.value" multiple collapse-tags size="small" filterable
                       style="flex: 1;" placeholder="选择行业">
              <el-option v-for="ind in industries" :key="ind" :label="ind" :value="ind" />
            </el-select>
          </template>
          <el-button link size="small" type="danger" @click="conditions.splice(i, 1)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
        <div v-if="!conditions.length" class="empty">
          <el-button @click="addCondition"><el-icon><Plus /></el-icon>添加第一个条件</el-button>
        </div>
      </div>
    </div>

    <div class="presets card glass-card">
      <span class="preset-label">快速模板:</span>
      <el-button size="small" @click="applyPreset('value')">价值股</el-button>
      <el-button size="small" @click="applyPreset('growth')">成长股</el-button>
      <el-button size="small" @click="applyPreset('momentum')">动量突破</el-button>
      <el-button size="small" @click="applyPreset('mainfund')">主力流入</el-button>
      <el-button size="small" @click="applyPreset('lowvol')">低波动白马</el-button>
    </div>

    <div class="card glass-card results-card" v-if="results.length">
      <div class="results-head">
        <h3>选股结果 ({{ results.length }})</h3>
      </div>
      <el-table :data="results" stripe size="small" @row-click="goStock"
                :row-style="{ cursor: 'pointer' }" empty-text="无数据">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="name" label="名称" width="100" />
        <el-table-column prop="code" label="代码" width="80" />
        <el-table-column prop="industry" label="行业" width="120" />
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
        <el-table-column prop="pe" label="PE" width="80" align="right" />
        <el-table-column prop="pb" label="PB" width="80" align="right" />
        <el-table-column prop="roe" label="ROE" width="80" align="right" />
        <el-table-column prop="debtRatio" label="负债率" width="90" align="right" />
        <el-table-column label="市值(亿)" width="100" align="right">
          <template #default="{ row }">{{ row.marketCap }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import { useRefreshable } from '@/composables/useRefreshable'

const router = useRouter()
const loading = ref(false)
const logic = ref<'AND' | 'OR'>('AND')
const conditions = ref<any[]>([
  { field: 'roe', op: '>=', value: 15 },
])
const fields = ref<any[]>([])
const results = ref<any[]>([])

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
  return { '>=': '≥', '<=': '≤', '>': '>', '<': '<', '==': '是', 'between': '介于', 'in': '属于', 'not_in': '不属于' }[op] || op
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

function goStock(row: any) { router.push(`/stock/${row.code}`) }

onMounted(loadFields)
useRefreshable('条件选股', runQuery, { autoRefresh: false })
</script>

<style scoped>
.page-head { margin-bottom: 18px; }
.page-head h1 { font-size: 22px; font-weight: 600; }
.page-head .dek { margin-top: 4px; color: var(--text-3); font-size: 13px; }
.card { padding: 16px 20px; margin-bottom: 14px; }
.builder-head {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 12px;
}
.builder-title { font-weight: 600; color: var(--text); margin-right: 6px; }
.conditions-list { display: flex; flex-direction: column; gap: 8px; }
.cond-row {
  display: flex; align-items: center; gap: 8px;
  padding: 8px;
  background: var(--surface-2);
  border-radius: 8px;
}
.cond-idx {
  width: 22px; height: 22px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: var(--brand-soft); color: var(--brand);
  font-size: 12px; font-weight: 600;
}
.cond-sep { color: var(--text-3); font-size: 12px; }
.empty { text-align: center; padding: 16px 0; color: var(--text-4); }
.presets {
  display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
}
.preset-label { color: var(--text-3); font-size: 13px; margin-right: 4px; }
.results-head { margin-bottom: 12px; }
.results-head h3 { margin: 0; font-size: 15px; }
</style>
