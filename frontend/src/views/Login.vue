<template>
  <div class="login-page">
    <div class="login-card rise rise-1">
      <div class="brand">
        <div class="brand-mark">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="3 17 9 11 13 15 21 7"></polyline>
            <polyline points="14 7 21 7 21 14"></polyline>
          </svg>
        </div>
        <div class="brand-text">
          <div class="brand-name">智能选股</div>
          <div class="brand-sub">A 股 · 因子量化 · 策略回测</div>
        </div>
      </div>

      <SegmentTabs v-model="mode" :options="modeOptions" block class="mode-tabs" />

      <form @submit.prevent="handleSubmit" class="form">
        <div class="field">
          <el-input v-model="form.username" placeholder="账号" size="large">
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </div>
        <div v-if="mode === 'register'" class="field">
          <el-input v-model="form.nickname" placeholder="昵称" size="large">
            <template #prefix><el-icon><UserFilled /></el-icon></template>
          </el-input>
        </div>
        <div class="field">
          <el-input v-model="form.password" type="password" placeholder="密码" show-password size="large">
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </div>

        <el-button type="primary" size="large" native-type="submit" class="submit" :loading="loading">
          {{ mode === 'login' ? '登录' : '注册' }}
        </el-button>
      </form>

    </div>

    <div class="footer-meta">© {{ new Date().getFullYear() }} 智能选股</div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, UserFilled, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { register } from '@/api/user'
import SegmentTabs from '@/components/ui/SegmentTabs.vue'
import type { SegmentOption } from '@/types/ui'

const router = useRouter()
const userStore = useUserStore()

const mode = ref<'login' | 'register'>('login')
const modeOptions: SegmentOption<'login' | 'register'>[] = [
  { label: '登录', value: 'login' },
  { label: '注册', value: 'register' },
]
const loading = ref(false)
const form = reactive({ username: '', password: '', nickname: '' })

async function handleSubmit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请填写账号和密码')
    return
  }
  loading.value = true
  try {
    if (mode.value === 'login') {
      await userStore.login(form.username, form.password)
      ElMessage.success('登录成功')
      router.push('/dashboard')
    } else {
      await register(form.username, form.password, form.nickname || form.username)
      ElMessage.success('注册成功，请登录')
      mode.value = 'login'
    }
  } catch {} finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  background: var(--bg);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.login-card {
  width: 100%;
  max-width: 380px;
  background: var(--surface);
  border-radius: var(--radius-lg);
  padding: 32px 28px;
  box-shadow: var(--shadow-card);
}
.brand {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 28px;
}
.brand-mark {
  width: 44px; height: 44px;
  border-radius: 12px;
  background: var(--brand);
  color: var(--on-brand);
  display: flex; align-items: center; justify-content: center;
}
.brand-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.2;
}
.brand-sub {
  font-size: 12px;
  color: var(--text-3);
  margin-top: 3px;
}

.mode-tabs { margin-bottom: 18px; }

.form { display: flex; flex-direction: column; gap: 14px; }
.field { width: 100%; }

.submit {
  width: 100%;
  margin-top: 4px;
  letter-spacing: 0.05em;
}

.footer-meta {
  margin-top: 24px;
  font-size: 12px;
  color: var(--text-4);
}
</style>
