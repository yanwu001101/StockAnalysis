<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="logo">
        <el-icon :size="36" color="var(--brand)"><Setting /></el-icon>
        <h2>后台管理</h2>
        <p class="hint">仅限管理员登录</p>
      </div>
      <el-form @submit.prevent="onSubmit" :model="form" label-position="top">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="请输入密码"
            autocomplete="current-password"
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <el-button type="primary" :loading="loading" @click="onSubmit" style="width:100%">
          登录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const user = useUserStore()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

async function onSubmit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await user.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.replace('/dashboard')
  } catch (e: any) {
    ElMessage.error(e.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: var(--bg);
}
.login-card {
  width: 360px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-card);
}
.logo {
  text-align: center;
  margin-bottom: 16px;
}
.logo h2 { margin: 8px 0 4px; font-size: 18px; color: var(--text); }
.hint { color: var(--text-3); font-size: 12px; margin: 0; }
</style>
