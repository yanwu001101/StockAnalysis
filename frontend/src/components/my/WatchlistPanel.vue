<template>
  <div class="watchlist-panel">
    <AppCard title="我的自选股">
      <template #actions>
        <el-input v-model="addCode" placeholder="输入代码添加" size="small" class="add-input" maxlength="6" @keyup.enter="addStock">
          <template #append>
            <el-button @click="addStock"><el-icon><Plus /></el-icon></el-button>
          </template>
        </el-input>
        <el-button size="small" @click="showGroupDialog = true">
          <el-icon><FolderAdd /></el-icon>新建分组
        </el-button>
      </template>

      <SegmentTabs v-if="groups.length > 1" v-model="activeGroup" :options="groupOptions" small class="group-tabs" />

      <StockTable :rows="currentStocks" :columns="columns" rank empty="暂无自选股，输入代码添加" actions-label="">
        <template #cell-t="{ row }">
          <el-tooltip v-if="tOf(row.code) && tOf(row.code).action !== 'no_data' && tOf(row.code).action !== 'wait'"
                      :content="(tOf(row.code).reasons || []).join('；')" placement="top" :show-after="200">
            <el-tag :type="tOf(row.code).action === 'positive_t' ? 'danger' : 'success'" size="small" effect="plain">
              {{ tOf(row.code).action_label }} · {{ tOf(row.code).strength }}
            </el-tag>
          </el-tooltip>
          <span v-else class="dim">—</span>
        </template>
        <template #actions="{ row }">
          <el-button type="danger" text size="small" @click.stop="removeStock(row.code)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </StockTable>
    </AppCard>

    <AppDialog v-model="showGroupDialog" title="新建分组" width="400px">
      <el-input v-model="newGroupName" placeholder="分组名称" />
      <template #footer>
        <el-button @click="showGroupDialog = false">取消</el-button>
        <el-button type="primary" @click="createGroup">创建</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useRefreshable } from '@/composables/useRefreshable'
import { useWatchlist } from '@/composables/useWatchlist'
import * as userApi from '@/api/user'
import { getTSignalBatch } from '@/api/t'
import { padCode } from '@/utils/score'
import type { StockColumn, SegmentOption } from '@/types/ui'
import AppCard from '@/components/ui/AppCard.vue'
import AppDialog from '@/components/ui/AppDialog.vue'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import StockTable from '@/components/stock/StockTable.vue'

const userStore = useUserStore()
const wl = useWatchlist()
const addCode = ref('')
const activeGroup = ref('')
const showGroupDialog = ref(false)
const newGroupName = ref('')

const groups = computed(() => userStore.watchlists || [])
const groupOptions = computed<SegmentOption<string>[]>(() => groups.value.map(g => ({ label: g.name, value: String(g.id) })))
const currentGroupId = computed(() => Number(activeGroup.value) || groups.value[0]?.id)
const currentStocks = computed(() => {
  const g = groups.value.find(g => String(g.id) === activeGroup.value)
  return g?.stocks || groups.value[0]?.stocks || []
})

const columns: StockColumn[] = [
  { key: 'price', label: '最新价', type: 'price' },
  { key: 'changePercent', label: '涨跌幅', type: 'change' },
  { key: 'compositeScore', label: '综合分', type: 'score', align: 'center' },
  { key: 't', label: '做T', align: 'center' },
]

async function addStock() {
  const code = addCode.value.trim()
  if (!code) return
  if (!currentGroupId.value) { ElMessage.warning('请先创建分组'); return }
  try {
    await wl.add(code, currentGroupId.value)
    addCode.value = ''
  } catch {}
}

async function removeStock(code: string) {
  if (!currentGroupId.value) return
  try { await wl.remove(code, currentGroupId.value) } catch {}
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

const tMap = ref<Record<string, any>>({})
function tOf(code: any) { return tMap.value[padCode(code)] }
async function loadTSignals() {
  const codes = (currentStocks.value || []).map((s: any) => padCode(s.code))
  if (!codes.length) { tMap.value = {}; return }
  try {
    const res = await getTSignalBatch(codes)
    const m: Record<string, any> = {}
    res.forEach((r: any) => { m[r.code] = r })
    tMap.value = m
  } catch { tMap.value = {} }
}
watch(currentStocks, loadTSignals, { immediate: true })

useRefreshable('自选股', reloadWatchlists)
</script>

<style scoped>
.add-input { width: 170px; }
.group-tabs { margin-bottom: 12px; }
.dim { color: var(--text-4); }
@media (max-width: 768px) {
  .add-input { width: 150px; }
}
</style>
