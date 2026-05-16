<template>
  <div class="page-container">
    <header class="page-head">
      <h1>龙虎榜</h1>
      <p class="dek">机构席位 / 游资 / 上榜原因 多维查看 · 数据来源东方财富</p>
    </header>

    <div class="toolbar">
      <el-radio-group v-model="windowDays" size="small">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="14">近 14 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
        <el-radio-button :value="60">近 60 天</el-radio-button>
      </el-radio-group>

      <el-radio-group v-model="activeTab" size="small">
        <el-radio-button value="recent">明细</el-radio-button>
        <el-radio-button value="institution">净买榜</el-radio-button>
        <el-radio-button value="stock">个股上榜频次</el-radio-button>
      </el-radio-group>
    </div>

    <div class="card" v-loading="loading">
      <el-table v-if="activeTab === 'recent'" :data="recent" stripe size="small"
                @row-click="goStock" :row-style="{ cursor: 'pointer' }" empty-text="无数据">
        <el-table-column prop="tradeDate" label="日期" width="100" />
        <el-table-column prop="code" label="代码" width="80" />
        <el-table-column prop="reason" label="上榜原因" min-width="200" show-overflow-tooltip />
        <el-table-column prop="seatType" label="席位类型" width="90">
          <template #default="{ row }">
            <span class="tag" :class="seatCls(row.seatType)">{{ row.seatType || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="seatName" label="席位" min-width="180" show-overflow-tooltip />
        <el-table-column label="买入额(万)" width="110" align="right">
          <template #default="{ row }">{{ wan(row.buyAmount) }}</template>
        </el-table-column>
        <el-table-column label="卖出额(万)" width="110" align="right">
          <template #default="{ row }">{{ wan(row.sellAmount) }}</template>
        </el-table-column>
        <el-table-column label="净额(万)" width="100" align="right">
          <template #default="{ row }">
            <span :class="(row.netAmount || 0) >= 0 ? 'price-up' : 'price-down'">{{ wan(row.netAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <el-table v-else-if="activeTab === 'institution'" :data="instRank" stripe size="small"
                @row-click="goStock" :row-style="{ cursor: 'pointer' }" empty-text="无数据">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="name" label="名称" width="100" />
        <el-table-column prop="code" label="代码" width="80" />
        <el-table-column prop="industry" label="行业" width="100" />
        <el-table-column prop="appearances" label="机构上榜次数" width="110" align="center" />
        <el-table-column label="累计净买(万)" align="right">
          <template #default="{ row }">
            <span :class="row.netSum >= 0 ? 'price-up' : 'price-down'" class="num">{{ wan(row.netSum) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计买入(万)" align="right">
          <template #default="{ row }">{{ wan(row.buySum) }}</template>
        </el-table-column>
        <el-table-column prop="lastSeen" label="最近上榜" width="100" />
      </el-table>

      <el-table v-else :data="stockRank" stripe size="small"
                @row-click="goStock" :row-style="{ cursor: 'pointer' }" empty-text="无数据">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="name" label="名称" width="100" />
        <el-table-column prop="code" label="代码" width="80" />
        <el-table-column prop="industry" label="行业" width="100" />
        <el-table-column prop="appearances" label="上榜天数" width="100" align="center" />
        <el-table-column label="累计净额(万)" align="right">
          <template #default="{ row }">
            <span :class="row.netSum >= 0 ? 'price-up' : 'price-down'" class="num">{{ wan(row.netSum) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reasons" label="上榜原因" min-width="200" show-overflow-tooltip />
        <el-table-column prop="lastSeen" label="最近上榜" width="100" />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getLhbRecent, getLhbInstitutionRank, getLhbStockRank, type LhbRow, type LhbAggRow } from '@/api/lhb'

const router = useRouter()
const windowDays = ref(30)
const activeTab = ref<'recent' | 'institution' | 'stock'>('recent')
const recent = ref<LhbRow[]>([])
const instRank = ref<LhbAggRow[]>([])
const stockRank = ref<LhbAggRow[]>([])
const loading = ref(false)

function wan(v: number | null | undefined) {
  if (v == null) return '—'
  return (v / 10000).toFixed(0)
}

function seatCls(t: string) {
  if (t.includes('机构')) return 'tag-inst'
  if (t.includes('游资') || t.includes('营业部')) return 'tag-retail'
  return ''
}

function goStock(row: any) { router.push(`/stock/${row.code}`) }

async function load() {
  loading.value = true
  try {
    if (activeTab.value === 'recent') {
      recent.value = await getLhbRecent(windowDays.value)
    } else if (activeTab.value === 'institution') {
      instRank.value = await getLhbInstitutionRank(windowDays.value)
    } else {
      stockRank.value = await getLhbStockRank(windowDays.value)
    }
  } finally {
    loading.value = false
  }
}

watch([windowDays, activeTab], load)
onMounted(load)
</script>

<style scoped>
.page-head { margin-bottom: 18px; }
.page-head h1 { font-size: 22px; font-weight: 600; }
.page-head .dek { margin-top: 4px; color: var(--text-3); font-size: 13px; }
.toolbar {
  display: flex; gap: 16px; margin-bottom: 14px; flex-wrap: wrap;
}
.card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 16px 18px;
}
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  background: var(--surface-2);
  color: var(--text-3);
}
.tag-inst { background: var(--brand-soft); color: var(--brand); font-weight: 600; }
.tag-retail { background: var(--warn-soft); color: #B88800; }
</style>
