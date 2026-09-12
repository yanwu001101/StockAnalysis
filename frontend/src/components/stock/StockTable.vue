<template>
  <StockCardList
    v-if="isMobile"
    :rows="sortedRows"
    :columns="columns"
    :stock="stock"
    :rank="rank"
    :loading="loading"
    :empty="empty"
    :error="error"
    :row-key="rowKey"
    :name-key="nameKey"
    :code-key="codeKey"
    :industry-key="industryKey"
    :clickable="clickable"
    :to="to"
    :row-class="rowClass"
    :sort-key="sortKey"
    :sort-dir="sortDir"
    @row-click="onRowClick"
    @sort="toggleSort"
    @retry="$emit('retry')"
  >
    <template v-for="(_, name) in $slots" :key="name" #[name]="scope">
      <slot :name="name" v-bind="scope ?? {}" />
    </template>
  </StockCardList>

  <div v-else class="stock-table-wrap" :style="wrapStyle">
    <SkeletonRows v-if="loading && !rows.length" :rows="6" :row-height="dense ? 37 : 49" :cells="Math.min(columns.length, 4)" :rank="rank" />
    <table v-else class="stock-table" :class="{ dense, busy: loading }">
      <thead>
        <tr>
          <th v-if="rank" class="st-rank">#</th>
          <th v-if="stock" class="st-stock">{{ stockLabel }}</th>
          <th
            v-for="col in columns"
            :key="col.key"
            :class="[alignCls(col), { sortable: col.sortable, active: sortKey === col.key }]"
            :style="colStyle(col)"
            @click="col.sortable && toggleSort(col.key)"
          >
            {{ col.label }}
            <el-tooltip v-if="col.tooltip" :content="col.tooltip" placement="top">
              <el-icon class="st-info"><InfoFilled /></el-icon>
            </el-tooltip>
            <span v-if="col.sortable" class="st-sort">{{ sortArrow(col.key) }}</span>
          </th>
          <th v-if="$slots.actions" class="st-actions">{{ actionsLabel }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, i) in sortedRows"
          :key="rowId(row, i)"
          class="st-row"
          :class="[{ clickable: isClickable(row) }, rowClass?.(row)]"
          @click="onRowClick(row)"
        >
          <td v-if="rank" class="st-rank num">{{ i + 1 }}</td>
          <td v-if="stock" class="st-stock">
            <span class="st-name">{{ row?.[nameKey] || padCode(row?.[codeKey]) || '—' }}</span>
            <span v-if="subtitleOf(row)" class="st-code mono">{{ subtitleOf(row) }}</span>
          </td>
          <td v-for="col in columns" :key="col.key" :class="alignCls(col)">
            <slot :name="`cell-${col.key}`" :row="row" :value="valueOf(row, col)" :index="i">
              <StockCell :row="row" :col="col" />
            </slot>
          </td>
          <td v-if="$slots.actions" class="st-actions" @click.stop>
            <slot name="actions" :row="row" :index="i" />
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="colspan" class="st-empty-cell">
            <EmptyState
              v-if="error"
              variant="error"
              title="数据加载失败"
              :description="empty"
              @retry="$emit('retry')"
            />
            <EmptyState v-else variant="empty" :title="empty" />
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { InfoFilled } from '@element-plus/icons-vue'
import type { StockColumn } from '@/types/ui'
import { padCode, stockPath } from '@/utils/score'
import { useDevice } from '@/composables/useDevice'
import StockCell from './StockCell.vue'
import StockCardList from './StockCardList.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import SkeletonRows from '@/components/ui/SkeletonRows.vue'

// 全站唯一的股票列表：桌面渲染表格，手机自动切成卡片列表。
// 列由 columns 配置驱动，特殊单元格用 #cell-<key> 插槽覆盖，行尾操作用 #actions。
const props = withDefaults(defineProps<{
  rows: any[]
  columns: StockColumn[]
  /** 是否显示前置的"名称 / 代码·行业"列 */
  stock?: boolean
  stockLabel?: string
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
  /** 点击行是否跳转（默认跳个股详情） */
  clickable?: boolean
  /** 自定义跳转地址；返回空则该行不可点 */
  to?: (row: any) => string | null | undefined
  rowClass?: (row: any) => string | undefined
  maxHeight?: number | string
  dense?: boolean
  actionsLabel?: string
  /** 初始排序列（须是 sortable 的列） */
  defaultSort?: string
}>(), {
  stock: true, stockLabel: '名称', rank: false, loading: false, empty: '暂无数据', error: false,
  rowKey: 'code', nameKey: 'name', codeKey: 'code', industryKey: 'industry',
  clickable: true, dense: false, actionsLabel: '操作',
})

const emit = defineEmits<{
  (e: 'row-click', row: any): void
  (e: 'sort-change', payload: { key: string | null; dir: 'asc' | 'desc' }): void
  (e: 'retry'): void
}>()

