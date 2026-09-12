<template>
  <div class="strategy-scores" :class="{ mobile: isMobile }">
    <!-- 22+ 个策略的雷达图在手机上标签全部重叠，手机只保留排序后的评分列表 -->
    <AppCard v-if="!isMobile && sorted.length" title="策略评分雷达" compact>
      <RadarChart :indicators="radarIndicators" :values="radarValues" :height="400" />
    </AppCard>

    <AppCard v-if="sorted.length" title="多策略评分详情" sub="按得分从高到低">
      <div class="strategy-grid">
        <div class="strategy-item" v-for="it in visible" :key="it.id">
          <div class="strategy-head">
            <span class="strategy-name">{{ it.name }}</span>
            <ScorePill :score="it.score" size="sm" />
          </div>
          <el-progress :percentage="Math.min(100, Math.max(0, it.score))" :color="colorOf(it.score)" :show-text="false" :stroke-width="6" />
        </div>
      </div>
      <el-button
        v-if="sorted.length > COLLAPSED_COUNT"
        link
        size="small"
        class="toggle-all"
        @click="expandedAll = !expandedAll"
      >
        {{ expandedAll ? '收起' : `展开全部 ${sorted.length} 项` }}
        <el-icon><component :is="expandedAll ? 'ArrowUp' : 'ArrowDown'" /></el-icon>
      </el-button>
    </AppCard>

    <AppCard v-else title="多策略评分详情">
      <EmptyState
        variant="empty"
        title="暂无策略评分"
        description="该股票的策略评分数据尚未生成，可稍后刷新重试"
      />
    </AppCard>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useStrategyStore } from '@/stores/strategy'
import { useDevice } from '@/composables/useDevice'
import { scoreLevel } from '@/utils/score'
import AppCard from '@/components/ui/AppCard.vue'
import ScorePill from '@/components/stock/ScorePill.vue'
import RadarChart from '@/components/charts/RadarChart.vue'
import EmptyState from '@/components/ui/EmptyState.vue'

const props = defineProps<{ scores: Record<string, number> }>()
const strategyStore = useStrategyStore()
const { isMobile } = useDevice()

// 收起时只展示得分最高的几项，避免 29 个策略项把概览页拉成一长条
const COLLAPSED_COUNT = 6
const expandedAll = ref(false)

const radarIndicators = computed(() => strategyStore.strategies.map(s => ({ name: s.name, max: 100 })))
const radarValues = computed(() => strategyStore.strategies.map(s => props.scores[s.id] || 0))

const sorted = computed(() =>
  Object.entries(props.scores)
    .map(([id, score]) => ({ id, name: nameOf(id), score: Number(score) || 0 }))
    .sort((a, b) => b.score - a.score)
)
const visible = computed(() =>
  expandedAll.value ? sorted.value : sorted.value.slice(0, COLLAPSED_COUNT)
)

function nameOf(id: string) {
  return strategyStore.strategies.find(s => s.id === id)?.name || id
}
function colorOf(score: number) {
  const lv = scoreLevel(score)
  return lv === 'high' ? 'var(--brand)' : lv === 'mid' ? 'var(--warn)' : 'var(--up)'
}
</script>

<style scoped>
.strategy-scores { display: flex; flex-direction: column; gap: 16px; }
.strategy-scores.mobile { gap: 12px; }
.strategy-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.strategy-item { padding: 10px 12px; background: var(--bg-2); border-radius: var(--radius); min-width: 0; }
.strategy-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px; }
.strategy-name { font-size: 13px; color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.toggle-all { margin-top: 10px; }
@media (max-width: 768px) {
  .strategy-grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px; }
}
</style>
