<template>
  <el-card shadow="never">
    <div class="hdr">
      <el-input v-model="keyword" placeholder="搜索 key / 描述" style="width:240px" clearable @keyup.enter="load" />
      <el-button @click="load">搜索</el-button>
      <div style="flex:1"></div>
      <el-button type="primary" @click="openEdit({ k: '', v: '', description: '' })">新增配置</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" style="margin-top:12px">
      <el-table-column prop="k" label="Key" width="220" />
      <el-table-column prop="v" label="Value" show-overflow-tooltip />
      <el-table-column prop="description" label="说明" show-overflow-tooltip />
      <el-table-column prop="updatedAt" label="更新时间" width="170" />
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="edit.visible" :title="edit.isNew ? '新增配置' : '编辑配置'" width="520px">
      <el-form :model="edit.form" label-position="top">
        <el-form-item label="Key">
          <el-input v-model="edit.form.k" :disabled="!edit.isNew" placeholder="例如 strategy.scoreThreshold" />
        </el-form-item>
        <el-form-item label="Value">
          <el-input v-model="edit.form.v" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="edit.form.description" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="edit.visible = false">取消</el-button>
        <el-button type="primary" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listConfigs, upsertConfig, deleteConfig, type AppConfigRow } from '@/api/configs'

const rows = ref<AppConfigRow[]>([])
const loading = ref(false)
const keyword = ref('')
const edit = reactive({
  visible: false,
  isNew: true,
  form: { k: '', v: '', description: '' },
})

async function load() {
  loading.value = true
  try {
    rows.value = await listConfigs(keyword.value || undefined)
  } finally {
    loading.value = false
  }
}

function openEdit(row: { k: string; v: string; description: string }) {
  edit.isNew = !row.k
  edit.form = { k: row.k, v: row.v, description: row.description || '' }
  edit.visible = true
}

async function onSave() {
  if (!edit.form.k) {
    ElMessage.warning('key 不能为空')
    return
  }
  await upsertConfig(edit.form.k, edit.form.v, edit.form.description)
  edit.visible = false
  ElMessage.success('已保存')
  load()
}

async function onDelete(row: AppConfigRow) {
  await ElMessageBox.confirm(`确认删除配置 ${row.k}?`, '提示', { type: 'warning' })
  await deleteConfig(row.k)
  ElMessage.success('已删除')
  load()
}

onMounted(() => load())
</script>

<style scoped>
.hdr { display: flex; gap: 8px; align-items: center; }
</style>
