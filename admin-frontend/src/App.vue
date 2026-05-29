<template>
  <router-view />
</template>

<script setup lang="ts">
import { useUserStore } from '@/stores/user'

useUserStore().hydrate()
</script>

<style>
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Segoe UI', Roboto, Helvetica, sans-serif;
  background: var(--bg);
  color: var(--text);
}
</style>
