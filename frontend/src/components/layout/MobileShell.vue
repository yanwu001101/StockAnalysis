<template>
  <div class="m-shell">
    <MobileHeader :title="title" :back="isDetail" @search="searchOpen = true" />
    <main class="m-content" :class="{ 'with-tabbar': !isDetail }">
      <router-view v-slot="{ Component }">
        <keep-alive>
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
    <TabBar v-if="!isDetail" />
    <StockSearch v-if="searchOpen" variant="panel" @close="searchOpen = false" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import MobileHeader from './MobileHeader.vue'
import TabBar from './TabBar.vue'
import StockSearch from '@/components/stock/StockSearch.vue'

const route = useRoute()
const searchOpen = ref(false)

const isDetail = computed(() => !!route.meta.hidden)
const title = computed(() => String(route.meta.mobileTitle || route.meta.title || '智能选股'))
</script>

<style scoped>
.m-shell {
  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  overflow: hidden;
}
.m-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
}
.m-content.with-tabbar { padding-bottom: calc(var(--tabbar-height) + env(safe-area-inset-bottom)); }
</style>
