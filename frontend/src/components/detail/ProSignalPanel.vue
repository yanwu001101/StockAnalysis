<template>
  <div class="pro-signal-panel">
    <div v-if="loading" class="loading-state">
      <el-icon class="rotating"><Loading /></el-icon>
      <span>专业信号计算中...</span>
    </div>

    <template v-else-if="data">
      <div class="head">
        <div>
          <h4>{{ data.name }} <span class="code mono">{{ data.code }}</span></h4>
          <p class="sub">{{ data.horizon }} · 无滞后 Leading Indicators</p>
        </div>
        <span class="price num">¥{{ data.price?.toFixed(2) }}</span>
      </div>

      <div class="dashboard">
        <div class="prob-card" :class="data.direction">
          <h5>方向预测</h5>
          <div class="label">{{ data.label }}</div>
          <div class="prob-bar">
            <div class="bar-fill" :style="{ width: data.probabilityUp + '%' }"></div>
          </div>
          <div class="prob-numbers num">
            <span class="up">↑ {{ data.probabilityUp }}%</span>
            <span class="down">↓ {{ data.probabilityDown }}%</span>
          </div>
          <div class="confidence">
            <span class="meta">置信度 {{ data.confidence }}%</span>
            <el-progress :percentage="data.confidence" :stroke-width="6" :color="confColor" :show-text="false" />
          </div>
        </div>

        <div class="list-card">
          <h5>核心驱动信号</h5>
          <ul>
            <li v-for="(s, i) in data.keySignals" :key="i">{{ s }}</li>
          </ul>
        </div>

        <div class="list-card risks">
          <h5>风险提示</h5>
          <ul>
            <li v-for="(r, i) in data.risks" :key="i" class="risk-item">{{ r }}</li>
          </ul>
        </div>
      </div>

      <h5 class="dim-title">九维度 Leading 指标矩阵</h5>
      <div class="dim-grid">
        <div v-for="d in data.dimensions" :key="d.nameEn" class="dim-cell"
             :class="{ bull: d.score > 0.2, bear: d.score < -0.2 }">
          <div class="dim-head">
            <span class="dim-name">{{ d.name }}</span>
            <span class="dim-value num">{{ d.value }}</span>
          </div>
          <div class="dim-bar">
            <div class="bar-track">
              <div class="bar-mid"></div>
              <div class="bar-pointer" :style="{ left: ((d.score + 1) / 2 * 100) + '%' }"></div>
            </div>
          </div>
          <div class="dim-detail">{{ d.detail }}</div>
          <div class="dim-weight">权重 {{ (d.weight * 100).toFixed(0) }}%</div>
        </div>
      </div>

      <el-collapse class="info-fold">
        <el-collapse-item title="指标体系说明" name="info">
          <p class="info-p">本页采用 Leading 指标体系，与多策略评分（Lagging-friendly）形成互补：</p>
          <ul class="info-list">
            <li><b>Heikin-Ashi</b> 平滑趋势 — 颜色连续度反映趋势惯性</li>
            <li><b>DEMA / TEMA</b> — 低滞后双/三重指数均线，比 EMA 提前约 30%</li>
            <li><b>TSI</b> 真实力度指数 (Blau 1991) — 双平滑动量，0 轴穿越早于 MACD</li>
            <li><b>VWAP 偏离</b> — 价格相对成交量加权均价的位置，机构成本锚</li>
            <li><b>Volume Profile POC</b> — 拍卖理论核心价位，价格突破 VAH/VAL 视为方向确认</li>
            <li><b>CMF</b> Chaikin Money Flow — 收盘位置 × 成交量，资金流入流出</li>
            <li><b>盘口主动度</b> — 5 日成交量加权收盘相对位置</li>
            <li><b>短 EMA 交叉</b> — EMA5/10 即时金叉死叉 + 量能确认</li>
            <li><b>5 日宽度</b> — 短期涨跌家数与平均斜率</li>
          </ul>
        </el-collapse-item>
      </el-collapse>
    </template>

    <div v-else class="empty">未找到数据</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { getStockProSignal } from '@/api/stock'

// 只在显示时才请求（父组件用 v-if 控制），避免详情页每次都多打一个慢接口。
const props = defineProps<{ code: string }>()
const data = ref<any>(null)
const loading = ref(false)

