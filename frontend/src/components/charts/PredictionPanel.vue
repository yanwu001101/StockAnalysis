<template>
  <div class="prediction-panel glass-card">
    <div class="panel-header">
      <h3>涨跌概率分析</h3>
      <el-tag size="small" type="info">{{ prediction.timeHorizon }}</el-tag>
    </div>

    <!-- Probability display -->
    <div class="prob-section">
      <div class="prob-bar-container">
        <div class="prob-bar">
          <div class="prob-fill prob-up" :style="{ width: prediction.probabilityUp + '%' }">
            <span v-if="prediction.probabilityUp > 15">{{ prediction.probabilityUp }}%</span>
          </div>
          <div class="prob-fill prob-down" :style="{ width: prediction.probabilityDown + '%' }">
            <span v-if="prediction.probabilityDown > 15">{{ prediction.probabilityDown }}%</span>
          </div>
        </div>
        <div class="prob-labels">
          <span class="prob-label-up">
            <el-icon><Top /></el-icon> 上涨
          </span>
          <span class="prob-label-down">
            下跌 <el-icon><Bottom /></el-icon>
          </span>
        </div>
      </div>

      <div class="signal-badge-row">
        <div class="signal-badge" :class="'signal-' + prediction.signal">
          {{ prediction.signalLabel }}
        </div>
        <div class="confidence-badge">
          <span class="conf-label">置信度</span>
          <span class="conf-value">{{ prediction.confidence }}%</span>
        </div>
      </div>
    </div>

    <!-- Dimension breakdown -->
    <div class="dimensions-section">
      <h4>信号维度分解</h4>
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
            <div class="dim-score-label" :style="{ left: (dim.score + 1) * 50 + '%' }">
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
        <h4>
          <el-icon><TrendCharts /></el-icon> 核心驱动
        </h4>
        <ul>
          <li v-for="(d, i) in prediction.keyDrivers" :key="i">{{ d }}</li>
        </ul>
      </div>
      <div class="insight-block warnings">
        <h4>
          <el-icon><WarningFilled /></el-icon> 风险提示
        </h4>
        <ul>
          <li v-for="(w, i) in prediction.riskWarnings" :key="i">{{ w }}</li>
        </ul>
      </div>
    </div>

    <div class="disclaimer">
      * 基于多维度量化模型，仅供参考，不构成投资建议
    </div>
  </div>
</template>

<script setup lang="ts">
import { Top, Bottom, TrendCharts, WarningFilled } from '@element-plus/icons-vue'
import type { PredictionResult } from '@/types'

defineProps<{
  prediction: PredictionResult
}>()
</script>

<style scoped>
.prediction-panel {
  padding: 20px;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
}
.panel-header h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary);
}

/* Probability bar */
.prob-section {
  margin-bottom: 20px;
}
.prob-bar-container {
  margin-bottom: 12px;
}
.prob-bar {
  display: flex;
  height: 36px;
  border-radius: 18px;
  overflow: hidden;
  background: rgba(255, 71, 87, 0.1);
}
.prob-fill {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  transition: width 0.8s ease;
  min-width: 0;
}
.prob-fill span {
  white-space: nowrap;
}
.prob-up {
  background: linear-gradient(90deg, #2AE8A4, #00D4FF);
  color: #fff;
  border-radius: 18px 0 0 18px;
}
.prob-down {
  background: linear-gradient(90deg, #FF6B81, #FF4757);
  color: #fff;
  border-radius: 0 18px 18px 0;
}
.prob-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 12px;
}
.prob-label-up {
  color: #2AE8A4;
  display: flex;
  align-items: center;
  gap: 2px;
}
.prob-label-down {
  color: #FF4757;
  display: flex;
  align-items: center;
  gap: 2px;
}

/* Signal badge */
.signal-badge-row {
  display: flex;
  align-items: center;
  gap: 16px;
  justify-content: center;
}
.signal-badge {
  font-size: 20px;
  font-weight: 700;
  padding: 6px 24px;
  border-radius: 20px;
}
.signal-bullish {
  background: rgba(42, 232, 164, 0.15);
  color: #2AE8A4;
}
.signal-bearish {
  background: rgba(255, 71, 87, 0.15);
  color: #FF4757;
}
.signal-neutral {
  background: rgba(255, 195, 18, 0.15);
  color: #FFC312;
}
.confidence-badge {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.conf-label {
  font-size: 11px;
  color: var(--text-muted);
}
.conf-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

/* Dimensions */
.dimensions-section {
  margin-bottom: 18px;
}
.dimensions-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: var(--text-secondary);
}
.dim-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.dim-item {
  position: relative;
}
.dim-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 4px;
}
.dim-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  min-width: 64px;
}
.dim-detail {
  font-size: 12px;
  color: var(--text-muted);
  flex: 1;
  text-align: right;
  margin-left: 8px;
}
.dim-bar-wrap {
  position: relative;
  height: 8px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 4px;
  overflow: visible;
}
.dim-bar-center {
  position: absolute;
  left: 50%;
  top: 0;
  width: 1px;
  height: 100%;
  background: rgba(255, 255, 255, 0.15);
}
.dim-bar-fill {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s ease, left 0.6s ease;
}
.dim-positive {
  background: linear-gradient(90deg, rgba(42, 232, 164, 0.5), #2AE8A4);
}
.dim-negative {
  background: linear-gradient(90deg, #FF4757, rgba(255, 71, 87, 0.5));
}
.dim-score-label {
  position: absolute;
  top: -16px;
  transform: translateX(-50%);
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}
.dim-sub-signals {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.sub-tag {
  font-size: 11px;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.04);
  padding: 1px 6px;
  border-radius: 3px;
}

/* Insights */
.insights-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
}
.insight-block h4 {
  margin: 0 0 8px 0;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.insight-block ul {
  margin: 0;
  padding-left: 16px;
  list-style: disc;
}
.insight-block li {
  font-size: 12px;
  line-height: 1.8;
  color: var(--text-secondary);
}
.drivers h4 { color: #2AE8A4; }
.warnings h4 { color: #FFC312; }

.disclaimer {
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
  opacity: 0.6;
}

@media (max-width: 768px) {
  .insights-section { grid-template-columns: 1fr; }
}
</style>
