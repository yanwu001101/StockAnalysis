/**
 * DayInspector — K 线点击联动面板。
 *
 * 纯展示：输入是 dayContext 选择器的输出。当天有交易信号时展示信号与理由；
 * 没有信号时明确说明"当日无信号"，并展示当日 OHLC。AI 快照（辩论/舆情）
 * 是当前分析的结论快照，不是当日生成——文案上如实标注。
 */
<script setup lang="ts">
import type { DayContext } from '@/utils/selectors'
import type { DebateDTO, QuantVerdictPayload } from '@/types/quant'

defineProps<{
  context: DayContext | null
  verdict: QuantVerdictPayload | null
}>()

function formatPct(value: number): string {
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
}

function debateFor(debate: readonly DebateDTO[], side: DebateDTO['side']): DebateDTO[] {
  return debate.filter((entry) => entry.side === side)
}
</script>

<template>
  <div class="day-inspector">
    <template v-if="context">
      <div class="day-head">
        <span class="day-date num">{{ context.date }}</span>
        <span v-if="context.marker" class="day-signal" :class="context.marker.action === 'BUY' ? 'up' : 'down'">
          {{ context.marker.action === 'BUY' ? '买入信号' : '卖出信号' }}
        </span>
        <span v-else class="day-signal flat">无交易信号</span>
      </div>
      <dl class="ohlc">
        <div><dt>开盘</dt><dd class="num">{{ context.open.toFixed(2) }}</dd></div>
        <div><dt>收盘</dt><dd class="num">{{ context.close.toFixed(2) }}</dd></div>
        <div><dt>最高</dt><dd class="num up">{{ context.high.toFixed(2) }}</dd></div>
        <div><dt>最低</dt><dd class="num down">{{ context.low.toFixed(2) }}</dd></div>
        <div>
          <dt>涨跌</dt>
          <dd class="num" :class="context.changePct > 0 ? 'up' : context.changePct < 0 ? 'down' : 'flat'">
            {{ formatPct(context.changePct) }}
          </dd>
        </div>
      </dl>
      <p v-if="context.marker" class="marker-reason">
        <span class="marker-tag">信号理由</span>{{ context.marker.reason }}
      </p>
      <p v-else class="marker-reason muted">当日策略未触发交易（信号基于截至前一日收盘的信息）</p>
    </template>
    <p v-else class="day-empty">点击 K 线图上的任意一天，这里会显示当日的行情与信号。</p>

    <div v-if="verdict" class="ai-snapshot">
      <h4>AI 分析快照<span class="snapshot-note">（本次分析的总结论，非当日生成）</span></h4>
      <div class="snapshot-debate">
        <div class="side bull">
          <span class="side-tag">多方</span>
          <ul>
            <li v-for="(entry, index) in debateFor(verdict.debate, 'BULL')" :key="index">
              {{ entry.argument }}
            </li>
          </ul>
        </div>
        <div class="side bear">
          <span class="side-tag">空方</span>
          <ul>
            <li v-for="(entry, index) in debateFor(verdict.debate, 'BEAR')" :key="index">
              {{ entry.argument }}
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.day-inspector {
  display: grid;
  gap: var(--space-3);
}

.day-head {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}

.day-date {
  font-size: 16px;
  font-weight: 700;
}

.day-signal {
  font-size: 12px;
  border: 1px solid currentColor;
  border-radius: 999px;
  padding: 0 8px;
}

.ohlc {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(88px, 1fr));
  gap: var(--space-2);
}

.ohlc div {
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-2);
}

.ohlc dt {
  font-size: 10px;
  color: var(--text-muted);
}

.ohlc dd {
  margin: 0;
  font-size: 14px;
}

.marker-reason {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.marker-reason.muted {
  color: var(--text-muted);
}

.marker-tag {
  display: inline-block;
  font-size: 10px;
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 3px;
  padding: 0 4px;
  margin-right: var(--space-2);
}

.ai-snapshot h4 {
  margin: 0 0 var(--space-2);
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.snapshot-note {
  font-size: 10px;
  color: var(--text-muted);
  margin-left: var(--space-2);
  font-weight: 400;
}

.snapshot-debate {
  display: grid;
  gap: var(--space-2);
}

.side {
  border-left: 2px solid var(--border-strong);
  padding-left: var(--space-2);
}

.side.bull {
  border-color: var(--color-up);
}

.side.bear {
  border-color: var(--color-down);
}

.side-tag {
  font-size: 10px;
  color: var(--text-muted);
}

.side ul {
  margin: var(--space-1) 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 2px;
}

.side li {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.day-empty {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
