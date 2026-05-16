<template>
  <div class="page-container">
    <header class="page-head">
      <h1>资金流向</h1>
      <p class="dek">主力资金 · 北向加仓 · 板块轮动</p>
    </header>

    <div class="toolbar">
      <el-radio-group v-model="windowDays" size="small">
        <el-radio-button :value="3">3日</el-radio-button>
        <el-radio-button :value="5">5日</el-radio-button>
        <el-radio-button :value="10">10日</el-radio-button>
        <el-radio-button :value="20">20日</el-radio-button>
      </el-radio-group>

      <el-radio-group v-model="activeTab" size="small">
        <el-radio-button value="main-in">主力净流入</el-radio-button>
        <el-radio-button value="main-out">主力净流出</el-radio-button>
        <el-radio-button value="nb">北向加仓</el-radio-button>
        <el-radio-button value="sector">板块资金</el-radio-button>
      </el-radio-group>
    </div>

    <div class="card" v-loading="loading">
      <el-table v-if="activeTab === 'main-in' || activeTab === 'main-out'" :data="mainRows" stripe size="small"
                @row-click="goStock" :row-style="{ cursor: 'pointer' }" empty-text="无数据">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="name" label="名称" width="100" />
        <el-table-column prop="code" label="代码" width="80" />
        <el-table-column prop="industry" label="行业" width="100" />
        <el-table-column label="最新价" width="80" align="right">
          <template #default="{ row }">{{ row.price.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="涨跌幅" width="80" align="right">
          <template #default="{ row }">
            <span :class="row.changePercent >= 0 ? 'price-up' : 'price-down'">
              {{ row.changePercent >= 0 ? '+' : '' }}{{ row.changePercent }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="主力净额(万)" align="right">
          <template #default="{ row }">
            <span :class="row.mainNetSum >= 0 ? 'price-up' : 'price-down'" class="num">{{ wan(row.mainNetSum) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="超大单(万)" align="right">
          <template #default="{ row }">
            <span :class="row.superLargeSum >= 0 ? 'price-up' : 'price-down'" class="num">{{ wan(row.superLargeSum) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="大单(万)" align="right">
          <template #default="{ row }">
            <span :class="row.largeSum >= 0 ? 'price-up' : 'price-down'" class="num">{{ wan(row.largeSum) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <el-table v-else-if="activeTab === 'nb'" :data="nbRows" stripe size="small"
                @row-click="goStock" :row-style="{ cursor: 'pointer' }" empty-text="无数据">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="name" label="名称" width="100" />
        <el-table-column prop="code" label="代码" width="80" />
        <el-table-column prop="industry" label="行业" width="100" />
        <el-table-column label="最新价" width="80" align="right">
          <template #default="{ row }">{{ row.price.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="北向加仓股数" align="right">
          <template #default="{ row }">
            <span :class="row.sharesDiff >= 0 ? 'price-up' : 'price-down'" class="num">
              {{ row.sharesDiff >= 0 ? '+' : '' }}{{ (row.sharesDiff / 10000).toFixed(1) }}万股
            </span>
          </template>
        </el-table-column>
        <el-table-column label="当前持股(万股)" align="right">
          <template #default="{ row }">{{ (row.currentShares / 10000).toFixed(0) }}</template>
        </el-table-column>
        <el-table-column label="占比" width="80" align="right">
          <template #default="{ row }">{{ row.currentRatio.toFixed(2) }}%</template>
        </el-table-column>
      </el-table>

      <el-table v-else :data="sectorRows" stripe size="small" empty-text="无数据">
        <el-table-column prop="rank" label="#" width="50" />
        <el-table-column prop="name" label="板块" min-width="120" />
        <el-table-column prop="count" label="家数" width="80" align="center" />
        <el-table-column label="平均涨跌" width="100" align="right">
          <template #default="{ row }">
            <span :class="row.avgChange >= 0 ? 'price-up' : 'price-down'">
              {{ row.avgChange >= 0 ? '+' : '' }}{{ row.avgChange }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="成交额(亿)" align="right" />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getMainRank, getNorthboundRank, getSectorFlow,
         type MainFlowRow, type NbFlowRow, type SectorRow } from '@/api/moneyflow'

const router = useRouter()
const windowDays = ref(5)
const activeTab = ref<'main-in' | 'main-out' | 'nb' | 'sector'>('main-in')
const mainRows = ref<MainFlowRow[]>([])
const nbRows = ref<NbFlowRow[]>([])
const sectorRows = ref<SectorRow[]>([])
const loading = ref(false)

function wan(v: number) { return (v / 10000).toFixed(0) }
function goStock(row: any) { router.push(`/stock/${row.code}`) }

async function load() {
  loading.value = true
  try {
    if (activeTab.value === 'main-in') {
      mainRows.value = await getMainRank(windowDays.value, 30, 'inflow')
    } else if (activeTab.value === 'main-out') {
      mainRows.value = await getMainRank(windowDays.value, 30, 'outflow')
    } else if (activeTab.value === 'nb') {
      nbRows.value = await getNorthboundRank(windowDays.value, 30)
    } else {
      sectorRows.value = await getSectorFlow()
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
</style>
