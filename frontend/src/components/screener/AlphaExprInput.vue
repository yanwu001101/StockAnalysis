<template>
  <div class="alpha-expr" ref="rootEl">
    <el-input ref="inputEl" :model-value="modelValue" type="textarea" :rows="rows" spellcheck="false"
              class="expr-input" placeholder="例如 -pct_chg(close, 20) 或 rank(roe) - rank(debt)"
              @update:model-value="$emit('update:modelValue', String($event ?? ''))" />
    <div class="expr-tools">
      <el-select :model-value="''" placeholder="插入示例因子" size="small" style="width: 170px"
                 @change="(v: string) => { if (v) { $emit('update:modelValue', v) ; $emit('change', v) } }">
        <el-option v-for="ex in (help?.examples ?? [])" :key="ex.name" :label="ex.name" :value="ex.expr">
          <span class="ex-name">{{ ex.name }}</span>
          <span class="ex-desc">{{ ex.desc }}</span>
        </el-option>
      </el-select>
      <el-popover trigger="click" :width="380">
        <template #reference>
          <el-button size="small" plain>字段 / 算子</el-button>
        </template>
        <div class="alpha-help">
          <div v-for="g in (help?.fields ?? [])" :key="g.category" class="alpha-help-group">
            <div class="alpha-help-cat">{{ g.category }}</div>
            <div v-for="it in g.items" :key="it.name" class="alpha-help-item" @click="insertToken(it.name)">
              <code>{{ it.name }}</code><span>{{ it.desc }}</span>
            </div>
          </div>
          <div v-if="help?.notes?.length" class="alpha-help-notes">
            <div v-for="n in help.notes" :key="n">· {{ n }}</div>
          </div>
        </div>
      </el-popover>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getAlphaHelp } from '@/api/strategy'
import type { AlphaHelp } from '@/api/strategy'

defineProps<{ modelValue: string; rows?: number }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void; (e: 'change', v: string): void }>()

const help = ref<AlphaHelp | null>(null)
const rootEl = ref<HTMLElement | null>(null)
const inputEl = ref<{ textarea?: HTMLTextAreaElement } | null>(null)
onMounted(() => { getAlphaHelp().then(h => { help.value = h }).catch(() => { /* 帮助面板失败不影响主流程 */ }) })

/** 点击帮助项：字段直接插入，算子补一对括号，光标落括号内。 */
function insertToken(token: string) {
  const cur = inputEl.value?.textarea ?? null
  const pos = cur ? cur.selectionStart ?? 0 : 0
  const value = cur?.value ?? ''
  const before = value.slice(0, pos)
  const after = value.slice(pos)
  const base = token.split('(')[0]
  const isOp = token.includes('(') && base === base.toUpperCase() && /[A-Z]/.test(base)
  const insert = isOp ? `${base}()` : base
  emit('update:modelValue', before + insert + after)
  requestAnimationFrame(() => {
    if (cur) {
      cur.focus()
      const p = before.length + insert.length - (isOp ? 1 : 0)
      cur.selectionStart = cur.selectionEnd = p
    }
  })
}
</script>

<style scoped>
.alpha-expr { display: flex; flex-direction: column; gap: 8px; }
.expr-input :deep(textarea) { font-family: Consolas, Monaco, monospace; font-size: 12px; }
.expr-tools { display: flex; gap: 8px; }
.ex-name { font-size: 12px; }
.ex-desc { float: right; font-size: 11px; color: var(--text-3); margin-left: 12px; }
.alpha-help { max-height: 380px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.alpha-help-cat { font-size: 11px; color: var(--text-3); margin-bottom: 4px; }
.alpha-help-item { display: flex; gap: 8px; align-items: baseline; padding: 3px 4px; border-radius: 6px; cursor: pointer; }
.alpha-help-item:hover { background: var(--surface-hover); }
.alpha-help-item code { font-size: 12px; color: var(--brand); white-space: nowrap; }
.alpha-help-item span { font-size: 11px; color: var(--text-3); }
.alpha-help-notes { font-size: 11px; color: var(--text-3); line-height: 1.7; border-top: 1px solid var(--line); padding-top: 8px; }
</style>
