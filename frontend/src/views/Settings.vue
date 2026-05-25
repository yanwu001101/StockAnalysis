<template>
  <div class="page-container">
    <div class="settings-grid">

      <!-- 1. 数据健康面板 -->
      <section class="card">
        <header class="card-head">
          <h3>数据健康</h3>
          <div class="head-actions">
            <span v-if="health.timestamp" class="ts">{{ health.timestamp }}</span>
            <el-button size="small" :loading="loadingHealth" @click="loadHealth">刷新</el-button>
          </div>
        </header>

        <div class="status-row">
          <div class="status-pill" :class="health.mysql.connected ? 'ok' : 'bad'">
            MySQL · {{ health.mysql.connected ? '已连接' : '断开' }}
          </div>
          <div class="status-pill" :class="health.redis.connected ? 'ok' : 'bad'">
            Redis · {{ health.redis.connected ? '已连接' : '断开' }}
          </div>
          <div class="status-pill" :class="health.spot.present ? 'ok' : 'warn'">
            行情快照 · {{ spotLabel }}
          </div>
        </div>

        <div class="kv-grid" v-if="health.redis.connected">
          <div class="kv"><span>缓存 key 数</span><b>{{ health.redis.ds_key_count ?? '-' }}</b></div>
          <div class="kv"><span>Redis 内存</span><b>{{ formatBytes(health.redis.memory_used_bytes) }}</b></div>
          <div class="kv" v-if="health.spot.present">
            <span>快照行数</span><b>{{ health.spot.rows?.toLocaleString() ?? '-' }}</b>
          </div>
          <div class="kv" v-if="health.spot.present">
            <span>快照大小</span><b>{{ formatBytes(health.spot.size_bytes) }}</b>
          </div>
        </div>

        <div v-if="circuitEntries.length" class="circuit-row">
          <span class="row-label">数据源熔断:</span>
          <span
            v-for="c in circuitEntries"
            :key="c.name"
            class="circuit-tag"
            :class="`cb-${c.state}`"
          >{{ c.name }} · {{ circuitLabel(c.state) }}</span>
        </div>

        <details class="tables-fold" v-if="tableRows.length">
          <summary>数据库表行数 ({{ tableRows.length }})</summary>
          <div class="table-grid">
            <div v-for="t in tableRows" :key="t.name" class="kv" :class="{ 'kv-empty': !t.count }">
              <span>{{ t.name }}</span><b>{{ t.count == null ? '—' : t.count.toLocaleString() }}</b>
            </div>
          </div>
        </details>
      </section>

      <!-- 2. 数据管理 -->
      <section class="card">
        <header class="card-head"><h3>数据管理</h3></header>

        <div class="action-block">
          <div class="action-title">手动预热数据</div>
          <div class="action-desc">触发一次后台数据采集任务,完成前页面可继续使用。</div>
          <div class="action-row">
            <el-button
              v-for="job in JOBS"
              :key="job.id"
              size="small"
              :loading="warmupBusy[job.id]"
              :disabled="anyWarmupBusy"
              @click="triggerWarmup(job.id)"
            >{{ job.label }}</el-button>
          </div>
        </div>

        <div class="action-block">
          <div class="action-title">清空缓存</div>
          <div class="action-desc">删除 Redis 中 <code>ds:*</code> 所有 key。修复"明明有数据却显示为空"的情况。</div>
          <div class="action-row">
            <el-button size="small" type="warning" plain :loading="clearing" @click="confirmClear">清空 ds:* 缓存</el-button>
          </div>
        </div>

        <div class="action-block" v-if="recentRuns.length">
          <div class="action-title">最近任务</div>
          <el-table :data="recentRuns" size="small" :border="false" stripe>
            <el-table-column prop="job" label="任务" width="110" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <span class="status-tag" :class="`s-${row.status}`">{{ runStatusLabel(row.status) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="started_at" label="开始" width="170" />
            <el-table-column label="耗时" width="80">
              <template #default="{ row }">{{ row.duration_s != null ? row.duration_s + ' 秒' : '—' }}</template>
            </el-table-column>
            <el-table-column prop="error" label="错误" show-overflow-tooltip />
          </el-table>
        </div>
      </section>

      <!-- 3. 显示偏好 -->
      <section class="card">
        <header class="card-head"><h3>显示偏好</h3></header>
        <el-form label-position="top" size="default" class="pref-form">
          <el-form-item label="涨跌颜色">
            <el-radio-group v-model="settings.colorScheme">
              <el-radio-button value="red-up">
                <span class="up-sample">红涨</span><span class="down-sample">绿跌</span>
                <span class="hint-sm">A 股习惯</span>
              </el-radio-button>
              <el-radio-button value="red-down">
                <span class="up-sample">绿涨</span><span class="down-sample">红跌</span>
                <span class="hint-sm">国际习惯</span>
              </el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="金额单位">
            <el-radio-group v-model="settings.amountUnit">
              <el-radio-button value="yi">亿元</el-radio-button>
              <el-radio-button value="wan">万元</el-radio-button>
            </el-radio-group>
            <span class="hint">影响个股资金流、龙虎榜等大额数据的显示。</span>
          </el-form-item>

          <el-form-item label="K 线默认复权">
            <el-radio-group v-model="settings.klineAdjust">
              <el-radio-button value="qfq">前复权</el-radio-button>
              <el-radio-button value="hfq">后复权</el-radio-button>
              <el-radio-button value="none">不复权</el-radio-button>
            </el-radio-group>
            <span class="hint">个股详情 K 线打开时的默认选项。</span>
          </el-form-item>
        </el-form>
      </section>

      <!-- 4. 通用 -->
      <section class="card">
        <header class="card-head"><h3>通用</h3></header>
        <el-form label-position="top" size="default" class="pref-form">
          <el-form-item label="行情刷新间隔 (秒)">
            <el-input-number v-model="settings.refreshInterval" :min="5" :max="60" :step="5" />
            <span class="hint">仪表盘按此频率自动刷新。</span>
          </el-form-item>
          <el-form-item label="默认选股数量">
            <el-input-number v-model="settings.defaultLimit" :min="10" :max="200" :step="10" />
            <span class="hint">智能选股页"输出数量"的初始值。</span>
          </el-form-item>
        </el-form>
      </section>

      <!-- 5. 账户 -->
      <section class="card">
        <header class="card-head"><h3>账户</h3></header>
        <div class="account-row">
          <span class="account-name">{{ userStore.userInfo?.username || '未登录' }}</span>
          <el-button type="danger" plain @click="handleLogout">退出登录</el-button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useSettingsStore } from '@/stores/settings'
import {
  getAdminHealth,
  clearAdminCache,
  startWarmup,
  getWarmupStatus,
  type AdminHealth,
  type WarmupRun,
} from '@/api/admin'

const router = useRouter()
const userStore = useUserStore()
const settings = useSettingsStore()

const JOBS: { id: 'postmarket' | 'weekend' | 'premarket' | 'intraday'; label: string }[] = [
  { id: 'postmarket', label: '盘后 (K线/资金流/北向/龙虎榜)' },
  { id: 'weekend', label: '周末 (财务/股东/分红/概念)' },
  { id: 'premarket', label: '盘前' },
  { id: 'intraday', label: '盘中' },
]

const emptyHealth: AdminHealth = {
  timestamp: '',
  mysql: { connected: false },
  redis: { connected: false },
  spot: { present: false },
  circuits: {},
}

const health = ref<AdminHealth>(emptyHealth)
const loadingHealth = ref(false)
const warmupBusy = reactive<Record<string, boolean>>({})
const clearing = ref(false)
const recentRuns = ref<WarmupRun[]>([])
let pollTimer: number | undefined

const anyWarmupBusy = computed(() => Object.values(warmupBusy).some(v => v))

const spotLabel = computed(() => {
  const s = health.value.spot
  if (!s.present) return s.ttl_seconds === -2 ? '缺失' : '过期'
  if (s.ttl_seconds == null) return '正常'
  return `${s.ttl_seconds}s 剩余`
})

const tableRows = computed(() =>
  Object.entries(health.value.mysql.tables || {})
    .map(([name, count]) => ({ name, count: count as number | null }))
)

const circuitEntries = computed(() =>
  Object.entries(health.value.circuits || {}).map(([name, state]) => ({ name, state }))
)

async function loadHealth() {
  loadingHealth.value = true
  try {
    health.value = await getAdminHealth()
  } catch (e) {
    // 全局 interceptor 已经弹过错了
  } finally {
    loadingHealth.value = false
  }
}

async function loadRecent() {
  try {
    const res: any = await getWarmupStatus()
    recentRuns.value = (res && res.items) ? res.items : []
  } catch (_) {}
}

async function triggerWarmup(job: 'postmarket' | 'weekend' | 'premarket' | 'intraday') {
  warmupBusy[job] = true
  try {
    const run = await startWarmup(job)
    ElMessage.success(`已启动: ${job} (${run.id})`)
    await loadRecent()
    pollUntilDone(run.id)
  } catch (_) {
    warmupBusy[job] = false
  }
}

function pollUntilDone(id: string) {
  const tick = async () => {
    try {
      const r: any = await getWarmupStatus(id)
      const run = r as WarmupRun
      // refresh recent list
      const idx = recentRuns.value.findIndex(x => x.id === id)
      if (idx >= 0) recentRuns.value[idx] = run
      else await loadRecent()
      if (run.status === 'running') {
        pollTimer = window.setTimeout(tick, 2000)
      } else {
        warmupBusy[run.job] = false
        if (run.status === 'success') {
          ElMessage.success(`${run.job} 完成 (${run.duration_s}s)`)
          loadHealth()
        } else {
          ElMessage.error(`${run.job} 失败: ${run.error || '未知错误'}`)
        }
      }
    } catch (_) {
      // give up polling on error; user can refresh
    }
  }
  tick()
}

async function confirmClear() {
  try {
    await ElMessageBox.confirm('确定要清空 Redis 中所有 ds:* key 吗?', '清空缓存', {
      type: 'warning',
      confirmButtonText: '清空',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  clearing.value = true
  try {
    const res = await clearAdminCache('ds:*')
    ElMessage.success(`已删除 ${res.deleted} 个 key`)
    await loadHealth()
  } catch (_) {
  } finally {
    clearing.value = false
  }
}

function handleLogout() {
  userStore.logout()
  router.push('/login')
}

function formatBytes(n?: number) {
  if (n == null) return '—'
  if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(2) + ' MB'
  if (n >= 1024) return (n / 1024).toFixed(1) + ' KB'
  return n + ' B'
}

function runStatusLabel(s: string) {
  if (s === 'running') return '运行中'
  if (s === 'success') return '成功'
  if (s === 'failed') return '失败'
  return s
}

function circuitLabel(state: string) {
  if (state === 'closed') return '正常'
  if (state === 'open') return '熔断'
  if (state === 'half_open') return '探测中'
  return state
}

onMounted(() => {
  loadHealth()
  loadRecent()
})
onUnmounted(() => {
  if (pollTimer) window.clearTimeout(pollTimer)
})
</script>

<style scoped>
.page-container { padding: 16px; }
.settings-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: 1fr;
  max-width: 920px;
}
.card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 18px 20px;
}
.card-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.card-head h3 { margin: 0; font-size: 15px; color: var(--text); font-weight: 600; }
.head-actions { display: flex; align-items: center; gap: 10px; }
.ts { font-size: 12px; color: var(--text-3); }

.status-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.status-pill {
  padding: 5px 12px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  background: var(--bg-2);
  color: var(--text-2);
}
.status-pill.ok { background: var(--brand-soft); color: var(--brand); }
.status-pill.bad { background: var(--up-soft); color: var(--up); }
.status-pill.warn { background: var(--warn-soft); color: #b07a00; }

.kv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}
.kv {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--bg-2);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
}
.kv span { font-size: 12px; color: var(--text-3); }
.kv b { font-family: var(--font-num); font-size: 13px; color: var(--text); font-weight: 600; }
.kv-empty b { color: var(--text-4); }

.circuit-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 4px; }
.row-label { font-size: 12px; color: var(--text-3); }
.circuit-tag {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--bg-2);
  color: var(--text-2);
}
.circuit-tag.cb-closed { background: var(--brand-soft); color: var(--brand); }
.circuit-tag.cb-open { background: var(--up-soft); color: var(--up); }
.circuit-tag.cb-half_open { background: var(--warn-soft); color: #b07a00; }

.tables-fold { margin-top: 12px; }
.tables-fold summary {
  cursor: pointer;
  font-size: 12px;
  color: var(--text-3);
  padding: 4px 0;
}
.table-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 6px;
  margin-top: 8px;
}

