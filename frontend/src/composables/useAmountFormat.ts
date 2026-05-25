import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useSettingsStore } from '@/stores/settings'
import { formatAmount, formatAmountText, type AmountUnit } from '@/utils/format'

/**
 * Reactive amount formatter that respects the user's amountUnit preference.
 *
 * Usage:
 *   const { format, formatText, unit } = useAmountFormat()
 *   const { value, suffix } = format(1234567890)   // → { value: '12.35', suffix: '亿' }
 *   const text = formatText(1234567890)             // → '12.35 亿'
 */
export function useAmountFormat() {
  const settings = useSettingsStore()
  const { amountUnit } = storeToRefs(settings)

  const unit = computed<AmountUnit>(() => amountUnit.value)

  function format(v: number | null | undefined, decimals = 2) {
    return formatAmount(v, unit.value, decimals)
  }
  function formatText(v: number | null | undefined, decimals = 2) {
    return formatAmountText(v, unit.value, decimals)
  }

  const suffixLabel = computed(() => (unit.value === 'yi' ? '亿' : '万'))

  return { format, formatText, unit, suffixLabel }
}
