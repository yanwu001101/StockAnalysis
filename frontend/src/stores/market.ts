import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { MarketSummary, SectorData } from '@/types'
import * as marketApi from '@/api/market'

export const useMarketStore = defineStore('market', () => {
  const summary = ref<MarketSummary | null>(null)
  const sectors = ref<SectorData[]>([])
  const northboundFlow = ref<any[]>([])
  const topStocks = ref<any[]>([])
  const indices = ref<any[]>([])
  const gainers = ref<any[]>([])
  const losers = ref<any[]>([])
  const mostActive = ref<any[]>([])
  const loading = ref(false)

  async function fetchSummary() {
    loading.value = true
    try {
      summary.value = await marketApi.getMarketSummary()
    } catch {
      // 保留上一次 summary，避免整页被一条失败请求打空
    } finally {
      loading.value = false
    }
  }

  async function fetchSectors() {
    try { sectors.value = await marketApi.getSectorRotation() } catch { /* keep */ }
  }

  async function fetchNorthboundFlow(days: number = 30) {
    try { northboundFlow.value = await marketApi.getNorthboundFlow(days) } catch { /* keep */ }
  }

  async function fetchTopStocks(limit: number = 20) {
    try { topStocks.value = await marketApi.getTopStocks(limit) } catch { /* keep */ }
  }

  async function fetchIndices() {
    try { indices.value = await marketApi.getIndices() } catch { /* keep */ }
  }

  async function fetchGainers(limit: number = 10) {
    try { gainers.value = await marketApi.getGainers(limit) } catch { /* keep */ }
  }

  async function fetchLosers(limit: number = 10) {
    try { losers.value = await marketApi.getLosers(limit) } catch { /* keep */ }
  }

  async function fetchMostActive(limit: number = 10) {
    try { mostActive.value = await marketApi.getMostActive(limit) } catch { /* keep */ }
  }

  async function fetchAll() {
    loading.value = true
    try {
      await Promise.allSettled([
        fetchSummary(),
        fetchSectors(),
        fetchNorthboundFlow(),
        fetchTopStocks(),
        fetchIndices(),
        fetchGainers(),
        fetchLosers(),
        fetchMostActive(),
      ])
    } finally {
      loading.value = false
    }
  }

  return {
    summary, sectors, northboundFlow, topStocks, indices, gainers, losers, mostActive, loading,
    fetchSummary, fetchSectors, fetchNorthboundFlow, fetchTopStocks,
    fetchIndices, fetchGainers, fetchLosers, fetchMostActive, fetchAll,
  }
})
