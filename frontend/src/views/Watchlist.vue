<template>
  <div class="page-container">
    <div class="watchlist-header glass-card">
      <h2>我的自选股</h2>
      <div class="header-actions">
        <el-input v-model="addCode" placeholder="输入股票代码添加" size="small" style="width: 200px;" @keyup.enter="addStock">
          <template #append>
            <el-button @click="addStock"><el-icon><Plus /></el-icon></el-button>
          </template>
        </el-input>
        <el-button size="small" @click="showGroupDialog = true">
          <el-icon><FolderAdd /></el-icon>新建分组
        </el-button>
      </div>
    </div>

    <div class="group-tabs" v-if="groups.length > 1">
      <el-tabs v-model="activeGroup" type="card">
        <el-tab-pane v-for="g in groups" :key="g.id" :label="g.name" :name="String(g.id)" />
      </el-tabs>
    </div>

    <div class="glass-card stock-table-card">
      <el-table :data="currentStocks" stripe @row-click="$router.push(`/stock/${$event.code}`)" :row-style="{ cursor: 'pointer' }" size="small" empty-description="暂无自选股">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="name" label="名称" width="100">
          <template #default="{ row }"><span class="stock-name">{{ row.name }}</span></template>
        </el-table-column>
        <el-table-column prop="code" label="代码" width="80" />
        <el-table-column prop="industry" label="行业" width="100" />
        <el-table-column prop="price" label="最新价" width="80" align="right">
          <template #default="{ row }">
            <span :class="row.changePercent >= 0 ? 'price-up' : 'price-down'">{{ row.price }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="changePercent" label="涨跌幅" width="80" align="right">
          <template #default="{ row }">
            <span :class="row.changePercent >= 0 ? 'price-up' : 'price-down'">
              {{ row.changePercent >= 0 ? '+' : '' }}{{ row.changePercent }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="compositeScore" label="综合分" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.compositeScore >= 80 ? 'success' : row.compositeScore >= 60 ? 'warning' : 'danger'" size="small" effect="dark">
              {{ row.compositeScore ?? '--' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click.stop="removeStock(row.code)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="showGroupDialog" title="新建分组" width="400px">
      <el-input v-model="newGroupName" placeholder="分组名称" />
      <template #footer>
        <el-button @click="showGroupDialog = false">取消</el-button>
        <el-button type="primary" @click="createGroup">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useRefreshable } from '@/composables/useRefreshable'
import * as userApi from '@/api/user'

const userStore = useUserStore()
const addCode = ref('')
const activeGroup = ref('')
const showGroupDialog = ref(false)
const newGroupName = ref('')

const groups = computed(() => userStore.watchlists || [])
const currentStocks = computed(() => {
  const g = groups.value.find(g => String(g.id) === activeGroup.value)
  return g?.stocks || groups.value[0]?.stocks || []
})

async function addStock() {
  if (!addCode.value.trim()) return
  const gid = Number(activeGroup.value) || groups.value[0]?.id
  if (!gid) { ElMessage.warning('请先创建分组'); return }
  try {
    await userApi.addToWatchlist(gid, addCode.value.trim())
    ElMessage.success('添加成功')
    addCode.value = ''
    await userStore.fetchWatchlists()
  } catch {}
}

async function removeStock(code: string) {
  const gid = Number(activeGroup.value) || groups.value[0]?.id
  if (!gid) return
  try {
    await userApi.removeFromWatchlist(gid, code)
    ElMessage.success('已移除')
    await userStore.fetchWatchlists()
  } catch {}
}

async function createGroup() {
  if (!newGroupName.value.trim()) return
  try {
    await userApi.createWatchlist(newGroupName.value.trim())
    showGroupDialog.value = false
    newGroupName.value = ''
    await userStore.fetchWatchlists()
    ElMessage.success('分组已创建')
  } catch {}
}

async function reloadWatchlists() {
  if (!userStore.isLoggedIn) return
  await userStore.fetchWatchlists()
  if (groups.value.length && !activeGroup.value) {
    activeGroup.value = String(groups.value[0].id)
  }
}

useRefreshable('自选股', reloadWatchlists)
</script>

<style scoped>
.watchlist-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  margin-bottom: 16px;
}
.watchlist-header h2 { margin: 0; font-size: 20px; color: var(--text-primary); }
.header-actions { display: flex; gap: 12px; }
.group-tabs { margin-bottom: 16px; }
.stock-table-card { padding: 16px; }
.stock-name { font-weight: 600; color: var(--text-primary); }
</style>
