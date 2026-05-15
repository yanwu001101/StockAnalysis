import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { MarketSummary, SectorData } from '@/types'
import * as marketApi from '@/api/market'

export const useMarketStore = defineStore('market', () => {
  const summary = ref<MarketSummary | null>(null)
  const sectors = ref<SectorData[]>([])
  const northboundFlow = ref<any[]>([])
  const topStocks = ref<any[]>([])
  const loading = ref(false)

  async function fetchSummary() {
    loading.value = true
    try {
      summary.value = await marketApi.getMarketSummary()
    } finally {
      loading.value = false
    }
  }

  async function fetchSectors() {
    sectors.value = await marketApi.getSectorRotation()
  }

  async function fetchNorthboundFlow(days: number = 30) {
    northboundFlow.value = await marketApi.getNorthboundFlow(days)
  }

  async function fetchTopStocks(limit: number = 20) {
    topStocks.value = await marketApi.getTopStocks(limit)
  }

  async function fetchAll() {
    loading.value = true
    try {
      await Promise.allSettled([
        fetchSummary(),
        fetchSectors(),
        fetchNorthboundFlow(),
        fetchTopStocks(),
      ])
    } finally {
      loading.value = false
    }
  }

  return { summary, sectors, northboundFlow, topStocks, loading, fetchSummary, fetchSectors, fetchNorthboundFlow, fetchTopStocks, fetchAll }
})
