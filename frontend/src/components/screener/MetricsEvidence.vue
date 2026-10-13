<template><div class="metric-evidence" :class="{ warning: evidence?.status !== 'VALID' }" role="status"><p v-for="line in lines" :key="line">{{ line }}</p></div></template>
<script setup lang="ts">
import { computed } from 'vue'
import type { MetricsEvidence } from '@/types'
import { evidenceLines } from '@/utils/metricEvidence'
const props = defineProps<{ evidence?: MetricsEvidence | null }>()
const lines = computed(() => evidenceLines(props.evidence))
</script>
<style scoped>
.metric-evidence { font-size:12px; color:var(--text-3); line-height:1.6; overflow-wrap:anywhere; }
.metric-evidence.warning { color:var(--warn-text); }
.metric-evidence p { margin:6px 0; }
</style>
