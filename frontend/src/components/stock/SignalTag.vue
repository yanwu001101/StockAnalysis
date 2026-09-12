<template>
  <span class="sig" :class="signal || 'neutral'">{{ signalText(signal) }}</span>
</template>

<script setup lang="ts">
import { signalText } from '@/utils/score'

defineProps<{ signal?: string | null }>()
</script>

<style scoped>
.sig {
  display: inline-block;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 9px;
  border-radius: var(--radius-pill);
  line-height: 1.5;
  white-space: nowrap;
}
.sig.bullish { background: var(--up-soft); color: var(--up); }
.sig.bearish { background: var(--down-soft); color: var(--down); }
.sig.neutral { background: var(--surface-2); color: var(--text-3); }
</style>
