<template>
  <div class="expression-screener" :class="{ mobile: isMobile }">
    <div class="editor-col">
      <AppCard title="表达式">
        <template #actions>
          <span class="hint" v-if="validation.ok === true">✓ 通过</span>
          <span class="hint err" v-else-if="validation.ok === false">{{ validation.error }}</span>
          <el-button size="small" @click="validate">校验</el-button>
          <el-button type="primary" size="small" :loading="loading" @click="runQuery">运行</el-button>
        </template>
        <textarea v-model="expr" class="expr-area" spellcheck="false"
                  rows="5"
                  placeholder="例如：CLOSE > MA(CLOSE, 60) and MACD_GC(5) and V > MA(V, 20) * 2"
                  @input="validation.ok = null"></textarea>
        <div class="preset-row" v-if="examples.length">
          <span class="preset-label">示例</span>
          <el-button v-for="ex in examples" :key="ex.name" size="small" link @click="applyExample(ex)">
            {{ ex.name }}
          </el-button>
        </div>
      </AppCard>

      <AppCard v-if="isMobile" flush class="help-fold">
        <el-collapse>
          <el-collapse-item title="语法手册" name="help">
            <div class="help-body"><HelpList /></div>
          </el-collapse-item>
        </el-collapse>
      </AppCard>

      <AppCard v-if="results.length || loading" :title="`选股结果 (${results.length})`">
        <StockTable :rows="results" :columns="columns" rank :loading="loading" empty="没有股票满足表达式" />
      </AppCard>
    </div>

    <div v-if="!isMobile" class="help-col">
      <AppCard title="语法手册" class="help-card"><HelpList /></AppCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, h, defineComponent } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import { useRefreshable } from '@/composables/useRefreshable'
import { useDevice } from '@/composables/useDevice'
import type { StockColumn } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import StockTable from '@/components/stock/StockTable.vue'

const { isMobile } = useDevice()
const expr = ref('PE > 0 and PE <= 25 and ROE >= 15 and DEBT <= 60')
const loading = ref(false)
const results = ref<any[]>([])
const fieldGroups = ref<any[]>([])
const examples = ref<any[]>([])
const validation = reactive<{ ok: boolean | null; error: string }>({ ok: null, error: '' })

const columns: StockColumn[] = [
  { key: 'price', label: '最新价', type: 'price' },
  { key: 'changePercent', label: '涨跌幅', type: 'change' },
  { key: 'pe', label: 'PE', type: 'num', digits: 2 },
  { key: 'pb', label: 'PB', type: 'num', digits: 2 },
  { key: 'roe', label: 'ROE', type: 'percent', digits: 1 },
  { key: 'marketCap', label: '市值(亿)', type: 'num', digits: 0 },
]

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

// 语法手册在桌面右栏与手机折叠面板里各渲染一次，用内联组件避免重复模板。
const HelpList = defineComponent({
  setup() {
    return () => [
      ...fieldGroups.value.map(group => h('div', { class: 'help-group', key: group.category }, [
        h('div', { class: 'help-head' }, group.category),
        ...(group.items || []).map((it: any) => h('div', {
          class: 'help-item', key: it.name, onClick: () => insertToken(String(it.name).split(' ')[0]),
        }, [
          h('code', { class: 'help-name' }, it.name),
          h('span', { class: 'help-desc' }, it.desc),
        ])),
      ])),
      h('div', { class: 'help-group' }, [
        h('div', { class: 'help-head' }, '运算符'),
        h('div', { class: 'help-item' }, [h('code', { class: 'help-name' }, 'and / or / not'), h('span', { class: 'help-desc' }, '布尔逻辑')]),
        h('div', { class: 'help-item' }, [h('code', { class: 'help-name' }, '>= <= > < =='), h('span', { class: 'help-desc' }, '比较')]),
        h('div', { class: 'help-item' }, [h('code', { class: 'help-name' }, '+ - * / **'), h('span', { class: 'help-desc' }, '算术')]),
      ]),
    ]
  },
})

onMounted(loadHelp)
useRefreshable('表达式选股', runQuery, { immediate: false, autoRefresh: false })
</script>

<style scoped>
.expression-screener {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  align-items: start;
}
.expression-screener.mobile { grid-template-columns: 1fr; gap: 12px; }
.editor-col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.expression-screener.mobile .editor-col { gap: 12px; }
.hint { color: var(--brand); font-size: 12px; }
.hint.err { color: var(--up); }
.expr-area {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  background: var(--surface-2);
  color: var(--text);
  font-family: var(--font-num);
  font-size: 13px;
  line-height: 1.7;
  resize: vertical;
  outline: none;
}
.expr-area:focus { border-color: var(--brand); }
.preset-row { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; margin-top: 10px; }
.preset-label { color: var(--text-3); font-size: 13px; margin-right: 4px; }

.help-card { position: sticky; top: 16px; max-height: 80vh; overflow-y: auto; }
.help-fold :deep(.el-collapse) { border: 0; }
.help-fold :deep(.el-collapse-item__header) { padding: 0 14px; font-weight: 600; border: 0; background: transparent; }
.help-fold :deep(.el-collapse-item__wrap) { border: 0; background: transparent; }
.help-fold :deep(.el-collapse-item__content) { padding: 0 14px 12px; }
:deep(.help-group) { margin-bottom: 14px; }
:deep(.help-head) {
  font-size: 12px; font-weight: 600; color: var(--text-3);
  text-transform: uppercase; letter-spacing: 0.5px;
  margin-bottom: 6px;
}
:deep(.help-item) {
  display: flex; align-items: baseline; gap: 8px;
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
}
:deep(.help-item:hover) { background: var(--surface-hover); }
:deep(.help-name) {
  font-family: var(--font-num);
  background: var(--brand-soft);
  color: var(--brand);
  padding: 1px 5px; border-radius: 3px;
  font-size: 11px;
  white-space: nowrap;
}
:deep(.help-desc) { color: var(--text-3); font-size: 11px; }
@media (max-width: 1100px) {
  .expression-screener { grid-template-columns: 1fr; }
  .help-card { position: static; max-height: none; }
}
</style>
