<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <div class="hdr">
              <span>注册任务</span>
              <el-button text @click="loadJobs"><el-icon><Refresh /></el-icon></el-button>
            </div>
          </template>
          <el-table :data="jobs" size="small" empty-text="未加载到调度器">
            <el-table-column prop="id" label="Job ID" width="220" />
            <el-table-column prop="next_run_time" label="下次执行" />
            <el-table-column prop="trigger" label="触发条件" />
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card shadow="never">
          <template #header><div class="hdr"><span>手动触发</span></div></template>
          <el-select v-model="manualJob" placeholder="选择任务" style="width:60%; margin-right:8px">
            <el-option v-for="j in validJobs" :key="j" :label="j" :value="j" />
          </el-select>
          <el-button type="primary" :loading="running" @click="runManual">触发</el-button>
          <el-divider />
          <p style="color:var(--text-3); font-size:13px;">缓存清理</p>
          <el-input v-model="cachePattern" placeholder="key pattern,例如 ds:*" style="width:60%; margin-right:8px" />
          <el-button type="warning" @click="clearCacheNow">清除</el-button>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-top:16px">
      <template #header>
        <div class="hdr">
          <span>近期运行历史</span>
          <el-button text @click="loadRuns"><el-icon><Refresh /></el-icon></el-button>
        </div>
      </template>
      <el-table :data="runs" size="small" empty-text="尚无运行记录">
        <el-table-column prop="id" label="Run ID" width="120" />
        <el-table-column prop="job" label="任务" width="140" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="started_at" label="开始" />
        <el-table-column prop="finished_at" label="结束">
          <template #default="{ row }">{{ row.finished_at || '—' }}</template>
        </el-table-column>
        <el-table-column prop="duration_s" label="耗时(s)" width="100" />
        <el-table-column prop="error" label="错误" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listSchedulerJobs, runJob, listRuns, clearCache,
  type SchedulerJob, type JobRun,
} from '@/api/tasks'

const jobs = ref<SchedulerJob[]>([])
const runs = ref<JobRun[]>([])
const validJobs = ref<string[]>(['postmarket', 'weekend', 'premarket', 'intraday', 'strategy_score'])
const manualJob = ref('postmarket')
const cachePattern = ref('ds:*')
const running = ref(false)

function statusType(s: string) {
  if (s === 'success') return 'success'
  if (s === 'failed') return 'danger'
  return 'warning'
}

async function loadJobs() {
  const r = await listSchedulerJobs()
  jobs.value = r.jobs || []
  if (r.valid_runs?.length) validJobs.value = r.valid_runs
}
async function loadRuns() {
  const r = await listRuns() as { items: JobRun[] }
  runs.value = r.items || []
}
async function runManual() {
  running.value = true
  try {
    await runJob(manualJob.value)
    ElMessage.success(`已触发 ${manualJob.value}`)
    setTimeout(loadRuns, 600)
  } finally {
    running.value = false
  }
}
async function clearCacheNow() {
  if (!cachePattern.value.includes('*')) {
    ElMessage.warning('pattern 必须包含 *')
    return
  }
  await ElMessageBox.confirm(`确认清除匹配 ${cachePattern.value} 的所有 Redis key?`, '提示', { type: 'warning' })
  const r: any = await clearCache(cachePattern.value)
  ElMessage.success(`已清除 ${r.deleted ?? 0} 个 key`)
}

onMounted(() => {
  loadJobs()
  loadRuns()
})
</script>

<style scoped>
.hdr { display: flex; align-items: center; justify-content: space-between; }
</style>
