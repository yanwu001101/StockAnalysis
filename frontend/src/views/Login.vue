<template>
  <div class="login-page">
    <div class="login-card glass-card">
      <div class="login-header">
        <div class="logo-icon">
          <el-icon :size="36" color="#00D4FF"><TrendCharts /></el-icon>
        </div>
        <h1>A股智能选股平台</h1>
        <p class="subtitle">十大策略 · 智能选股 · 回测验证</p>
      </div>

      <el-tabs v-model="mode" class="login-tabs">
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>

      <el-form :model="form" size="large" @submit.prevent="handleSubmit">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" prefix-icon="User" />
        </el-form-item>
        <el-form-item v-if="mode === 'register'">
          <el-input v-model="form.nickname" placeholder="昵称" prefix-icon="UserFilled" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleSubmit" style="width: 100%;">
            {{ mode === 'login' ? '登录' : '注册' }}
          </el-button>
        </el-form-item>
      </el-form>

      <div class="skip-login">
        <el-button text type="primary" @click="$router.push('/dashboard')">先逛逛，不登录</el-button>
      </div>
    </div>
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

const mode = ref('login')
const loading = ref(false)
const form = reactive({ username: '', password: '', nickname: '' })

async function handleSubmit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  loading.value = true
  try {
    if (mode.value === 'login') {
      await userStore.login(form.username, form.password)
      ElMessage.success('登录成功')
    } else {
      await register(form.username, form.password, form.nickname || form.username)
      ElMessage.success('注册成功，请登录')
      mode.value = 'login'
      return
    }
    router.push('/dashboard')
  } catch {} finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  background: var(--bg-primary);
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-card {
  width: 400px;
  padding: 40px;
}
.login-header {
  text-align: center;
  margin-bottom: 24px;
}
.logo-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  background: rgba(0, 212, 255, 0.1);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-header h1 {
  margin: 0;
  font-size: 22px;
  color: var(--accent-cyan);
  text-shadow: 0 0 15px rgba(0, 212, 255, 0.3);
}
.subtitle {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--text-muted);
}
.login-tabs {
  margin-bottom: 16px;
}
.skip-login {
  text-align: center;
  margin-top: 8px;
}
</style>
