<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="hdr">
          <span>系统健康</span>
          <el-button text @click="load"><el-icon><Refresh /></el-icon></el-button>
        </div>
      </template>

      <el-row :gutter="16">
        <el-col :span="8">
          <h4>JVM</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="已用 / 最大">{{ jvm.heapUsedMB }} / {{ jvm.heapMaxMB }} MB</el-descriptions-item>
            <el-descriptions-item label="CPU 核数">{{ jvm.processors }}</el-descriptions-item>
            <el-descriptions-item label="运行时长">{{ formatUptime(jvm.uptimeMs) }}</el-descriptions-item>
          </el-descriptions>
        </el-col>
        <el-col :span="8">
          <h4>MySQL</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="状态">
              <el-tag :type="ds.mysql?.connected ? 'success' : 'danger'" size="small">
                {{ ds.mysql?.connected ? '正常' : '断开' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
          <el-table v-if="ds.mysql?.tables" :data="tableRows" size="small" style="margin-top:8px" max-height="320">
            <el-table-column prop="name" label="表" />
            <el-table-column prop="rows" label="行数" width="120" />
          </el-table>
        </el-col>
        <el-col :span="8">
          <h4>Redis</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="状态">
              <el-tag :type="ds.redis?.connected ? 'success' : 'danger'" size="small">
                {{ ds.redis?.connected ? '正常' : '断开' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="ds:* key 数">{{ ds.redis?.ds_key_count ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="内存占用">
              {{ ds.redis?.memory_used_bytes ? (ds.redis.memory_used_bytes / 1024 / 1024).toFixed(1) + ' MB' : '—' }}
            </el-descriptions-item>
          </el-descriptions>

          <h4 style="margin-top:16px">Spot 缓存</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="存在">
              <el-tag :type="ds.spot?.present ? 'success' : 'info'" size="small">
                {{ ds.spot?.present ? '是' : '否' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="TTL(秒)">{{ ds.spot?.ttl_seconds ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="行数">{{ ds.spot?.rows ?? '—' }}</el-descriptions-item>
          </el-descriptions>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getOverview } from '@/api/monitor'

const jvm = ref({ heapUsedMB: 0, heapMaxMB: 0, processors: 0, uptimeMs: 0 })
const ds = ref<any>({})

const tableRows = computed(() => {
  const t = ds.value?.mysql?.tables || {}
  return Object.entries(t).map(([name, rows]) => ({ name, rows: rows as number ?? '—' }))
})

function formatUptime(ms: number) {
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h}h ${m}m`
}

async function load() {
  const o = await getOverview()
  jvm.value = o.jvm
  ds.value = o.dataService
}

onMounted(() => load())
</script>

<style scoped>
.hdr { display: flex; justify-content: space-between; align-items: center; }
h4 { margin: 0 0 8px; font-size: 14px; }
</style>
