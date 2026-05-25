<template>
  <router-view />
</template>

<script setup lang="ts">
import { useSettingsStore } from '@/stores/settings'
import { useUserStore } from '@/stores/user'

// Touch the store at the root so colorScheme / amountUnit / klineAdjust are
// hydrated from localStorage on app boot, before any view mounts. The store's
// internal watch handles future updates; we just need to trigger initialisation.
useSettingsStore()

// Rehydrate user session: token persists across reloads in localStorage, but
// userInfo lives only in memory and would otherwise be null until the user
// logs in again — leading to the header avatar falling back to "U" and the
// app looking half-logged-in.
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
