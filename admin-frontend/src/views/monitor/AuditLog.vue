<template>
  <el-card shadow="never">
    <template #header>
      <div class="hdr">
        <div>
          <el-input
            v-model="actionFilter"
            placeholder="按 action 过滤,例如 USER_RESET_PASSWORD"
            style="width:280px"
            clearable
            @keyup.enter="load(1)"
          />
          <el-button @click="load(1)" style="margin-left:8px">搜索</el-button>
        </div>
        <el-button text @click="load()"><el-icon><Refresh /></el-icon></el-button>
      </div>
    </template>
    <el-table :data="rows" v-loading="loading" size="small">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="createdAt" label="时间" width="170" />
      <el-table-column prop="adminName" label="操作人" width="120" />
      <el-table-column label="动作" width="180">
        <template #default="{ row }">
          <el-tag size="small">{{ row.action }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="target" label="目标" width="220" />
      <el-table-column prop="payloadJson" label="参数" show-overflow-tooltip />
      <el-table-column prop="ip" label="IP" width="140" />
    </el-table>
    <el-pagination
      v-model:current-page="page.current"
      v-model:page-size="page.size"
      :total="page.total"
      :page-sizes="[20, 50, 100]"
      layout="total, sizes, prev, pager, next"
      style="margin-top:12px"
      @current-change="load()"
      @size-change="load()"
    />
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { getAuditLog, type AuditLogRow } from '@/api/monitor'

const rows = ref<AuditLogRow[]>([])
const loading = ref(false)
const actionFilter = ref('')
const page = reactive({ current: 1, size: 30, total: 0 })

async function load(p?: number) {
  if (p) page.current = p
  loading.value = true
  try {
    const res = await getAuditLog({
      page: page.current,
      size: page.size,
      action: actionFilter.value || undefined,
    })
    rows.value = res.records
    page.total = res.total
  } finally {
    loading.value = false
  }
}

onMounted(() => load())
</script>

<style scoped>
.hdr { display: flex; justify-content: space-between; align-items: center; }
</style>
