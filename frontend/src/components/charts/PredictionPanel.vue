<template>
  <div class="prediction-panel">
    <div class="panel-header">
      <h4>涨跌概率分析</h4>
      <el-tag size="small" type="info">{{ prediction.timeHorizon }}</el-tag>
    </div>

    <!-- Probability display -->
    <div class="prob-section">
      <div class="prob-bar">
        <div class="prob-fill prob-up" :style="{ width: prediction.probabilityUp + '%' }">
          <span v-if="prediction.probabilityUp > 15">{{ prediction.probabilityUp }}%</span>
        </div>
        <div class="prob-fill prob-down" :style="{ width: prediction.probabilityDown + '%' }">
          <span v-if="prediction.probabilityDown > 15">{{ prediction.probabilityDown }}%</span>
        </div>
      </div>
      <div class="prob-labels">
        <span class="prob-label-up"><el-icon><Top /></el-icon> 上涨</span>
        <span class="prob-label-down">下跌 <el-icon><Bottom /></el-icon></span>
      </div>

      <div class="signal-badge-row">
        <div class="signal-badge" :class="'signal-' + prediction.signal">{{ prediction.signalLabel }}</div>
        <div class="confidence-badge">
          <span class="conf-label">置信度</span>
          <span class="conf-value num">{{ prediction.confidence }}%</span>
        </div>
      </div>
    </div>

    <!-- Dimension breakdown -->
    <div class="dimensions-section">
      <h5>信号维度分解</h5>
      <div class="dim-list">
        <div class="dim-item" v-for="dim in prediction.dimensions" :key="dim.nameEn">
          <div class="dim-header">
            <span class="dim-name">{{ dim.name }}</span>
            <span class="dim-detail">{{ dim.detail }}</span>
          </div>
          <div class="dim-bar-wrap">
            <div class="dim-bar-center"></div>
            <div
              class="dim-bar-fill"
              :class="dim.score >= 0 ? 'dim-positive' : 'dim-negative'"
              :style="{ width: Math.abs(dim.score) * 50 + '%',
                         left: dim.score >= 0 ? '50%' : (50 - Math.abs(dim.score) * 50) + '%' }"
            ></div>
            <div class="dim-score-label num" :style="{ left: (dim.score + 1) * 50 + '%' }">
              {{ dim.score > 0 ? '+' : '' }}{{ (dim.score * 100).toFixed(0) }}
            </div>
          </div>
          <div class="dim-sub-signals" v-if="Object.keys(dim.subSignals).length">
            <span class="sub-tag" v-for="(v, k) in dim.subSignals" :key="k">{{ v }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Key drivers -->
    <div class="insights-section">
      <div class="insight-block drivers">
        <h5><el-icon><TrendCharts /></el-icon> 核心驱动</h5>
        <ul>
          <li v-for="(d, i) in prediction.keyDrivers" :key="i">{{ d }}</li>
        </ul>
      </div>
      <div class="insight-block warnings">
        <h5><el-icon><WarningFilled /></el-icon> 风险提示</h5>
        <ul>
          <li v-for="(w, i) in prediction.riskWarnings" :key="i">{{ w }}</li>
        </ul>
      </div>
    </div>

    <div class="disclaimer">* 基于多维度量化模型，仅供参考，不构成投资建议</div>
  </div>
</template>

<script setup lang="ts">
import { Top, Bottom, TrendCharts, WarningFilled } from '@element-plus/icons-vue'
import type { PredictionResult } from '@/types'

defineProps<{ prediction: PredictionResult }>()
</script>

<style scoped>
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.panel-header h4 { margin: 0; font-size: 14px; color: var(--text); }
h5 { margin: 0 0 8px; font-size: 13px; color: var(--text-2); font-weight: 600; display: flex; align-items: center; gap: 4px; }

.prob-section { margin-bottom: 18px; }
.prob-bar {
  display: flex;
  height: 32px;
  border-radius: 16px;
  overflow: hidden;
  background: var(--bg-2);
}
.prob-fill {
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; color: var(--surface);
  transition: width 0.8s ease;
  min-width: 0;
}
.prob-fill span { white-space: nowrap; }
.prob-up { background: var(--up); }
.prob-down { background: var(--down); }
.prob-labels { display: flex; justify-content: space-between; margin-top: 6px; font-size: 12px; }
.prob-label-up { color: var(--up); display: flex; align-items: center; gap: 2px; }
.prob-label-down { color: var(--down); display: flex; align-items: center; gap: 2px; }

.signal-badge-row { display: flex; align-items: center; gap: 16px; justify-content: center; margin-top: 12px; }
.signal-badge { font-size: 18px; font-weight: 700; padding: 5px 22px; border-radius: 20px; }
.signal-bullish { background: var(--up-soft); color: var(--up); }
.signal-bearish { background: var(--down-soft); color: var(--down); }
.signal-neutral { background: var(--warn-soft); color: var(--warn-text); }
.confidence-badge { display: flex; flex-direction: column; align-items: center; }
.conf-label { font-size: 11px; color: var(--text-3); }
.conf-value { font-size: 16px; font-weight: 600; color: var(--text); }

.dimensions-section { margin-bottom: 16px; }
.dim-list { display: flex; flex-direction: column; gap: 14px; }
.dim-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; gap: 8px; }
.dim-name { font-size: 13px; font-weight: 600; color: var(--text); min-width: 64px; }
.dim-detail { font-size: 12px; color: var(--text-3); flex: 1; text-align: right; }
.dim-bar-wrap { position: relative; height: 8px; background: var(--bg-2); border-radius: 4px; }
.dim-bar-center { position: absolute; left: 50%; top: 0; width: 1px; height: 100%; background: var(--line-strong); }
.dim-bar-fill { position: absolute; top: 0; height: 100%; border-radius: 4px; transition: width 0.6s ease, left 0.6s ease; }
.dim-positive { background: var(--up); }
.dim-negative { background: var(--down); }
.dim-score-label {
  position: absolute; top: -16px;
  transform: translateX(-50%);
  font-size: 11px; font-weight: 600;
  color: var(--text-2);
}
.dim-sub-signals { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.sub-tag { font-size: 11px; color: var(--text-3); background: var(--bg-2); padding: 1px 6px; border-radius: 3px; }

.insights-section { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 12px; }
.insight-block ul { margin: 0; padding-left: 16px; list-style: disc; }
.insight-block li { font-size: 12px; line-height: 1.8; color: var(--text-2); }
.drivers h5 { color: var(--brand); }
.warnings h5 { color: var(--warn-text); }

.disclaimer { font-size: 11px; color: var(--text-4); text-align: center; }

@media (max-width: 768px) {
  .insights-section { grid-template-columns: 1fr; }
  .dim-detail { display: none; }
}
</style>
