<template>
  <el-card shadow="never">
    <div class="hdr">
      <el-radio-group v-model="type" @change="load">
        <el-radio-button :value="''">全部</el-radio-button>
        <el-radio-button value="whitelist">白名单</el-radio-button>
        <el-radio-button value="blacklist">黑名单</el-radio-button>
        <el-radio-button value="pool">候选池</el-radio-button>
      </el-radio-group>
      <div style="flex:1"></div>
      <el-button type="primary" @click="addDialog.visible = true">新增</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" style="margin-top:12px">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column label="类型" width="120">
        <template #default="{ row }">
          <el-tag :type="tagType(row.listType)" size="small">{{ typeLabel(row.listType) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="code" label="股票代码" width="140" />
      <el-table-column prop="note" label="备注" show-overflow-tooltip />
      <el-table-column prop="createdAt" label="添加时间" width="170" />
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="onRemove(row)">移除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="addDialog.visible" title="新增名单" width="420px">
      <el-form :model="addDialog.form" label-position="top">
        <el-form-item label="类型">
          <el-select v-model="addDialog.form.listType" style="width:100%">
            <el-option label="白名单" value="whitelist" />
            <el-option label="黑名单" value="blacklist" />
            <el-option label="候选池" value="pool" />
          </el-select>
        </el-form-item>
        <el-form-item label="股票代码">
          <el-input v-model="addDialog.form.code" placeholder="例如 600519" maxlength="10" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="addDialog.form.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="onAdd">确定</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listStockList, addStockList, removeStockList, type StockListRow } from '@/api/stockList'

const rows = ref<StockListRow[]>([])
const loading = ref(false)
const type = ref<string>('')
const addDialog = reactive({
  visible: false,
  form: { listType: 'whitelist', code: '', note: '' },
})

function tagType(t: string) {
  if (t === 'whitelist') return 'success'
  if (t === 'blacklist') return 'danger'
  return ''
}
function typeLabel(t: string) {
  return { whitelist: '白名单', blacklist: '黑名单', pool: '候选池' }[t] || t
}

async function load() {
  loading.value = true
  try {
    rows.value = await listStockList(type.value || undefined)
  } finally {
    loading.value = false
  }
}

async function onAdd() {
  if (!addDialog.form.code.trim()) {
    ElMessage.warning('请输入股票代码')
    return
  }
  await addStockList({
    listType: addDialog.form.listType,
    code: addDialog.form.code.trim(),
    note: addDialog.form.note,
  })
  ElMessage.success('已添加')
  addDialog.visible = false
  addDialog.form.code = ''
  addDialog.form.note = ''
  load()
}

async function onRemove(row: StockListRow) {
  await ElMessageBox.confirm(`确认移除 ${row.code}?`, '提示', { type: 'warning' })
  await removeStockList(row.id)
  ElMessage.success('已移除')
  load()
}

onMounted(() => load())
</script>

<style scoped>
.hdr { display: flex; gap: 8px; align-items: center; }
</style>