const confColor = computed(() => {
  const c = data.value?.confidence || 0
  return c >= 60 ? 'var(--brand)' : c >= 40 ? 'var(--warn)' : 'var(--up)'
})

async function load() {
  if (!props.code) return
  loading.value = true
  try {
    data.value = await getStockProSignal(props.code)
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

watch(() => props.code, load, { immediate: true })
</script>

<style scoped>
.loading-state { display: flex; align-items: center; justify-content: center; gap: 12px; padding: 48px 0; color: var(--text-3); font-size: 14px; }
.rotating { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 14px; }
.head h4 { margin: 0; font-size: 16px; color: var(--text); }
.head .code { font-size: 13px; color: var(--text-3); font-weight: 400; margin-left: 6px; }
.head .sub { margin: 4px 0 0; font-size: 12px; color: var(--text-3); }
.head .price { font-size: 22px; font-weight: 700; color: var(--text); }

h5 { margin: 0 0 8px; font-size: 13px; color: var(--text-2); font-weight: 600; }
.dashboard { display: grid; grid-template-columns: 1.2fr 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.prob-card, .list-card { padding: 14px; background: var(--bg-2); border-radius: var(--radius); min-width: 0; }
.prob-card { text-align: center; }
.prob-card h5 { color: var(--text-3); }
.prob-card .label { font-size: 26px; font-weight: 800; padding: 6px 0; }
.prob-card.up .label { color: var(--up); }
.prob-card.down .label { color: var(--down); }
.prob-card.flat .label { color: var(--text-3); }
.prob-bar { height: 8px; background: var(--down-soft); border-radius: 4px; overflow: hidden; margin: 10px 0 6px; }
.bar-fill { height: 100%; background: var(--up); }
.prob-numbers { display: flex; justify-content: space-between; font-size: 14px; font-weight: 700; padding: 4px 0 10px; }
.prob-numbers .up { color: var(--up); }
.prob-numbers .down { color: var(--down); }
.confidence .meta { font-size: 12px; color: var(--text-3); display: block; margin-bottom: 4px; text-align: left; }
.list-card ul { margin: 0; padding-left: 18px; }
.list-card li { font-size: 13px; color: var(--text); padding: 3px 0; line-height: 1.5; }
.risks .risk-item { color: var(--warn-text); }

.dim-title { margin-top: 4px; }
.dim-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 14px; }
.dim-cell {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  min-width: 0;
}
.dim-cell.bull { border-color: var(--up); background: var(--up-soft); }
.dim-cell.bear { border-color: var(--down); background: var(--down-soft); }
.dim-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; gap: 6px; }
.dim-name { font-size: 13px; font-weight: 600; color: var(--text); }
.dim-value { font-size: 12px; color: var(--text-3); }
.dim-bar { padding: 4px 0 6px; }
.bar-track { position: relative; height: 4px; background: var(--line); border-radius: 2px; }
.bar-mid { position: absolute; left: 50%; top: -2px; width: 1px; height: 8px; background: var(--text-4); }
.bar-pointer {
  position: absolute; top: -3px; width: 10px; height: 10px;
  background: var(--text-2); border-radius: 50%;
  transform: translateX(-50%); transition: left 0.3s;
}
.dim-cell.bull .bar-pointer { background: var(--up); }
.dim-cell.bear .bar-pointer { background: var(--down); }
.dim-detail { font-size: 11px; color: var(--text-3); line-height: 1.5; margin-top: 4px; }
.dim-weight { font-size: 10px; color: var(--text-4); margin-top: 4px; }

.info-fold { border: 0; }
.info-fold :deep(.el-collapse-item__header) { font-size: 13px; color: var(--text-3); background: transparent; border-color: var(--line); }
.info-fold :deep(.el-collapse-item__wrap) { background: transparent; border: 0; }
.info-p { font-size: 13px; color: var(--text); margin: 8px 0; }
.info-list { margin: 0; padding-left: 18px; }
.info-list li { font-size: 12px; color: var(--text-3); padding: 2px 0; line-height: 1.6; }
.info-list b { color: var(--text); font-weight: 600; }
.empty { padding: 40px; text-align: center; color: var(--text-3); }

@media (max-width: 900px) {
  .dashboard { grid-template-columns: 1fr; }
  .dim-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 600px) {
  .dim-grid { grid-template-columns: 1fr; }
}
</style>
