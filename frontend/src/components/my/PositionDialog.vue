<template>
  <AppDialog :model-value="modelValue" :title="form.id ? '编辑持仓' : '录入持仓'" width="520px" @update:model-value="$emit('update:modelValue', $event)">
    <el-form label-position="top">
      <div class="form-row">
        <el-form-item label="股票代码">
          <el-input v-model="form.code" placeholder="600519" maxlength="6" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="可不填" />
        </el-form-item>
      </div>
      <div class="form-row">
        <el-form-item label="持仓股数">
          <el-input-number v-model="form.shares" :min="0" :step="100" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="可用股数">
          <el-input-number v-model="form.availableShares" :min="0" :step="100" controls-position="right" style="width: 100%" />
        </el-form-item>
      </div>
      <div class="form-row">
        <el-form-item label="成本价">
          <el-input-number v-model="form.avgCost" :min="0" :precision="3" :step="0.1" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="目标仓位%">
          <el-input-number v-model="form.targetWeight" :min="1" :max="100" :step="5" controls-position="right" style="width: 100%" />
        </el-form-item>
      </div>
      <el-form-item label="备注">
        <el-input v-model="form.notes" placeholder="例如：底仓，不轻易卖" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as portfolioApi from '@/api/portfolio'
import AppDialog from '@/components/ui/AppDialog.vue'

const props = defineProps<{ modelValue: boolean; position?: any | null }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'saved'): void
}>()

const saving = ref(false)
const form = reactive<any>({
  id: undefined, code: '', name: '', shares: 100, availableShares: 100, avgCost: 0, targetWeight: 20, notes: '',
})

// 每次打开时按传入的持仓回填；新增时回到默认值。
watch(() => props.modelValue, (open) => {
  if (!open) return
  const row = props.position
  Object.assign(form, {
    id: row?.id,
    code: row?.code || '',
    name: row?.name || '',
    shares: Number(row?.shares || 100),
    availableShares: Number(row?.availableShares || row?.shares || 100),
    avgCost: Number(row?.avgCost || 0),
    targetWeight: Number(row?.targetWeight || 20),
    notes: row?.notes || '',
  })
})

async function save() {
  if (!/^\d{6}$/.test(String(form.code).trim())) {
    ElMessage.warning('请输入 6 位股票代码')
    return
  }
  saving.value = true
  try {
    await portfolioApi.savePortfolioPosition({ ...form, code: String(form.code).trim() })
    ElMessage.success('持仓已保存')
    emit('update:modelValue', false)
    emit('saved')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 768px) { .form-row { grid-template-columns: 1fr; gap: 0; } }
</style>
