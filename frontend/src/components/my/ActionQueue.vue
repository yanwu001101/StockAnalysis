<template>
  <AppCard title="操作队列" sub="按优先级排序，先处理风险，再考虑买入和做 T">
    <template #actions><span class="muted">策略引擎 v2</span></template>

    <div v-if="items.length" class="action-list">
      <article
        v-for="item in items"
        :key="item.id"
        class="action-card"
        :class="`action-${item.actionType || 'info'}`"
      >
        <div class="action-top">
          <div>
            <h4>
              <router-link class="name-link" :to="stockPath(item.code)">{{ item.name || item.code }}</router-link>
              <span class="mono">{{ item.code }}</span>
            </h4>
            <p>{{ item.ruleSummary }}</p>
          </div>
          <el-tag :type="tagType(item.actionType)" effect="light">{{ item.actionLabel }}</el-tag>
        </div>

        <StatGrid :items="ticket(item)" :cols="isMobile ? 2 : 4" size="sm" class="trade-ticket" />

        <div class="strategy-strip">
          <span>策略共识</span>
          <b>{{ consensusText(item) }}</b>
        </div>

        <div class="strategy-tags" v-if="(item.strategyConsensus?.topBullish?.length || 0) + (item.strategyConsensus?.topBearish?.length || 0)">
          <el-tag v-for="s in item.strategyConsensus?.topBullish || []" :key="`b-${item.id}-${s.id}`" type="success" effect="plain" size="small">
            {{ s.name }} {{ fixedOrDash(s.score, 0) }}
          </el-tag>
          <el-tag v-for="s in item.strategyConsensus?.topBearish || []" :key="`r-${item.id}-${s.id}`" type="danger" effect="plain" size="small">
            {{ s.name }} {{ fixedOrDash(s.score, 0) }}
          </el-tag>
        </div>

        <ul class="reason-list">
          <li v-for="r in item.reasons" :key="r">{{ r }}</li>
        </ul>
        <div class="step-box" v-if="item.steps?.length">
          <strong>新手操作</strong>
          <span v-for="s in item.steps" :key="s">{{ s }}</span>
        </div>
      </article>
    </div>
    <el-empty v-else description="录入持仓后生成买卖和做 T 建议" :image-size="90" />
  </AppCard>
</template>

<script setup lang="ts">
import { fixedOrDash, formatMoney } from '@/utils/format'
import { stockPath } from '@/utils/score'
import { useDevice } from '@/composables/useDevice'
import type { StatItem } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import StatGrid from '@/components/ui/StatGrid.vue'

defineProps<{ items: any[] }>()
const { isMobile } = useDevice()

function tagType(type: string) {
  if (type === 'danger') return 'danger'
  if (type === 'warning') return 'warning'
  if (type === 'success') return 'success'
  return 'info'
}

function consensusText(item: any) {
  const c = item.strategyConsensus || {}
  const effective = Number(c.effective || 0)
  if (!effective) return '暂无足够策略数据'
  return `${c.bullish || 0} 看多 / ${c.bearish || 0} 看空 / ${c.triggered || 0} 触发`
}

function ticket(item: any): StatItem[] {
  return [
    { label: '建议股数', value: item.suggestedShares || 0 },
    { label: '预估金额', value: formatMoney(item.suggestedAmount) },
    { label: '低吸线', value: fixedOrDash(item.buyBelow) },
    { label: '高抛线', value: fixedOrDash(item.sellAbove) },
  ]
}
</script>

<style scoped>
.muted { color: var(--text-3); font-size: 12px; }
.action-list { display: flex; flex-direction: column; gap: 12px; }
.action-card {
  border: 1px solid var(--line);
  border-left: 4px solid var(--brand);
  border-radius: var(--radius);
  padding: 14px;
  background: var(--surface);
}
.action-danger { border-left-color: var(--down); }
.action-warning { border-left-color: var(--warn); }
.action-success { border-left-color: var(--up); }
.action-top { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.action-top h4 { margin: 0; font-size: 16px; display: flex; align-items: baseline; gap: 8px; }
.name-link { color: var(--text); text-decoration: none; }
.action-top h4 span { color: var(--text-3); font-size: 12px; }
.action-top p { margin: 6px 0 0; color: var(--text-2); line-height: 1.6; font-size: 13px; }
.trade-ticket { margin: 12px 0; }
.strategy-strip {
  display: flex; justify-content: space-between; gap: 10px;
  padding: 9px 10px; border-radius: 6px;
  background: var(--brand-soft); color: var(--text-2);
  margin-bottom: 10px; font-size: 13px;
}
.strategy-strip b { color: var(--brand); }
.strategy-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.reason-list { margin: 0 0 10px 18px; padding: 0; color: var(--text-2); line-height: 1.7; font-size: 13px; }
.step-box {
  display: flex; flex-direction: column; gap: 4px;
  padding: 10px; border-radius: 8px;
  background: var(--surface-2); font-size: 13px; color: var(--text-2);
}
.step-box strong { color: var(--text); }
</style>