const router = useRouter()
const { isMobile } = useDevice()

const sortKey = ref<string | null>(props.defaultSort ?? null)
const sortDir = ref<'asc' | 'desc'>('desc')

function valueOf(row: any, col: StockColumn) {
  return col.format ? col.format(row) : row?.[col.key]
}

const sortedRows = computed(() => {
  const key = sortKey.value
  if (!key) return props.rows
  const col = props.columns.find(c => c.key === key)
  if (!col) return props.rows
  const dir = sortDir.value === 'desc' ? -1 : 1
  return [...props.rows].sort((a, b) => {
    const va = Number(valueOf(a, col))
    const vb = Number(valueOf(b, col))
    const na = Number.isFinite(va), nb = Number.isFinite(vb)
    if (!na && !nb) return 0
    if (!na) return 1
    if (!nb) return -1
    return (va - vb) * dir
  })
})

function toggleSort(key: string) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
  else { sortKey.value = key; sortDir.value = 'desc' }
  emit('sort-change', { key: sortKey.value, dir: sortDir.value })
}
function sortArrow(key: string) {
  // 只在激活列显示方向箭头，避免每列都有箭头互相干扰
  if (sortKey.value !== key) return ''
  return sortDir.value === 'desc' ? '↓' : '↑'
}

function alignCls(col: StockColumn) {
  return col.align ? `st-${col.align}` : (col.type && col.type !== 'text' ? 'st-right' : 'st-left')
}
function colStyle(col: StockColumn) {
  if (!col.width) return undefined
  const w = typeof col.width === 'number' ? `${col.width}px` : col.width
  return { width: w, minWidth: w }
}
function rowId(row: any, i: number) {
  const v = row?.[props.rowKey]
  return v == null ? i : `${v}-${i}`
}
function subtitleOf(row: any): string {
  const code = row?.[props.nameKey] ? padCode(row?.[props.codeKey]) : ''
  const ind = row?.[props.industryKey]
  return [code, ind].filter(Boolean).join(' · ')
}
function isClickable(row: any) {
  if (!props.clickable) return false
  if (props.to) return !!props.to(row)
  return !!row?.[props.codeKey]
}
function onRowClick(row: any) {
  emit('row-click', row)
  if (!isClickable(row)) return
  const target = props.to ? props.to(row) : stockPath(row[props.codeKey])
  if (target) router.push(target)
}

const colspan = computed(() => props.columns.length + (props.rank ? 1 : 0) + (props.stock ? 1 : 0) + 1)
const wrapStyle = computed(() => props.maxHeight
  ? { maxHeight: typeof props.maxHeight === 'number' ? `${props.maxHeight}px` : props.maxHeight, overflowY: 'auto' as const }
  : undefined)
</script>

<style scoped>
.stock-table-wrap { width: 100%; overflow-x: auto; }
.st-skeleton { padding: 8px 0; }
.stock-table { width: 100%; border-collapse: collapse; }
.stock-table.busy tbody { opacity: 0.6; }
.stock-table th {
  text-align: left;
  font-weight: 500;
  font-size: 12px;
  color: var(--text-3);
  padding: 10px 8px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  position: sticky;
  top: 0;
  z-index: 1;
  white-space: nowrap;
}
.stock-table th.sortable { cursor: pointer; user-select: none; }
.stock-table th.sortable:hover, .stock-table th.active { color: var(--text); }
.st-sort { font-size: 11px; margin-left: 2px; color: var(--text-4); }
.stock-table th.active .st-sort { color: var(--brand); }
.st-info { vertical-align: -2px; margin-left: 2px; color: var(--text-4); }
.stock-table td {
  padding: 12px 8px;
  font-size: 14px;
  color: var(--text-2);
  border-bottom: 1px solid var(--line);
  vertical-align: middle;
  font-variant-numeric: tabular-nums;
}
.stock-table.dense td { padding: 8px; font-size: 13px; }
.stock-table tbody tr:last-child td { border-bottom: 0; }
.st-row.clickable { cursor: pointer; transition: background 0.15s ease; }
.st-row.clickable:hover { background: var(--surface-hover); }
.st-rank { width: 32px; color: var(--text-4); font-size: 12px; }
.st-stock { min-width: 120px; }
.st-name { display: block; font-weight: 500; color: var(--text); white-space: nowrap; }
.st-code { display: block; font-size: 12px; color: var(--text-3); margin-top: 1px; white-space: nowrap; }
.st-left { text-align: left; }
.st-center { text-align: center; }
.st-right { text-align: right; }
.st-actions { text-align: center; width: 1%; white-space: nowrap; }
.st-empty-cell { text-align: center; padding: 8px 0 !important; }
.st-text { overflow-wrap: anywhere; }
</style>
