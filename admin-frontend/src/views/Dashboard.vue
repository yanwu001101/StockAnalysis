<template>
  <div class="dashboard">
    <el-row :gutter="16">
      <el-col :span="6" v-for="card in cards" :key="card.label">
        <el-card class="stat-card" shadow="never">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>系统资源</span>
              <el-button text @click="loadOverview"><el-icon><Refresh /></el-icon></el-button>
            </div>
          </template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="JVM 已用堆">{{ jvm.heapUsedMB }} MB / {{ jvm.heapMaxMB }} MB</el-descriptions-item>
            <el-descriptions-item label="CPU 核数">{{ jvm.processors }}</el-descriptions-item>
            <el-descriptions-item label="进程已运行">{{ formatUptime(jvm.uptimeMs) }}</el-descriptions-item>
            <el-descriptions-item label="MySQL">
              <el-tag :type="dsMysqlOk ? 'success' : 'danger'" size="small">
                {{ dsMysqlOk ? '正常' : '断开' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Redis">
              <el-tag :type="dsRedisOk ? 'success' : 'danger'" size="small">
                {{ dsRedisOk ? '正常' : '断开' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header><div class="card-header"><span>最近任务</span></div></template>
          <el-table :data="recentRuns" size="small" empty-text="暂无任务">
            <el-table-column prop="job" label="任务" width="120" />
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
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
import { getOverview } from '@/api/monitor'
import { listRuns, type JobRun } from '@/api/tasks'
import { getUserStats } from '@/api/users'

const jvm = ref({ heapUsedMB: 0, heapMaxMB: 0, processors: 0, uptimeMs: 0 })
const dataService = ref<any>({})
const recentRuns = ref<JobRun[]>([])
const stats = ref({ total: 0, admins: 0, disabled: 0, todayNew: 0 })

const dsMysqlOk = computed(() => dataService.value?.mysql?.connected === true)
const dsRedisOk = computed(() => dataService.value?.redis?.connected === true)

const cards = computed(() => [
  { label: '注册用户', value: stats.value.total },
  { label: '今日新增', value: stats.value.todayNew },
  { label: '管理员数', value: stats.value.admins },
  { label: '已禁用', value: stats.value.disabled },
])

function statusType(s: string) {
  if (s === 'success') return 'success'
  if (s === 'failed') return 'danger'
  return 'warning'
}
function formatUptime(ms: number) {
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h} 小时 ${m} 分`
}
async function loadOverview() {
  const ov = await getOverview()
  jvm.value = ov.jvm
  dataService.value = ov.dataService
}
async function loadRuns() {
  const r = await listRuns()
  recentRuns.value = (r as any).items || []
}
async function loadStats() {
  stats.value = await getUserStats()
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
