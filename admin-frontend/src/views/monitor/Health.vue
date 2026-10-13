<template>
  <div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="hdr">
          <span>系统健康</span>
          <el-button text @click="load"><el-icon><Refresh /></el-icon></el-button>
        </div>
      </template>

      <el-row :gutter="16">
        <el-col :xs="24" :sm="8">
          <h4>JVM</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="已用 / 最大">{{ numberText(jvm.heapUsedMB) }} / {{ numberText(jvm.heapMaxMB) }} MB</el-descriptions-item>
            <el-descriptions-item label="CPU 核数">{{ numberText(jvm.processors) }}</el-descriptions-item>
            <el-descriptions-item label="运行时长">{{ uptimeText(jvm.uptimeMs) }}</el-descriptions-item>
          </el-descriptions>
        </el-col>
        <el-col :xs="24" :sm="8">
          <h4>MySQL</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="状态">
              <el-tag :type="connectedStatus(ds.mysql?.connected).type" size="small">
                {{ connectedStatus(ds.mysql?.connected).label }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
          <el-table v-if="ds.mysql?.tables" :data="tableRows" size="small" style="margin-top:8px" max-height="320">
            <el-table-column prop="name" label="表" />
            <el-table-column prop="rows" label="行数" width="120" />
          </el-table>
        </el-col>
        <el-col :xs="24" :sm="8">
          <h4>Redis</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="状态">
              <el-tag :type="connectedStatus(ds.redis?.connected).type" size="small">
                {{ connectedStatus(ds.redis?.connected).label }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="ds:* key 数">{{ ds.redis?.ds_key_count ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="内存占用">
              {{ ds.redis?.memory_used_bytes == null ? '—' : numberText(ds.redis.memory_used_bytes / 1048576, 1, ' MB') }}
            </el-descriptions-item>
          </el-descriptions>

          <h4 style="margin-top:16px">Spot 缓存</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="存在">
              <el-tag :type="ds.spot?.present ? 'success' : 'info'" size="small">
                {{ ds.spot?.present === true ? '是' : ds.spot?.present === false ? '否' : '未确认' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="TTL(秒)">{{ ds.spot?.ttl_seconds ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="行数">{{ ds.spot?.rows ?? '—' }}</el-descriptions-item>
          </el-descriptions>
        </el-col>
      </el-row>
    </el-card>
    <el-card shadow="never" style="margin-top:16px">
      <template #header>库内参考交易日覆盖</template>
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>参考日 {{ anchor?.date || '—' }} · 日历{{ anchor?.calendarVerified === true ? '已验证' : '未验证' }}</template>
        {{ anchor?.note || '缺少独立交易日历，仅反映相对库内参考日的数据覆盖，不证明已更新到市场实际最新交易日。' }}
        <div>来源 {{ anchor?.source || '—' }} · 检查时间 {{ anchor?.asOf || '—' }} · 截止日 {{ anchor?.cutoffDate || '—' }} · 日历滞后 {{ numberText(anchor?.lagCalendarDays) }} 天</div>
      </el-alert>
      <div class="table-wrap">
        <el-table :data="freshnessRows" size="small" empty-text="未返回覆盖数据，不据此判定健康" style="margin-top:12px">
          <el-table-column type="expand"><template #default="{ row }"><div class="details">
            <p>{{ row.error || row.note || '无补充说明' }}</p>
            <p>模式 {{ row.coverageMode || '—' }} · 历史覆盖 {{ numberText(row.historyCoveragePct, 1, '%') }} · 该项参考日 {{ row.anchorDate || '—' }} · 分母来源 {{ row.universeSource || '—' }}</p>
            <el-table v-if="row.fieldCoverage?.length" :data="row.fieldCoverage" size="small">
              <el-table-column prop="field" label="字段" /><el-table-column label="有值 / 可用股票"><template #default="{ row: f }">{{ numberText(f.presentCodes) }} / {{ numberText(f.eligibleCodes) }}</template></el-table-column>
              <el-table-column label="字段覆盖"><template #default="{ row: f }">{{ numberText(f.coveragePct, 1, '%') }}</template></el-table-column>
            </el-table>
            <p v-if="row.fieldCoverage?.length">{{ row.fieldCoverageNote || '字段统计范围：每只股票最新一条记录，不是参考交易日截面。' }}</p>
          </div></template></el-table-column>
          <el-table-column prop="name" label="数据表" min-width="180" />
          <el-table-column label="状态" min-width="130"><template #default="{ row }"><el-tag :type="healthStatus(row.status).type" size="small">{{ healthStatus(row.status).label }}</el-tag></template></el-table-column>
          <el-table-column label="最新数据日" min-width="120"><template #default="{ row }">{{ row.latestDate || '—' }}</template></el-table-column>
          <el-table-column label="参考期有数据 / 合格宇宙" min-width="180"><template #default="{ row }">{{ numberText(row.coveredOnAnchor) }} / {{ numberText(row.eligibleUniverse) }}</template></el-table-column>
          <el-table-column label="参考期覆盖" min-width="110"><template #default="{ row }">{{ row.status === 'EVENT_DRIVEN' ? '不适用' : numberText(row.latestCoveragePct, 1, '%') }}</template></el-table-column>
          <el-table-column label="滞后 / 无历史" min-width="120"><template #default="{ row }">{{ numberText(row.staleCodes) }} / {{ numberText(row.missingCodes) }}</template></el-table-column>
          <el-table-column label="历史曾覆盖股票" min-width="130"><template #default="{ row }">{{ numberText(row.historyCodes) }}</template></el-table-column>
        </el-table>
      </div>
      <p class="note">日频按参考日、周频按参考周；财报、分红、龙虎榜等事件数据不要求每日覆盖全市场。历史曾覆盖不能替代本期覆盖。</p>
    </el-card>
    <el-card shadow="never" style="margin-top:16px">
      <template #header>复权全量重刷待办 · {{ numberText(ds.mysql?.basisRefresh?.pendingCount) }}</template>
      <p class="note">范围 {{ ds.mysql?.basisRefresh?.scope || '—' }} · {{ ds.mysql?.basisRefresh?.error || ds.mysql?.basisRefresh?.note || '未返回范围说明；不可将空列表当成全库已完成重刷。' }}</p>
      <el-table :data="ds.mysql?.basisRefresh?.items || []" size="small" empty-text="未返回待办明细；以待办数量和接口状态为准">
        <el-table-column prop="table" label="数据表" /><el-table-column prop="code" label="股票" /><el-table-column prop="requiredBars" label="所需历史根数" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getOverview, type MonitorOverview } from '@/api/monitor'
import { connectedStatus, healthStatus, numberText, uptimeText } from '@/utils/status'

const jvm = ref<Partial<MonitorOverview['jvm']>>({})
const ds = ref<MonitorOverview['dataService']>({})
const loading = ref(false)
const error = ref('')
const anchor = computed(() => ds.value.mysql?.freshnessAnchor)
const freshnessRows = computed(() => Object.entries(ds.value.mysql?.freshness || {}).map(([name, entry]) => ({ name, ...entry })))

const tableRows = computed(() => {
  const t = ds.value?.mysql?.tables || {}
  return Object.entries(t).map(([name, rows]) => ({ name, rows: numberText(rows) }))
})

async function load() {
  if (loading.value) return
  loading.value = true; error.value = ''; jvm.value = {}; ds.value = {}
  try { const o = await getOverview(); jvm.value = o.jvm || {}; ds.value = o.dataService || {} }
  catch (e) { error.value = e instanceof Error ? e.message : '健康检查加载失败' }
  finally { loading.value = false }
}

onMounted(() => load())
</script>

<style scoped>
.hdr { display: flex; justify-content: space-between; align-items: center; }
h4 { margin: 0 0 8px; font-size: 14px; }
.details { padding:4px 18px; font-size:12px; }
.note { color:var(--text-3); font-size:12px; line-height:1.7; }
.table-wrap { width:100%; overflow-x:auto; }
@media(max-width:767px) { .el-col { margin-bottom:16px; } }
</style>
