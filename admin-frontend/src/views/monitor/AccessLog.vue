<template>
  <el-card shadow="never">
    <template #header>
      <div class="hdr">
        <span>最近 {{ limit }} 条请求(进程内存,重启后清空)</span>
        <div>
          <el-input-number v-model="limit" :min="20" :max="500" :step="50" size="small" style="width:120px" />
          <el-button text @click="load" style="margin-left:8px"><el-icon><Refresh /></el-icon></el-button>
        </div>
      </div>
    </template>
    <el-table :data="rows" v-loading="loading" size="small" stripe>
      <el-table-column prop="ts" label="时间" width="180" />
      <el-table-column prop="method" label="方法" width="80" />
      <el-table-column label="路径" min-width="300">
        <template #default="{ row }">
          {{ row.uri }}<span v-if="row.query" style="color:var(--text-3)">?{{ row.query }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="elapsedMs" label="耗时(ms)" width="100">
        <template #default="{ row }">
          <span :style="{ color: row.elapsedMs >= 1000 ? 'var(--up)' : 'inherit' }">{{ row.elapsedMs }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="客户端 IP" width="160" />
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getAccessLog, type AccessLogEntry } from '@/api/monitor'

const rows = ref<AccessLogEntry[]>([])
const loading = ref(false)
const limit = ref(200)

function statusType(s: number) {
  if (s >= 500) return 'danger'
  if (s >= 400) return 'warning'
  return 'success'
}

async function load() {
  loading.value = true
  try {
    rows.value = await getAccessLog(limit.value)
  } finally {
    loading.value = false
  }
}

onMounted(() => load())
</script>

<style scoped>
.hdr { display: flex; justify-content: space-between; align-items: center; }
</style>
