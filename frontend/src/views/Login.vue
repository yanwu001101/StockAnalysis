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

      <div class="seg">
        <button :class="['seg-btn', { active: mode === 'login' }]" @click="mode = 'login'">登 录</button>
        <button :class="['seg-btn', { active: mode === 'register' }]" @click="mode = 'register'">注 册</button>
      </div>

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

        <button type="submit" class="submit" :disabled="loading">
          {{ loading ? '处理中…' : (mode === 'login' ? '登 录' : '注 册') }}
        </button>
      </form>

      <div class="foot">
        <button class="link" @click="$router.push('/dashboard')">先以访客身份进入 →</button>
      </div>
    </div>

    <div class="footer-meta">© {{ new Date().getFullYear() }} 智能选股</div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { register } from '@/api/user'

const router = useRouter()
const userStore = useUserStore()

const mode = ref<'login' | 'register'>('login')
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
  color: #FFFFFF;
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

.seg {
  display: flex;
  background: var(--bg-2);
  border-radius: 10px;
  padding: 4px;
  margin-bottom: 18px;
}
.seg-btn {
  flex: 1;
  background: transparent;
  border: 0;
  padding: 9px 0;
  border-radius: 8px;
  color: var(--text-3);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  letter-spacing: 0.04em;
  transition: background 0.18s ease, color 0.18s ease;
}
.seg-btn.active {
  background: var(--surface);
  color: var(--text);
  box-shadow: var(--shadow-card);
}

.form { display: flex; flex-direction: column; gap: 14px; }
.field { width: 100%; }

.submit {
  width: 100%;
  margin-top: 4px;
  background: var(--brand);
  color: #FFFFFF;
  border: 0;
  border-radius: var(--radius);
  padding: 13px 0;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  letter-spacing: 0.05em;
  transition: background 0.15s ease;
}
.submit:hover:not(:disabled) { background: var(--brand-press); }
.submit:disabled { opacity: 0.6; cursor: wait; }

.foot {
  margin-top: 18px;
  text-align: center;
}
.link {
  background: transparent;
  border: 0;
  color: var(--text-3);
  font-size: 13px;
  cursor: pointer;
}
.link:hover { color: var(--brand); }

.footer-meta {
  margin-top: 24px;
  font-size: 12px;
  color: var(--text-4);
}
</style>
