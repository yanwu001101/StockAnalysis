<template>
  <AppDialog :model-value="modelValue" title="导入持仓" width="680px" @update:model-value="$emit('update:modelValue', $event)">
    <el-alert
      class="import-alert"
      type="info"
      :closable="false"
      show-icon
      title="从同花顺或券商客户端复制持仓表，粘贴后即可同步到本地持仓；这里不会要求输入交易密码。"
    />
    <el-form label-position="top">
      <el-form-item label="持仓表内容">
        <el-input v-model="text" type="textarea" :rows="8" :placeholder="example" />
      </el-form-item>
      <el-form-item label="默认目标仓位%">
        <el-input-number v-model="targetWeight" :min="1" :max="100" :step="5" controls-position="right" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="importing" @click="doImport">导入并生成建议</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as portfolioApi from '@/api/portfolio'
import AppDialog from '@/components/ui/AppDialog.vue'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'imported'): void
}>()

const text = ref('')
const targetWeight = ref(20)
const importing = ref(false)
const example = '股票代码\t股票名称\t持仓数量\t可用数量\t成本价\n600519\t贵州茅台\t100\t100\t1688.50'

async function doImport() {
  if (!text.value.trim()) {
    ElMessage.warning('请先粘贴同花顺或券商导出的持仓表内容')
    return
  }
  importing.value = true
  try {
    const result = await portfolioApi.importPortfolioText({
      text: text.value,
      targetWeight: targetWeight.value,
      source: 'ths_export',
    })
    const imported = Number(result?.imported || 0)
    const skipped = Number(result?.skipped || 0)
    ElMessage.success(skipped ? `已导入 ${imported} 条，跳过 ${skipped} 条` : `已导入 ${imported} 条持仓`)
    text.value = ''
    emit('update:modelValue', false)
    emit('imported')
  } finally {
    importing.value = false
  }
}
</script>

<style scoped>
.import-alert { margin-bottom: 14px; }
</style>