.action-block { margin-bottom: 18px; }
.action-block:last-child { margin-bottom: 0; }
.action-title { font-size: 13px; color: var(--text); font-weight: 600; margin-bottom: 4px; }
.action-desc { font-size: 12px; color: var(--text-3); margin-bottom: 8px; }
.action-desc code {
  background: var(--bg-2);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-family: var(--font-num);
  font-size: 12px;
}
.action-row { display: flex; flex-wrap: wrap; gap: 8px; }

.status-tag { font-size: 11px; padding: 2px 8px; border-radius: var(--radius-pill); }
.s-running { background: var(--warn-soft); color: #b07a00; }
.s-success { background: var(--brand-soft); color: var(--brand); }
.s-failed  { background: var(--up-soft); color: var(--up); }

.pref-form :deep(.el-form-item) { margin-bottom: 16px; }
.hint { margin-left: 12px; font-size: 12px; color: var(--text-3); }
.hint-sm { margin-left: 6px; font-size: 11px; color: var(--text-3); opacity: 0.8; }

.up-sample   { color: var(--up); font-weight: 600; }
.down-sample { color: var(--down); font-weight: 600; margin-left: 4px; }

.account-row {
  display: flex; align-items: center; justify-content: space-between;
}
.account-name { font-size: 14px; color: var(--text-2); }
</style>
