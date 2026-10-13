<template>
  <div>
    <el-row :gutter="16">
      <el-col :xs="24" :sm="14">
        <el-card shadow="never">
          <template #header>
            <div class="hdr">
              <span>注册任务</span>
              <el-button text @click="loadJobs"><el-icon><Refresh /></el-icon></el-button>
            </div>
          </template>
          <el-alert v-if="jobsError" :title="jobsError" type="error" :closable="false" />
          <p>调度器：{{ schedulerRunning === true ? '运行中' : schedulerRunning === false ? '未运行' : '未确认' }}</p>
          <el-table :data="jobs" size="small" empty-text="未加载到调度器">
            <el-table-column prop="id" label="Job ID" width="220" />
            <el-table-column prop="next_run_time" label="下次执行" />
            <el-table-column prop="trigger" label="触发条件" />
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="10">
        <el-card shadow="never">
          <template #header><div class="hdr"><span>手动触发</span></div></template>
          <el-select v-model="manualJob" placeholder="选择任务" style="width:60%; margin-right:8px">
            <el-option v-for="j in validJobs" :key="j" :label="j" :value="j" />
          </el-select>
          <el-button type="primary" :loading="running" :disabled="!validJobs.length" @click="runManual">触发</el-button>
          <p class="note">触发成功只代表已提交，实际结果以运行历史的完成状态及步骤证据为准。</p>
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
      <el-alert v-if="runsError" :title="runsError + '；下方可能为上次成功加载的记录'" type="error" :closable="false" />
      <p class="note">运行中每 5 秒自动更新，终态后停止；部分成功、跳过及结果未确认均不等同于成功。</p>
      <el-table :data="runs" v-loading="runsLoading" size="small" empty-text="尚无运行记录">
        <el-table-column type="expand"><template #default="{ row }"><div class="evidence">
          <p>结果协议 {{ row.outcome_version ?? '—（无结构化证据）' }} · 处理行数 {{ numberText(row.rows) }} · 宇宙规模 {{ numberText(row.universe_size) }}</p>
          <p>行数为管线报告的 upsert 行数，不是新增股票数，也不是数据新鲜度保证。</p>
          <p>{{ row.error || row.reason || '无补充原因' }}</p><pre v-if="row.steps">{{ JSON.stringify(row.steps, null, 2) }}</pre>
        </div></template></el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="jobStatus(row.status).type" size="small">{{ jobStatus(row.status).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="job" label="任务" width="140" />
        <el-table-column prop="id" label="Run ID" width="120" />
        <el-table-column prop="started_at" label="开始" />
        <el-table-column prop="finished_at" label="结束">
          <template #default="{ row }">{{ row.finished_at || '—' }}</template>
        </el-table-column>
        <el-table-column label="耗时(s)" width="100"><template #default="{ row }">{{ numberText(row.duration_s, 1) }}</template></el-table-column>
        <el-table-column label="原因 / 错误"><template #default="{ row }">{{ row.error || row.reason || '—' }}</template></el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listSchedulerJobs, runJob, clearCache,
  type SchedulerJob,
} from '@/api/tasks'
import { useTaskRuns } from '@/composables/useTaskRuns'
import { jobStatus, numberText } from '@/utils/status'

const jobs = ref<SchedulerJob[]>([])
const { runs, loading: runsLoading, error: runsError, refresh: loadRuns } = useTaskRuns()
const validJobs = ref<string[]>([])
const schedulerRunning = ref<boolean | null>(null)
const jobsError = ref('')
const manualJob = ref('postmarket')
const cachePattern = ref('ds:*')
const running = ref(false)

async function loadJobs() {
  try {
    const r = await listSchedulerJobs()
    jobs.value = r.jobs || []; schedulerRunning.value = r.running; jobsError.value = ''
    validJobs.value = r.valid_runs || []
    if (!validJobs.value.includes(manualJob.value)) manualJob.value = validJobs.value[0] || ''
  } catch (e) { jobsError.value = e instanceof Error ? e.message : '调度器加载失败'; schedulerRunning.value = null; validJobs.value = [] }
}
async function runManual() {
  running.value = true
  try {
    await runJob(manualJob.value)
    ElMessage.success(`已触发 ${manualJob.value}`)
    await loadRuns()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '任务提交失败')
  } finally {
    running.value = false
  }
}
async function clearCacheNow() {
  if (!cachePattern.value.includes('*')) {
    ElMessage.warning('pattern 必须包含 *')
    return
  }
  try {
    await ElMessageBox.confirm(`确认清除匹配 ${cachePattern.value} 的所有 Redis key?`, '提示', { type: 'warning' })
    const r: any = await clearCache(cachePattern.value)
    ElMessage.success(`清理请求完成，删除数量 ${numberText(r.deleted)}`)
  } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(e instanceof Error ? e.message : '清理失败') }
}

onMounted(() => {
  loadJobs()
  loadRuns()
})
</script>

<style scoped>
.hdr { display: flex; align-items: center; justify-content: space-between; }
.note, .evidence { font-size:12px; color:var(--text-3); line-height:1.6; }
.evidence { padding:8px 16px; }
.evidence pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:320px; overflow:auto; }
@media(max-width:767px) { .el-col { margin-bottom:12px; } }
</style>
