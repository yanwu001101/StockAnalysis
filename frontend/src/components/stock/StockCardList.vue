<template>
  <div class="stock-cards">
    <div v-if="sortableCols.length" class="sc-sortbar">
      <span class="sc-sort-label">排序</span>
      <button
        v-for="col in sortableCols"
        :key="col.key"
        type="button"
        class="sc-sort-btn"
        :class="{ active: sortKey === col.key }"
        @click="$emit('sort', col.key)"
      >{{ col.label }}<span v-if="sortKey === col.key" class="sc-sort-dir">{{ sortDir === 'desc' ? '↓' : '↑' }}</span></button>
    </div>

    <SkeletonRows v-if="loading && !rows.length" :rows="5" :row-height="56" :cells="2" :rank="rank" />

    <template v-else>
      <div
        v-for="(row, i) in rows"
        :key="rowId(row, i)"
        class="sc-item"
        :class="[{ clickable: isClickable(row) }, rowClass?.(row)]"
        @click="$emit('row-click', row)"
      >
        <span v-if="rank" class="sc-rank num">{{ i + 1 }}</span>
        <div class="sc-main">
          <div class="sc-head">
            <div class="sc-title-wrap">
              <span class="sc-title">{{ titleOf(row) }}</span>
              <span v-if="subtitleOf(row)" class="sc-sub mono">{{ subtitleOf(row) }}</span>
            </div>
            <div v-if="primaryCols.length" class="sc-primary">
              <span v-for="col in primaryCols" :key="col.key" class="sc-primary-cell">
                <slot :name="`cell-${col.key}`" :row="row" :value="valueOf(row, col)" :index="i">
                  <StockCell :row="row" :col="col" />
                </slot>
              </span>
            </div>
            <div v-if="$slots.actions" class="sc-actions" @click.stop>
              <slot name="actions" :row="row" :index="i" />
            </div>
          </div>
          <div v-if="secondaryCols.length" class="sc-secondary">
            <span v-for="col in secondaryCols" :key="col.key" class="sc-kv">
              <span class="sc-k">{{ col.label }}</span>
              <slot :name="`cell-${col.key}`" :row="row" :value="valueOf(row, col)" :index="i">
                <StockCell :row="row" :col="col" small />
              </slot>
            </span>
          </div>
        </div>
      </div>
      <EmptyState
        v-if="!rows.length"
        :variant="error ? 'error' : 'empty'"
        :title="error ? '数据加载失败' : empty"
        @retry="$emit('retry')"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { StockColumn } from '@/types/ui'
import { padCode } from '@/utils/score'
import StockCell from './StockCell.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import SkeletonRows from '@/components/ui/SkeletonRows.vue'

// 手机版列表：每行一张卡片。列的 mobile 属性决定落在标题 / 右侧大字 / 底部小字。
const props = withDefaults(defineProps<{
  rows: any[]
  columns: StockColumn[]
  stock?: boolean
  rank?: boolean
  loading?: boolean
  /** 空态文案；error=true 时作为失败说明展示 */
  empty?: string
  /** 请求失败：区分"没有数据"与"加载失败"（后者提供重试） */
  error?: boolean
  rowKey?: string
  nameKey?: string
  codeKey?: string
  industryKey?: string
  clickable?: boolean
  to?: (row: any) => string | null | undefined
  rowClass?: (row: any) => string | undefined
  sortKey?: string | null
  sortDir?: 'asc' | 'desc'
}>(), {
  stock: true, rank: false, loading: false, empty: '暂无数据', error: false,
  rowKey: 'code', nameKey: 'name', codeKey: 'code', industryKey: 'industry',
  clickable: true, sortKey: null, sortDir: 'desc',
})

defineEmits<{
  (e: 'row-click', row: any): void
  (e: 'sort', key: string): void
  (e: 'retry'): void
}>()

