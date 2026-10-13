<template>
  <div class="prediction-panel">
    <div class="panel-header">
      <h4>{{ presentation.title }}</h4>
      <el-tag size="small" type="info">{{ prediction.timeHorizon }}</el-tag>
    </div>

    <!-- Probability display -->
    <div class="prob-section">
      <div class="cal-line" :class="presentation.calibrated ? 'cal-ok' : 'cal-warn'" role="status">
        {{ presentation.calibrationMessage }}
        <div v-if="prediction.calibration">
          相似信号 n={{ presentation.sampleText }}
          <template v-if="presentation.calibrated"> · T+5 上涨频率 {{ presentation.upText }} · 平均收益 {{ presentation.averageReturn }}</template>
          <span class="cal-date">（校准截至 {{ prediction.calibration.cal_date || '—' }} · 回放股票数 {{ prediction.calibration.universe ?? '—' }}）</span>
        </div>
      </div>
      <template v-if="presentation.calibrated">
        <div class="prob-bar" :aria-label="`历史 T+5 上涨频率 ${presentation.upText}`">
          <div class="prob-fill prob-up" :style="{ width: presentation.up + '%' }">
            <span>{{ presentation.upText }}</span>
          </div>
        </div>
        <div class="prob-labels">
          <span class="prob-label-up"><el-icon><Top /></el-icon> 历史上涨</span>
          <span>其余样本含持平，不等同于下跌</span>
        </div>
      </template>
      <div v-else class="trend-score">
        <span>偏多趋势评分</span><strong class="num">{{ presentation.scoreText }}</strong>
        <span class="score-note">高分表示模型偏多强度，不代表上涨概率</span>
      </div>
      <div class="signal-badge-row">
        <div class="signal-badge" :class="'signal-' + presentation.signal">{{ presentation.signalLabel }}</div>
        <div class="confidence-badge">
          <span class="conf-label">模型证据评分</span>
          <span class="conf-value num">{{ presentation.confidenceText }}</span>
        </div>
      </div>
      <p class="score-note">证据评分由信号一致性、数据完整度和信号强度组成，不是统计置信区间；指标之间可能相关，不能视为独立证据。</p>
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
import { computed } from 'vue'
import { Top, TrendCharts, WarningFilled } from '@element-plus/icons-vue'
import type { PredictionResult } from '@/types'
import { predictionPresentation } from '@/utils/predictionResult'

// Skill §4：只有经过历史校准的概率才能称为概率
const props = defineProps<{ prediction: PredictionResult }>()
const presentation = computed(() => predictionPresentation(props.prediction))
</script>

<style scoped>
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.panel-header h4 { margin: 0; font-size: 14px; color: var(--text); }
h5 { margin: 0 0 8px; font-size: 13px; color: var(--text-2); font-weight: 600; display: flex; align-items: center; gap: 4px; }

.prob-section { margin-bottom: 18px; }
.cal-line { font-size: 11px; padding: 5px 10px; border-radius: var(--radius-sm);
  margin-bottom: 10px; line-height: 1.5; }
.cal-line.cal-ok { background: var(--color-green-soft); color: var(--color-green); }
.cal-line.cal-warn { background: var(--warn-soft); color: var(--warn-text); }
.cal-date { opacity: 0.75; }
.trend-score { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; font-size: 13px; }
.trend-score strong { font-size: 20px; }
.score-note { color: var(--text-3); font-size: 11px; line-height: 1.6; }
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
