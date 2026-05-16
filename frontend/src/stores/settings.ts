import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useSettingsStore = defineStore('settings', () => {
  const isDark = ref(localStorage.getItem('isDark') === '1')
  const refreshInterval = ref(Number(localStorage.getItem('refreshInterval')) || 15)
  const defaultLimit = ref(Number(localStorage.getItem('defaultLimit')) || 80)

  watch(isDark, v => {
    localStorage.setItem('isDark', v ? '1' : '0')
    document.documentElement.classList.toggle('dark', v)
  })
  watch(refreshInterval, v => localStorage.setItem('refreshInterval', String(v)))
  watch(defaultLimit, v => localStorage.setItem('defaultLimit', String(v)))

  document.documentElement.classList.toggle('dark', isDark.value)

  return { isDark, refreshInterval, defaultLimit }
})
