<template>
  <AppCard title="我的持仓" sub="手工录入或导入同花顺/券商导出表">
    <template #actions>
      <el-button size="small" plain @click="$emit('import')">导入</el-button>
      <el-button size="small" type="primary" plain @click="$emit('add')">新增</el-button>
    </template>

    <div v-if="positions.length" class="position-list">
      <article v-for="row in positions" :key="row.id" class="position-row">
        <div class="pr-head">
          <router-link class="stock-link" :to="stockPath(row.code)">{{ row.name || row.code }}</router-link>
          <span class="code mono">{{ row.code }} · {{ row.industry || '行业待同步' }}</span>
        </div>
        <div class="position-numbers">
          <b class="num">{{ Number(row.shares || 0).toFixed(0) }} 股</b>
          <span>成本 {{ fixedOrDash(row.avgCost) }} / 现价 {{ fixedOrDash(row.price) }}</span>
        </div>
        <div class="row-actions">
          <el-button text size="small" @click="$emit('edit', row)">编辑</el-button>
          <el-button text type="danger" size="small" @click="$emit('remove', row.id)">删除</el-button>
        </div>
      </article>
    </div>
    <el-empty v-else description="暂无持仓，先导入或录入一只股票" :image-size="88" />
  </AppCard>
</template>

<script setup lang="ts">
import { fixedOrDash } from '@/utils/format'
import { stockPath } from '@/utils/score'
import AppCard from '@/components/ui/AppCard.vue'

defineProps<{ positions: any[] }>()
defineEmits<{
  (e: 'add'): void
  (e: 'import'): void
  (e: 'edit', row: any): void
  (e: 'remove', id: number): void
}>()
</script>

<style scoped>
.position-list { display: flex; flex-direction: column; gap: 10px; }
.position-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 6px 10px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
}
.pr-head { display: flex; flex-direction: column; min-width: 0; }
.stock-link { color: var(--text); font-weight: 700; text-decoration: none; }
.code { color: var(--text-3); font-size: 12px; margin-top: 2px; }
.position-numbers {
  grid-column: 1 / -1;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: var(--text-3);
  font-size: 13px;
}
.position-numbers b { color: var(--text); }
.row-actions { grid-column: 2; grid-row: 1; display: flex; justify-content: flex-end; }
</style>