const visibleCols = computed(() => props.columns.filter(c => c.mobile !== 'hidden'))
const titleCol = computed(() =>
  visibleCols.value.find(c => c.mobile === 'title') ?? (props.stock ? null : visibleCols.value[0] ?? null))

const primaryCols = computed(() => {
  const explicit = visibleCols.value.filter(c => c.mobile === 'primary')
  if (explicit.length) return explicit
  // 没显式指定时：股票列表默认把价格和涨跌幅放右侧
  const defaults: StockColumn[] = []
  const price = visibleCols.value.find(c => c.type === 'price')
  const change = visibleCols.value.find(c => c.type === 'change')
  if (price) defaults.push(price)
  if (change) defaults.push(change)
  return defaults
})

const secondaryCols = computed(() => {
  const used = new Set<string>([...primaryCols.value.map(c => c.key)])
  if (titleCol.value) used.add(titleCol.value.key)
  return visibleCols.value.filter(c => !used.has(c.key) && c.mobile !== 'title')
})

const sortableCols = computed(() => props.columns.filter(c => c.sortable))

function valueOf(row: any, col: StockColumn) {
  return col.format ? col.format(row) : row?.[col.key]
}
function rowId(row: any, i: number) {
  const v = row?.[props.rowKey]
  return v == null ? i : `${v}-${i}`
}
function titleOf(row: any): string {
  if (props.stock) return row?.[props.nameKey] || padCode(row?.[props.codeKey]) || '—'
  const v = titleCol.value ? valueOf(row, titleCol.value) : null
  return v == null || v === '' ? '—' : String(v)
}
function subtitleOf(row: any): string {
  if (!props.stock) return ''
  const code = row?.[props.nameKey] ? padCode(row?.[props.codeKey]) : ''
  const ind = row?.[props.industryKey]
  return [code, ind].filter(Boolean).join(' · ')
}
function isClickable(row: any) {
  if (!props.clickable) return false
  if (props.to) return !!props.to(row)
  return !!row?.[props.codeKey]
}
</script>

<style scoped>
.stock-cards { display: flex; flex-direction: column; }
.sc-sortbar {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 0 10px;
  overflow-x: auto;
  scrollbar-width: none;
}
.sc-sortbar::-webkit-scrollbar { display: none; }
.sc-sort-label { font-size: 12px; color: var(--text-3); flex-shrink: 0; }
.sc-sort-btn {
  border: 0; background: var(--bg-2); color: var(--text-2);
  font-size: 12px; padding: 5px 10px; border-radius: var(--radius-pill);
  white-space: nowrap; cursor: pointer;
}
.sc-sort-btn.active { background: var(--brand-soft); color: var(--brand); font-weight: 600; }
.sc-sort-dir { margin-left: 2px; }

.sc-item {
  display: flex;
  gap: 10px;
  padding: 12px 2px;
  border-bottom: 1px solid var(--line);
  min-height: 56px;
}
.sc-item:last-of-type { border-bottom: 0; }
.sc-item.clickable { cursor: pointer; }
.sc-item.clickable:active { background: var(--surface-hover); }
.sc-rank { width: 20px; flex-shrink: 0; color: var(--text-4); font-size: 12px; padding-top: 3px; text-align: right; }
.sc-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.sc-head { display: flex; align-items: center; gap: 10px; }
.sc-title-wrap { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.sc-title { font-size: 15px; font-weight: 600; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sc-sub { font-size: 12px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sc-primary { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; flex-shrink: 0; }
.sc-primary-cell { font-size: 15px; font-weight: 600; }
.sc-primary-cell:nth-child(n+2) { font-size: 13px; font-weight: 500; }
.sc-actions { flex-shrink: 0; display: flex; align-items: center; }
.sc-secondary { display: flex; flex-wrap: wrap; gap: 4px 14px; }
.sc-kv { display: inline-flex; align-items: baseline; gap: 4px; font-size: 12px; color: var(--text-2); max-width: 100%; }
.sc-k { color: var(--text-4); white-space: nowrap; flex-shrink: 0; }
</style>
