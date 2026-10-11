<template>
  <AppCard class="stock-header" :class="{ mobile: isMobile }">
    <div class="sh-row">
      <div class="sh-left">
        <template v-if="loading">
          <div class="skeleton-bar" style="width: 200px; height: 20px;"></div>
          <div class="skeleton-bar" style="width: 260px; height: 28px; margin-top: 10px;"></div>
        </template>
        <template v-else>
          <div class="sh-title">
            <span class="sh-name">{{ info.name || '—' }}</span>
            <span class="sh-code mono">{{ info.code || code }}</span>
            <el-tag v-if="info.industry" size="small" type="info">{{ info.industry }}</el-tag>
          </div>
          <div class="sh-price-row">
            <ChangeText :value="info.price" :by="info.changePercent ?? info.change" mode="price" class="sh-price" />
            <span class="sh-change">
              <ChangeText v-if="info.change != null" :value="info.change" mode="number" :digits="2" />
              <ChangeText :value="info.changePercent" class="sh-pct" />
            </span>
          </div>
        </template>
      </div>
      <div class="sh-right">
        <!-- 加载中显示骨架圈：0 分与「未加载」语义不同（SKILL §12），不得用假 0 占位 -->
        <div v-if="loading" class="gauge-skeleton" :style="{ width: (isMobile ? 64 : 84) + 'px', height: (isMobile ? 64 : 84) + 'px' }" />
        <ScoreGauge v-else :score="score" :size="isMobile ? 64 : 84" />
        <div class="sh-actions">
          <el-button type="success" size="small" @click="$emit('predict')">
            <el-icon><Aim /></el-icon><span v-if="!isMobile">专业预测</span>
          </el-button>
          <WatchlistButton :code="code" size="small" :icon-only="isMobile" />
          <el-button v-if="!isMobile" size="small" @click="$router.back()">返回</el-button>
        </div>
      </div>
    </div>
  </AppCard>
</template>

<script setup lang="ts">
import { Aim } from '@element-plus/icons-vue'
import { useDevice } from '@/composables/useDevice'
import AppCard from '@/components/ui/AppCard.vue'
import ChangeText from '@/components/stock/ChangeText.vue'
import WatchlistButton from '@/components/stock/WatchlistButton.vue'
import ScoreGauge from '@/components/charts/ScoreGauge.vue'

defineProps<{ info: any; code: string; score: number; loading?: boolean }>()
defineEmits<{ (e: 'predict'): void }>()
const { isMobile } = useDevice()
</script>

<style scoped>
.gauge-skeleton { border-radius: 50%; background: linear-gradient(100deg, var(--bg-2) 40%, var(--surface) 50%, var(--bg-2) 60%); background-size: 200% 100%; animation: sh-gauge 1.4s ease infinite; flex-shrink: 0; }
@keyframes sh-gauge { to { background-position: -200% 0; } }
.sh-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.sh-left { min-width: 0; }
.sh-title { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sh-name { font-size: 20px; font-weight: 600; color: var(--text); }
.sh-code { font-size: 14px; color: var(--text-3); }
.sh-price-row { display: flex; align-items: baseline; gap: 12px; margin-top: 6px; }
.sh-price { font-size: 28px; font-weight: 700; }
.sh-change { display: inline-flex; gap: 8px; font-size: 15px; }
.sh-right { display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
.sh-actions { display: flex; flex-direction: column; gap: 8px; }
.sh-actions :deep(.el-button + .el-button) { margin-left: 0; }
.stock-header.mobile .sh-name { font-size: 18px; }
.stock-header.mobile .sh-price { font-size: 24px; }
.stock-header.mobile .sh-change { font-size: 13px; }
.stock-header.mobile .sh-right { gap: 10px; }
.stock-header.mobile .sh-actions { flex-direction: row; }
</style>
