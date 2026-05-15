<template>
  <div class="page-container">
    <div class="settings-card glass-card">
      <h2>设置</h2>
      <el-form label-position="top" size="default">
        <el-divider content-position="left">外观</el-divider>
        <el-form-item label="主题模式">
          <el-switch v-model="isDark" active-text="暗色" inactive-text="亮色" @change="toggleTheme" />
        </el-form-item>

        <el-divider content-position="left">数据</el-divider>
        <el-form-item label="行情刷新间隔 (秒)">
          <el-input-number v-model="refreshInterval" :min="5" :max="60" :step="5" />
        </el-form-item>
        <el-form-item label="默认选股数量">
          <el-input-number v-model="defaultLimit" :min="10" :max="200" :step="10" />
        </el-form-item>

        <el-divider content-position="left">账户</el-divider>
        <el-form-item>
          <el-button type="danger" plain @click="handleLogout">退出登录</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const isDark = ref(true)
const refreshInterval = ref(15)
const defaultLimit = ref(80)

function toggleTheme(dark: boolean) {
  document.documentElement.classList.toggle('dark', dark)
}

function handleLogout() {
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.settings-card {
  max-width: 600px;
  padding: 32px;
}
.settings-card h2 {
  margin: 0 0 24px;
  font-size: 20px;
  color: var(--text-primary);
}
</style>
