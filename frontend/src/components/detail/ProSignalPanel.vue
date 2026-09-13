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
          <p class="sub">{{ data.horizon }} · Leading 指标体系(九维加权)</p>
        </div>
        <div class="head-price">
          <span class="hp-label">最新收盘价</span>
          <span class="price num">¥{{ data.price?.toFixed(2) }}</span>
        </div>
      </div>

      <!-- 决策链:现在多少钱 → 模型怎么看 → 预期到哪里 → 哪里买 → 哪里卖 → 何时失效 -->
      <div class="chain">
        <div class="chain-row head-row" :class="data.direction">
          <div class="chain-cell">
            <span class="cc-label">模型方向</span>
            <span class="cc-main">{{ data.label }}</span>
          </div>
          <div class="chain-cell">
            <span class="cc-label">方向评分(非概率)</span>
            <span class="cc-main num">{{ data.probabilityUp }} <small>/ 100 偏多强度</small></span>
          </div>
          <div class="chain-cell">
            <span class="cc-label">信号一致性(置信度)</span>
            <span class="cc-main num">{{ data.confidence }}<small>%</small></span>
          </div>
        </div>

        <div class="chain-row" v-if="data.forecast?.expected_target">
          <div class="chain-cell wide">
            <span class="cc-label">T+5 模型预期区间(基于 ATR 波动外推,非承诺价)</span>
            <span class="cc-main num">¥{{ data.forecast.expected_target[0] }} ~ ¥{{ data.forecast.expected_target[1] }}</span>
            <span class="cc-sub num" v-if="data.forecast.expected_change_pct">
              相对现价 {{ data.forecast.expected_change_pct[0] > 0 ? '+' : '' }}{{ data.forecast.expected_change_pct[0] }}% ~
              {{ data.forecast.expected_change_pct[1] > 0 ? '+' : '' }}{{ data.forecast.expected_change_pct[1] }}%
            </span>
          </div>
        </div>

        <div class="chain-row">
          <div class="chain-cell" v-if="data.forecast?.buy_ref">
            <span class="cc-label">买点参考区(回踩分批,不追高)</span>
            <span class="cc-main num buy">{{ fmtZone(data.forecast.buy_ref) }}</span>
            <span class="cc-sub">价值区下沿 ~ POC,跌破失效位停止</span>
          </div>
          <div class="chain-cell" v-if="data.forecast?.sell_ref">
            <span class="cc-label">卖点参考区(反弹分批止盈)</span>
            <span class="cc-main num sell">{{ fmtZone(data.forecast.sell_ref) }}</span>
            <span class="cc-sub">POC / 价值区上沿 / 20 日高附近</span>
          </div>
          <div class="chain-cell" v-if="data.forecast?.invalid_level">
            <span class="cc-label">失效位(收盘价有效越过即弃用本链路)</span>
            <span class="cc-main num invalid">¥{{ data.forecast.invalid_level }}</span>
            <span class="cc-sub">{{ data.forecast.invalidation }}</span>
          </div>
        </div>

        <div class="chain-row" v-if="data.forecast?.plan_line">
          <div class="chain-cell wide">
            <span class="cc-label">怎么用</span>
            <span class="cc-text">{{ data.forecast.plan_line }}</span>
          </div>
        </div>
      </div>

      <div class="dashboard">
        <div class="list-card">
          <h5>核心驱动信号(为什么是这个方向)</h5>
          <ul>
            <li v-for="(s, i) in data.keySignals" :key="i">{{ s }}</li>
          </ul>
        </div>

        <div class="list-card risks">
          <h5>风险提示</h5>
          <ul>
            <li v-for="(r, i) in data.risks" :key="i" class="risk-item">{{ r }}</li>
          </ul>
          <p class="score-note">方向评分由 9 个 leading 指标加权合成后映射到 0~100,
            表示指标组合的偏多强度,<b>不是历史命中率</b>;置信度 = 指标一致性 × 数据质量 × 信号强度。</p>
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
import { ref, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { getStockProSignal } from '@/api/stock'

// 只在显示时才请求（父组件用 v-if 控制），避免详情页每次都多打一个慢接口。
const props = defineProps<{ code: string }>()
const data = ref<any>(null)
const loading = ref(false)

function fmtZone(z: [number, number] | null): string {
  if (!z) return ''
  return z[0] === z[1] ? `¥${z[0]}` : `¥${z[0]} ~ ¥${z[1]}`
}

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
.head-price { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
.head-price .hp-label { font-size: 11px; color: var(--text-3); }
.head-price .price { font-size: 22px; font-weight: 700; color: var(--text); }

/* 决策链:每个模型输出都带「是什么/怎么用」说明 */
.chain { display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }
.chain-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.chain-row.head-row .chain-cell { background: var(--bg-2); }
.chain-cell {
  padding: 12px 14px; background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius); min-width: 0; display: flex; flex-direction: column; gap: 4px;
}
.chain-cell.wide { grid-column: 1 / -1; }
.cc-label { font-size: 11px; color: var(--text-3); line-height: 1.5; }
.cc-main { font-size: 19px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.cc-main small { font-size: 11px; color: var(--text-3); font-weight: 400; margin-left: 4px; }
.cc-main.buy { color: var(--up); }
.cc-main.sell { color: var(--down); }
.cc-main.invalid { color: var(--warn-text); }
.head-row .cc-main { font-size: 22px; }
.chain-row.head-row.up .cc-main { color: var(--up); }
.chain-row.head-row.down .cc-main { color: var(--down); }
.cc-sub { font-size: 11px; color: var(--text-3); line-height: 1.5; }
.cc-text { font-size: 13px; color: var(--text-2); line-height: 1.7; }
.score-note { margin: 10px 0 0; font-size: 11px; color: var(--text-3); line-height: 1.6; }
.score-note b { color: var(--warn-text); }

h5 { margin: 0 0 8px; font-size: 13px; color: var(--text-2); font-weight: 600; }
.dashboard { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.prob-card, .list-card { padding: 14px; background: var(--bg-2); border-radius: var(--radius); min-width: 0; }
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
  .chain-row { grid-template-columns: 1fr; }
  .head { flex-direction: column; align-items: flex-start; }
  .head-price { flex-direction: row; align-items: baseline; gap: 8px; }
}
@media (max-width: 600px) {
  .dim-grid { grid-template-columns: 1fr; }
}
</style>
