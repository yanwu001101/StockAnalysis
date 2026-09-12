<template>
  <div class="rank-list">
    <div
      v-for="(r, i) in shown"
      :key="r[codeKey] ?? i"
      class="rank-row"
      :class="{ clickable: !!r[codeKey] }"
      @click="go(r)"
    >
      <span class="rank-i num">{{ i + 1 }}</span>
      <span class="rank-name">{{ r[nameKey] || padCode(r[codeKey]) }}</span>
      <span v-if="r[nameKey]" class="rank-code mono">{{ padCode(r[codeKey]) }}</span>
      <span class="rank-val">
        <slot name="value" :row="r">
          <ChangeText v-if="valueType === 'change'" :value="r[valueKey]" />
          <ScorePill v-else-if="valueType === 'score'" :score="r[valueKey]" size="sm" />
          <span v-else class="num">{{ r[valueKey] ?? '—' }}</span>
        </slot>
      </span>
    </div>
    <div v-if="!shown.length" class="rank-empty">{{ empty }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { padCode, stockPath } from '@/utils/score'
import ChangeText from './ChangeText.vue'
import ScorePill from './ScorePill.vue'

// 紧凑排名列表（涨跌榜、各策略 Top 榜等），点击进详情。
const props = withDefaults(defineProps<{
  rows: any[]
  limit?: number
  valueKey?: string
  valueType?: 'change' | 'score' | 'text'
  nameKey?: string
  codeKey?: string
  empty?: string
}>(), { limit: 10, valueKey: 'changePercent', valueType: 'change', nameKey: 'name', codeKey: 'code', empty: '暂无数据' })

const router = useRouter()
const shown = computed(() => (props.rows || []).slice(0, props.limit))

function go(r: any) {
  if (r?.[props.codeKey]) router.push(stockPath(r[props.codeKey]))
}
</script>

<style scoped>
.rank-list { display: flex; flex-direction: column; }
.rank-row {
  display: grid;
  grid-template-columns: 22px 1fr auto auto;
  gap: 8px;
  align-items: center;
  padding: 8px 4px;
  font-size: 13px;
  border-bottom: 1px solid var(--line);
  min-height: 40px;
}
.rank-row:last-child { border-bottom: 0; }
.rank-row.clickable { cursor: pointer; }
.rank-row.clickable:hover { background: var(--surface-hover); }
.rank-i { color: var(--text-4); font-size: 12px; }
.rank-name { font-weight: 500; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank-code { font-size: 11px; color: var(--text-3); }
.rank-val { text-align: right; font-weight: 500; min-width: 56px; }
.rank-empty { padding: 30px 0; text-align: center; color: var(--text-4); font-size: 12px; }
</style>
