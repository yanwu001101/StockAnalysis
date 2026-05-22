<template>
  <div class="page-container pro-signal-page">
    <div v-if="loading" class="loading-state">
      <el-icon class="rotating"><Loading /></el-icon>
      <span>专业信号计算中...</span>
    </div>

    <template v-else-if="data">
      <div class="header glass-card">
        <div class="header-left">
          <el-button link size="small" @click="$router.back()">
            <el-icon><ArrowLeft /></el-icon>返回
          </el-button>
          <div class="title">
            <h2>{{ data.name }} <span class="code">{{ data.code }}</span></h2>
            <p class="sub">{{ data.horizon }} · 无滞后 Leading Indicators</p>
          </div>
        </div>
        <div class="price-box">
          <span class="price">¥{{ data.price?.toFixed(2) }}</span>
        </div>
      </div>

      <div class="dashboard">
        <div class="prob-card glass-card" :class="data.direction">
          <h3>方向预测</h3>
          <div class="label">{{ data.label }}</div>
          <div class="prob-bar">
            <div class="bar-fill up" :style="{ width: data.probabilityUp + '%' }"></div>
          </div>
          <div class="prob-numbers">
            <span class="up">↑ {{ data.probabilityUp }}%</span>
            <span class="down">↓ {{ data.probabilityDown }}%</span>
          </div>
          <div class="confidence">
            <span class="meta">置信度</span>
            <el-progress :percentage="data.confidence" :stroke-width="6" :color="confColor" />
          </div>
        </div>

        <div class="key-signals glass-card">
          <h3>核心驱动信号</h3>
          <ul>
            <li v-for="(s, i) in data.keySignals" :key="i">{{ s }}</li>
          </ul>
        </div>

        <div class="risks glass-card">
          <h3>风险提示</h3>
          <ul>
            <li v-for="(r, i) in data.risks" :key="i" class="risk-item">{{ r }}</li>
          </ul>
        </div>
      </div>

      <div class="dimensions-card glass-card">
        <h3>九维度 Leading 指标矩阵</h3>
        <div class="dim-grid">
          <div v-for="d in data.dimensions" :key="d.nameEn" class="dim-cell"
               :class="{ bull: d.score > 0.2, bear: d.score < -0.2, neutral: Math.abs(d.score) <= 0.2 }">
            <div class="dim-head">
              <span class="dim-name">{{ d.name }}</span>
              <span class="dim-value">{{ d.value }}</span>
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
      </div>

      <div class="info glass-card">
        <h3>说明</h3>
        <p>本页采用 Leading 指标体系，与个股详情页的 Lagging-friendly 多策略评分形成互补：</p>
        <ul>
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
      </div>
    </template>

    <div v-else class="empty">未找到数据</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Loading } from '@element-plus/icons-vue'
import { getStockProSignal } from '@/api/stock'

const route = useRoute()
const data = ref<any>(null)
const loading = ref(false)

const confColor = computed(() => {
  const c = data.value?.confidence || 0
  return c >= 60 ? '#10B981' : c >= 40 ? '#F59E0B' : '#EF4444'
})

async function load() {
  const code = route.params.code as string
  if (!code) return
  loading.value = true
  try {
    data.value = await getStockProSignal(code)
  } catch (e) {
    data.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => route.params.code, load)
</script>

<style scoped>
.pro-signal-page { padding-bottom: 24px; }
.loading-state {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  padding: 80px 0; color: var(--text-muted); font-size: 14px;
}
.rotating { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }

.header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; margin-bottom: 16px; }
.header-left { display: flex; align-items: center; gap: 16px; }
.title h2 { margin: 0; font-size: 18px; color: var(--text-primary); }
.title .code { font-size: 13px; color: var(--text-muted); font-weight: 400; margin-left: 8px; }
.title .sub { margin: 4px 0 0; font-size: 12px; color: var(--text-muted); }
.price-box .price { font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text-primary); }

.dashboard { display: grid; grid-template-columns: 1.2fr 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.prob-card { padding: 16px; text-align: center; }
.prob-card h3 { margin: 0 0 10px; font-size: 14px; color: var(--text-muted); font-weight: 600; }
.prob-card .label { font-size: 28px; font-weight: 800; padding: 8px 0; }
.prob-card.up .label { color: #FF4757; }
.prob-card.down .label { color: #2AE8A4; }
.prob-card.flat .label { color: var(--text-muted); }
.prob-bar { height: 8px; background: rgba(42,232,164,0.15); border-radius: 4px; overflow: hidden; margin: 10px 0 6px; }
.bar-fill.up { height: 100%; background: linear-gradient(90deg, #FF4757, #FF6B81); }
.prob-numbers { display: flex; justify-content: space-between; font-size: 14px; font-weight: 700; padding: 4px 0 10px; }
.prob-numbers .up { color: #FF4757; }
.prob-numbers .down { color: #2AE8A4; }
.confidence { margin-top: 8px; }
.confidence .meta { font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px; }

.key-signals, .risks { padding: 16px; }
.key-signals h3, .risks h3, .dimensions-card h3, .info h3 { margin: 0 0 10px; font-size: 14px; color: var(--text-primary); }
.key-signals ul, .risks ul { margin: 0; padding-left: 18px; }
.key-signals li { font-size: 13px; color: var(--text); padding: 3px 0; line-height: 1.5; }
.risks .risk-item { font-size: 13px; color: var(--warn, #FFC312); padding: 3px 0; }

.dimensions-card { padding: 16px; margin-bottom: 16px; }
.dim-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.dim-cell {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg-2);
  transition: all 0.2s;
}
.dim-cell.bull { border-color: rgba(255,71,87,0.4); background: rgba(255,71,87,0.05); }
.dim-cell.bear { border-color: rgba(42,232,164,0.4); background: rgba(42,232,164,0.05); }
.dim-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.dim-name { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.dim-value { font-size: 12px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.dim-bar { padding: 4px 0 6px; }
.bar-track { position: relative; height: 4px; background: var(--line); border-radius: 2px; }
.bar-mid { position: absolute; left: 50%; top: -2px; width: 1px; height: 8px; background: var(--text-muted); }
.bar-pointer {
  position: absolute; top: -3px; width: 10px; height: 10px;
  background: var(--text-primary); border-radius: 50%;
  transform: translateX(-50%); transition: left 0.3s;
}
.dim-cell.bull .bar-pointer { background: #FF4757; }
.dim-cell.bear .bar-pointer { background: #2AE8A4; }
.dim-detail { font-size: 11px; color: var(--text-3); line-height: 1.5; margin-top: 4px; }
.dim-weight { font-size: 10px; color: var(--text-muted); margin-top: 4px; }

.info { padding: 16px; }
.info p { font-size: 13px; color: var(--text); margin: 0 0 8px; }
.info ul { margin: 0; padding-left: 18px; }
.info li { font-size: 12px; color: var(--text-muted); padding: 2px 0; line-height: 1.6; }
.info b { color: var(--text-primary); font-weight: 600; }
.empty { padding: 60px; text-align: center; color: var(--text-muted); }

@media (max-width: 900px) {
  .dashboard { grid-template-columns: 1fr; }
  .dim-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 600px) {
  .dim-grid { grid-template-columns: 1fr; }
}
</style>
