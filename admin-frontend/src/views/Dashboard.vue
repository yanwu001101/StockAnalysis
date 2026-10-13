<template>
  <div class="dashboard">
    <el-alert v-for="(message, section) in errors" :key="section" :title="message" type="error" :closable="false" />
    <el-row :gutter="16">
      <el-col :xs="12" :sm="6" v-for="card in cards" :key="card.label">
        <el-card class="stat-card" shadow="never">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top:16px">
      <el-col :xs="24" :sm="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>系统资源</span>
              <el-button text @click="loadOverview"><el-icon><Refresh /></el-icon></el-button>
            </div>
          </template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="JVM 已用堆">{{ numberText(jvm.heapUsedMB) }} MB / {{ numberText(jvm.heapMaxMB) }} MB</el-descriptions-item>
            <el-descriptions-item label="CPU 核数">{{ numberText(jvm.processors) }}</el-descriptions-item>
            <el-descriptions-item label="进程已运行">{{ uptimeText(jvm.uptimeMs) }}</el-descriptions-item>
            <el-descriptions-item label="MySQL">
              <el-tag :type="connectedStatus(dataService.mysql?.connected).type" size="small">
                {{ connectedStatus(dataService.mysql?.connected).label }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Redis">
              <el-tag :type="connectedStatus(dataService.redis?.connected).type" size="small">
                {{ connectedStatus(dataService.redis?.connected).label }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="12">
        <el-card shadow="never">
          <template #header><div class="card-header"><span>最近任务</span></div></template>
          <el-table :data="recentRuns" size="small" empty-text="暂无任务">
            <el-table-column prop="job" label="任务" width="120" />
            <el-table-column prop="status" label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="jobStatus(row.status).type" size="small">{{ jobStatus(row.status).label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="started_at" label="开始时间" />
            <el-table-column prop="duration_s" label="耗时(s)" width="80" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getOverview, type MonitorOverview } from '@/api/monitor'
import { listRuns, type JobRun } from '@/api/tasks'
import { getUserStats } from '@/api/users'
import { connectedStatus, jobStatus, numberText, uptimeText } from '@/utils/status'

const jvm = ref<Partial<MonitorOverview['jvm']>>({})
const dataService = ref<any>({})
const recentRuns = ref<JobRun[]>([])
const stats = ref<{ total?: number; admins?: number; disabled?: number; todayNew?: number }>({})
const errors = ref<Record<string, string>>({})

const cards = computed(() => [
  { label: '注册用户', value: numberText(stats.value.total) },
  { label: '今日新增', value: numberText(stats.value.todayNew) },
  { label: '管理员数', value: numberText(stats.value.admins) },
  { label: '已禁用', value: numberText(stats.value.disabled) },
])

async function loadOverview() {
  jvm.value = {}; dataService.value = {}
  try { const ov = await getOverview(); jvm.value = ov.jvm || {}; dataService.value = ov.dataService || {}; delete errors.value.overview }
  catch { errors.value.overview = '系统资源加载失败，连接状态未确认' }
}
async function loadRuns() {
  try { const r = await listRuns(); recentRuns.value = r.items || []; delete errors.value.runs }
  catch { errors.value.runs = '近期任务加载失败；已有记录可能过期' }
}
async function loadStats() {
  try { stats.value = await getUserStats(); delete errors.value.stats }
  catch { stats.value = {}; errors.value.stats = '用户统计加载失败' }
}

onMounted(() => {
  loadOverview()
  loadRuns()
  loadStats()
})
</script>

<style scoped>
.dashboard { padding: 4px; }
.stat-card { border-radius: var(--radius-lg); border: 1px solid var(--line); }
.stat-label { color: var(--text-3); font-size: 13px; }
.stat-value { color: var(--text); font-size: 26px; font-weight: 600; margin-top: 4px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
</style>
