<template>
  <component :is="isMobile ? MobileShell : DesktopShell" />
</template>

<script setup lang="ts">
import { useDevice } from '@/composables/useDevice'
import DesktopShell from './DesktopShell.vue'
import MobileShell from './MobileShell.vue'

// 按设备切换外壳；页面组件在两个壳里完全共用。
const { isMobile } = useDevice()
</script>
