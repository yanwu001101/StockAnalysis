<template>
  <AppDialog :model-value="modelValue" :title="title" width="520px" @update:model-value="$emit('update:modelValue', $event)">
    <el-form label-position="top">
      <div class="form-row">
        <el-form-item label="股票代码">
          <el-input v-model="form.code" placeholder="600519" maxlength="6" :disabled="recordMode" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="可不填" />
        </el-form-item>
      </div>

      <!-- 记录买入:只填今日买入股数与价格,服务端累加持仓、更新成本并按 T+1 锁定 -->
      <div class="form-row">
        <el-form-item label="今日买入(股)">
          <el-input-number v-model="form.todayBought" :min="0" :step="100" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="买入价">
          <el-input-number v-model="form.buyPrice" :min="0" :precision="3" :step="0.1" controls-position="right" style="width: 100%" />
        </el-form-item>
      </div>
      <p class="t1-tip">今日买入部分受 A 股 T+1 限制当日不可卖,系统不会为其生成任何卖出/做T 信号;次一交易日自动解锁。</p>

      <template v-if="!recordMode">
        <div class="form-row">
          <el-form-item label="持仓股数(总)">
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
        <div v-if="form.lastBuyDate" class="lock-line">
          最近买入日 <b class="num">{{ form.lastBuyDate }}</b>,当日锁定 <b class="num">{{ form.lockedShares }}</b> 股
          <el-button text size="small" @click="clearLock">清除锁定记录</el-button>
        </div>
        <el-form-item label="备注">
          <el-input v-model="form.notes" placeholder="例如:底仓,不轻易卖" />
        </el-form-item>
      </template>
      <template v-else>
        <p class="muted" v-if="position?.shares">已有持仓 {{ position.shares }} 股,成本 {{ position.avgCost }};保存后累加并按买入价重算成本。</p>
        <p class="muted" v-else>当前无该股持仓,保存后按今日买入建立新持仓。</p>
      </template>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
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
  todayBought: 0, buyPrice: 0, lastBuyDate: null, lockedShares: 0, clearLock: false,
})
// 决策页"记录买入"传 recordMode:只录今日买入
const recordMode = computed(() => !!props.position?.recordMode)
const title = computed(() => recordMode.value ? '记录买入' : (form.id ? '编辑持仓' : '录入持仓'))

// 每次打开时按传入的持仓回填;新增时回到默认值。
watch(() => props.modelValue, (open) => {
  if (!open) return
  const row = props.position
  Object.assign(form, {
    id: row?.id,
    code: row?.code || '',
    name: row?.name || '',
    shares: Number(row?.shares || (row?.recordMode ? 0 : 100)),
    availableShares: Number(row?.availableShares || row?.shares || 100),
    avgCost: Number(row?.avgCost || 0),
    targetWeight: Number(row?.targetWeight || 20),
    notes: row?.notes || '',
    todayBought: Number(row?.todayBought || 0),
    buyPrice: Number(row?.buyPrice || 0),
    lastBuyDate: row?.lastBuyDate || null,
    lockedShares: Number(row?.lockedToday || row?.lockedShares || 0),
    clearLock: false,
  })
})

function clearLock() {
  form.lastBuyDate = null
  form.lockedShares = 0
  form.clearLock = true
}

async function save() {
  if (!/^\d{6}$/.test(String(form.code).trim())) {
    ElMessage.warning('请输入 6 位股票代码')
    return
  }
  const body: Record<string, any> = { code: String(form.code).trim(), name: form.name }
  if (recordMode.value) {
    if (!form.todayBought || form.todayBought <= 0) { ElMessage.warning('请填写今日买入股数'); return }
    body.todayBought = form.todayBought
    body.buyPrice = form.buyPrice
    // 新建持仓时服务端要求 shares/avgCost > 0:用今日买入量与买入价兜底
    body.shares = form.todayBought
    body.avgCost = form.buyPrice || form.avgCost
  } else {
    Object.assign(body, {
      id: form.id, shares: form.shares, availableShares: form.availableShares, avgCost: form.avgCost,
      targetWeight: form.targetWeight, notes: form.notes,
    })
    if (form.todayBought > 0) { body.todayBought = form.todayBought; body.buyPrice = form.buyPrice; body.sharesIsTotal = true }
    else if (form.clearLock) { body.lastBuyDate = ''; body.lockedShares = 0 }
  }
  saving.value = true
  try {
    await portfolioApi.savePortfolioPosition(body as any)
    ElMessage.success(recordMode.value ? '已记录买入,今日买入部分 T+1 锁定' : '持仓已保存')
    emit('update:modelValue', false)
    emit('saved')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.t1-tip { font-size: 12px; color: var(--text-3); margin: -6px 0 12px; line-height: 1.6; }
.lock-line { font-size: 12px; color: var(--text-2); margin-bottom: 10px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.lock-line b { color: var(--text); }
.muted { font-size: 12px; color: var(--text-3); }
@media (max-width: 768px) { .form-row { grid-template-columns: 1fr; gap: 0; } }
</style>
