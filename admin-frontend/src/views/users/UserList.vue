<template>
  <div>
    <el-card shadow="never">
      <div class="filter">
        <el-input
          v-model="filter.keyword"
          placeholder="搜索用户名/昵称"
          style="width:240px"
          clearable
          @keyup.enter="load(1)"
        />
        <el-select v-model="filter.role" placeholder="角色" clearable style="width:120px">
          <el-option label="ADMIN" value="ADMIN" />
          <el-option label="USER" value="USER" />
        </el-select>
        <el-select v-model="filter.status" placeholder="状态" clearable style="width:120px">
          <el-option label="启用" :value="1" />
          <el-option label="禁用" :value="0" />
        </el-select>
        <el-button type="primary" @click="load(1)">搜索</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" style="margin-top:12px">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="nickname" label="昵称" />
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'ADMIN' ? 'success' : ''" size="small">{{ row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? '' : 'danger'" size="small">
              {{ row.status === 1 ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="lastLoginAt" label="最近登录" width="170">
          <template #default="{ row }">{{ row.lastLoginAt || '—' }}</template>
        </el-table-column>
        <el-table-column prop="createdAt" label="注册时间" width="170" />
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="onToggle(row)">
              {{ row.status === 1 ? '禁用' : '启用' }}
            </el-button>
            <el-button
              size="small"
              :type="row.role === 'ADMIN' ? '' : 'success'"
              @click="onSetRole(row)"
            >
              {{ row.role === 'ADMIN' ? '降为 USER' : '升为 ADMIN' }}
            </el-button>
            <el-button size="small" type="warning" @click="onReset(row)">重置密码</el-button>
            <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page.current"
        v-model:page-size="page.size"
        :total="page.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        style="margin-top:12px"
        @current-change="load()"
        @size-change="load()"
      />
    </el-card>

    <!-- 临时密码弹框 -->
    <el-dialog v-model="resetDialog.visible" title="临时密码" width="420px" :close-on-click-modal="false">
      <p>已为用户 <strong>{{ resetDialog.username }}</strong> 重置密码。请将以下临时密码转告给该用户,**此密码只显示一次**。用户下次登录后需立即修改密码。</p>
      <el-input v-model="resetDialog.password" readonly style="margin-top:12px">
        <template #append>
          <el-button @click="copyPassword">复制</el-button>
        </template>
      </el-input>
      <template #footer>
        <el-button type="primary" @click="resetDialog.visible = false">我已记下</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listUsers, toggleUserStatus, setUserRole, resetUserPassword, deleteUser,
  type AdminUserRow,
} from '@/api/users'

const rows = ref<AdminUserRow[]>([])
const loading = ref(false)
const filter = reactive({ keyword: '', role: '', status: undefined as undefined | number })
const page = reactive({ current: 1, size: 20, total: 0 })
const resetDialog = reactive({ visible: false, username: '', password: '' })

async function load(p?: number) {
  if (p) page.current = p
  loading.value = true
  try {
    const res = await listUsers({
      page: page.current,
      size: page.size,
      keyword: filter.keyword || undefined,
      role: filter.role || undefined,
      status: filter.status,
    })
    rows.value = res.records
    page.total = res.total
  } finally {
    loading.value = false
  }
}

function reset() {
  filter.keyword = ''
  filter.role = ''
  filter.status = undefined
  load(1)
}

async function onToggle(row: AdminUserRow) {
  await toggleUserStatus(row.id)
  ElMessage.success('已更新状态')
  load()
}

async function onSetRole(row: AdminUserRow) {
  const next = row.role === 'ADMIN' ? 'USER' : 'ADMIN'
  await ElMessageBox.confirm(`确认将 ${row.username} 改为 ${next}?`, '提示', { type: 'warning' })
  await setUserRole(row.id, next)
  ElMessage.success('角色已更新')
  load()
}

async function onReset(row: AdminUserRow) {
  await ElMessageBox.confirm(`确认重置 ${row.username} 的密码?`, '提示', { type: 'warning' })
  const r = await resetUserPassword(row.id)
  resetDialog.username = r.username
  resetDialog.password = r.tempPassword
  resetDialog.visible = true
  load()
}

async function onDelete(row: AdminUserRow) {
  await ElMessageBox.confirm(`确认删除 ${row.username}? 软删除,可在数据库手动恢复。`, '危险操作', { type: 'error' })
  await deleteUser(row.id)
  ElMessage.success('已删除')
  load()
}

async function copyPassword() {
  try {
    await navigator.clipboard.writeText(resetDialog.password)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败,请手动选中复制')
  }
}

onMounted(() => load())
</script>

<style scoped>
.filter { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
