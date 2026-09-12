<template>
  <AppCard title="F10 公司资料" :loading="loading">
    <template #actions>
      <SegmentTabs v-model="tab" :options="tabOptions" small />
    </template>

    <div v-if="tab === 'profile'">
      <div class="profile-grid" v-if="data?.profile && Object.keys(data.profile).length">
        <div class="profile-item" v-for="(v, k) in data.profile" :key="k">
          <span class="profile-label">{{ k }}</span>
          <span class="profile-value">{{ profileText(String(k), v) }}</span>
        </div>
      </div>
      <el-empty v-else description="暂无公司概况数据" :image-size="80" />
    </div>

    <StockTable v-else-if="tab === 'holders'" :rows="data?.topHolders || []" :columns="holderColumns" :stock="false" :clickable="false" dense row-key="rank" empty="暂无股东数据" />

    <StockTable v-else-if="tab === 'dividend'" :rows="data?.dividends || []" :columns="dividendColumns" :stock="false" :clickable="false" dense row-key="annDate" empty="暂无分红数据" />

    <div v-else>
      <div class="peer-ranks" v-if="data?.peers?.ranks">
        <div class="rank-chip">
          <span class="rank-label">行业</span>
          <span class="rank-value">{{ data.peers.ranks.industry }} ({{ data.peers.ranks.industrySize }} 家)</span>
        </div>
        <div class="rank-chip" v-if="data.peers.ranks.peByRank">
          <span class="rank-label">PE 排名</span>
          <span class="rank-value num">{{ data.peers.ranks.peByRank }} / {{ data.peers.ranks.industrySize }}</span>
        </div>
        <div class="rank-chip" v-if="data.peers.ranks.pbByRank">
          <span class="rank-label">PB 排名</span>
          <span class="rank-value num">{{ data.peers.ranks.pbByRank }} / {{ data.peers.ranks.industrySize }}</span>
        </div>
        <div class="rank-chip" v-if="data.peers.ranks.roeRank">
          <span class="rank-label">ROE 排名</span>
          <span class="rank-value num">{{ data.peers.ranks.roeRank }} / {{ data.peers.ranks.industrySize }}</span>
        </div>
        <div class="rank-chip" v-if="data.peers.ranks.marketCapRank">
          <span class="rank-label">市值排名</span>
          <span class="rank-value num">{{ data.peers.ranks.marketCapRank }} / {{ data.peers.ranks.industrySize }}</span>
        </div>
      </div>
      <StockTable
        :rows="data?.peers?.peers || []"
        :columns="peerColumns"
        dense
        empty="暂无同业数据"
        :row-class="(r: any) => (r.isTarget ? 'peer-target' : undefined)"
        :to="(r: any) => (r.isTarget ? null : stockPath(r.code))"
      />
    </div>
  </AppCard>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { stockPath } from '@/utils/score'
import type { StockColumn, SegmentOption } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import StockTable from '@/components/stock/StockTable.vue'

defineProps<{ data: any; loading: boolean }>()

// 概况里的数值原样是浮点长尾（如 15940.54054331 / 1594054054331.0），按字段语义收敛显示。
function profileText(key: string, v: any): string {
  if (v == null || v === '') return '—'
  const n = typeof v === 'number' ? v : (typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v.trim()) ? Number(v) : NaN)
  if (!Number.isFinite(n)) return String(v)
  if (/市值/.test(key) && !/\(亿\)|（亿）/.test(key) && Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + ' 亿'
  if (/代码/.test(key)) return String(v)
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

type Tab = 'profile' | 'holders' | 'dividend' | 'peers'
const tab = ref<Tab>('profile')
const tabOptions: SegmentOption<Tab>[] = [
  { label: '公司概况', value: 'profile' },
  { label: '十大股东', value: 'holders' },
  { label: '分红送转', value: 'dividend' },
  { label: '同业比较', value: 'peers' },
]

const holderColumns: StockColumn[] = [
  { key: 'rank', label: '名次', align: 'center', width: 60, mobile: 'hidden' },
  { key: 'name', label: '股东名称', mobile: 'title' },
  { key: 'type', label: '股东性质', mobile: 'secondary' },
  { key: 'shares', label: '持股数量(万)', type: 'num', digits: 2, format: r => r.shares / 10000, mobile: 'primary' },
  { key: 'ratio', label: '持股比例', type: 'percent', digits: 2, mobile: 'primary' },
  { key: 'change', label: '持股变动', mobile: 'secondary' },
]
const dividendColumns: StockColumn[] = [
  { key: 'annDate', label: '公告日', mobile: 'title' },
  { key: 'exDate', label: '除权日', mobile: 'secondary' },
  { key: 'cashPer10', label: '现金分红(每10股/元)', type: 'num', digits: 2, mobile: 'primary' },
  { key: 'sharePer10', label: '送股(每10股)', type: 'num', digits: 2 },
  { key: 'transferPer10', label: '转增(每10股)', type: 'num', digits: 2 },
]
const peerColumns: StockColumn[] = [
  { key: 'price', label: '最新价', type: 'price' },
  { key: 'changePercent', label: '涨跌幅', type: 'change' },
  { key: 'pe', label: 'PE', type: 'num', digits: 2, format: r => (r.pe > 0 ? r.pe : null) },
  { key: 'pb', label: 'PB', type: 'num', digits: 2, format: r => (r.pb > 0 ? r.pb : null) },
  { key: 'roe', label: 'ROE', type: 'percent', digits: 2, format: r => (r.roe ? r.roe : null) },
  { key: 'marketCap', label: '市值(亿)', type: 'num', digits: 0 },
]
</script>

<style scoped>
.profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px 24px;
}
.profile-item {
  display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
  border-bottom: 1px dashed var(--line);
  padding-bottom: 6px;
}
.profile-label { color: var(--text-3); font-size: 13px; flex-shrink: 0; }
.profile-value { color: var(--text); font-size: 14px; font-weight: 500; text-align: right; overflow-wrap: anywhere; }
.peer-ranks { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.rank-chip {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--brand-soft);
  border-radius: var(--radius-pill);
  padding: 4px 12px;
  font-size: 12px;
}
.rank-label { color: var(--text-3); }
.rank-value { color: var(--brand); font-weight: 600; }
:deep(.peer-target) { background: var(--brand-soft) !important; }
:deep(.peer-target .st-name), :deep(.peer-target .sc-title) { font-weight: 700; }
@media (max-width: 768px) {
  .profile-grid { grid-template-columns: 1fr; gap: 8px; }
}
</style>
