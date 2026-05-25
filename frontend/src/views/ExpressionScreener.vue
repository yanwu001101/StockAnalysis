<template>
  <div class="page-container">
    <header class="page-head">
      <h1>表达式选股</h1>
      <p class="dek">Python-like 表达式 + 安全 AST eval · 支持时序函数 (MA/MACD/RSI/HHV/CROSS_UP) 与基本面字段</p>
    </header>

    <div class="layout">
      <div class="editor-col">
        <div class="card glass-card editor-card">
          <div class="editor-head">
            <span class="editor-title">表达式</span>
            <span class="hint" v-if="validation.ok === true">✓ 通过</span>
            <span class="hint err" v-else-if="validation.ok === false">{{ validation.error }}</span>
            <div style="flex: 1" />
            <el-button size="small" @click="validate">校验</el-button>
            <el-button type="primary" size="small" :loading="loading" @click="runQuery">运行</el-button>
          </div>
          <textarea v-model="expr" class="expr-area" spellcheck="false"
                    rows="6"
                    placeholder="例如：CLOSE > MA(CLOSE, 60) and MACD_GC(5) and V > MA(V, 20) * 2"
                    @input="validation.ok = null"></textarea>
        </div>

        <div class="card glass-card preset-card" v-if="examples.length">
          <span class="preset-label">示例:</span>
          <el-button v-for="ex in examples" :key="ex.name" size="small" link @click="applyExample(ex)">
            {{ ex.name }}
          </el-button>
        </div>

        <div class="card glass-card results-card" v-if="results.length">
          <h3>选股结果 ({{ results.length }})</h3>
          <el-table :data="results" stripe size="small" @row-click="goStock"
                    :row-style="{ cursor: 'pointer' }">
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
            <el-table-column label="市值(亿)" width="100" align="right">
              <template #default="{ row }">{{ formatNumber(row.marketCap, 0) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <div class="help-col">
        <div class="card glass-card help-card">
          <h3>语法手册</h3>
          <div v-for="group in fieldGroups" :key="group.category" class="help-group">
            <div class="help-head">{{ group.category }}</div>
            <div v-for="it in group.items" :key="it.name" class="help-item"
                 @click="insertToken(it.name.split(' ')[0])">
              <code class="help-name">{{ it.name }}</code>
              <span class="help-desc">{{ it.desc }}</span>
            </div>
          </div>
          <div class="help-group">
            <div class="help-head">运算符</div>
            <div class="help-item"><code>and / or / not</code><span>布尔逻辑</span></div>
            <div class="help-item"><code>&gt;= &lt;= &gt; &lt; ==</code><span>比较</span></div>
            <div class="help-item"><code>+ - * / **</code><span>算术</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import { useRefreshable } from '@/composables/useRefreshable'
import { formatNumber } from '@/utils/format'

const router = useRouter()
const expr = ref('PE > 0 and PE <= 25 and ROE >= 15 and DEBT <= 60')
const loading = ref(false)
const results = ref<any[]>([])
const fieldGroups = ref<any[]>([])
const examples = ref<any[]>([])
const validation = reactive<{ ok: boolean | null; error: string }>({ ok: null, error: '' })

async function loadHelp() {
  try {
    const d: any = await request.get('/expression/help')
    fieldGroups.value = d.fields || []
    examples.value = d.examples || []
  } catch {}
}

function insertToken(name: string) {
  expr.value = expr.value + (expr.value && !expr.value.endsWith(' ') ? ' ' : '') + name
}

function applyExample(ex: any) {
  expr.value = ex.expr
  validation.ok = null
}

async function validate() {
  try {
    const r: any = await request.post('/screen/expression/validate', { expression: expr.value })
    if (r?.ok) {
      validation.ok = true
      validation.error = ''
    } else {
      validation.ok = false
      validation.error = r?.error || '解析失败'
    }
  } catch (e: any) {
    validation.ok = false
    validation.error = e?.message || '校验失败'
  }
}

async function runQuery() {
  loading.value = true
  try {
    const data: any = await request.post('/screen/expression', {
      expression: expr.value,
      limit: 50,
      topUniverse: 300,
    })
    if (Array.isArray(data)) {
      results.value = data
      ElMessage.success(`找到 ${data.length} 只股票`)
    } else if (data?.error) {
      ElMessage.error(data.error)
      results.value = []
    } else {
      results.value = []
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '查询失败')
  } finally {
    loading.value = false
  }
}

function goStock(row: any) { router.push(`/stock/${row.code}`) }

onMounted(loadHelp)
useRefreshable('表达式选股', runQuery, { immediate: false, autoRefresh: false })
</script>

<style scoped>
.page-head { margin-bottom: 18px; }
.page-head h1 { font-size: 22px; font-weight: 600; }
.page-head .dek { margin-top: 4px; color: var(--text-3); font-size: 13px; }
.layout {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
}
.card { padding: 16px 18px; margin-bottom: 14px; }
.editor-card { padding-top: 12px; }
.editor-head {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 10px;
}
.editor-title { font-weight: 600; color: var(--text); }
.hint { color: var(--up); font-size: 12px; }
.hint.err { color: var(--down); }
.expr-area {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  background: var(--surface-2);
  color: var(--text);
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.7;
  resize: vertical;
  outline: none;
}
.expr-area:focus { border-color: var(--brand); }
.preset-card {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.preset-label { color: var(--text-3); font-size: 13px; margin-right: 4px; }
.results-card h3 { margin: 0 0 10px; font-size: 15px; }

.help-card { padding: 14px 16px; position: sticky; top: 16px; max-height: 80vh; overflow-y: auto; }
.help-card h3 { margin: 0 0 10px; font-size: 14px; color: var(--text); }
.help-group { margin-bottom: 14px; }
.help-head {
  font-size: 12px; font-weight: 600; color: var(--text-3);
  text-transform: uppercase; letter-spacing: 0.5px;
  margin-bottom: 6px;
}
.help-item {
  display: flex; align-items: baseline; gap: 8px;
  padding: 3px 6px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
}
.help-item:hover { background: var(--surface-hover); }
.help-name {
  font-family: 'JetBrains Mono', monospace;
  background: var(--brand-soft);
  color: var(--brand);
  padding: 1px 5px; border-radius: 3px;
  font-size: 11px;
  white-space: nowrap;
}
.help-desc { color: var(--text-3); font-size: 11px; }
@media (max-width: 1100px) {
  .layout { grid-template-columns: 1fr; }
  .help-card { position: static; max-height: none; }
}
</style>
