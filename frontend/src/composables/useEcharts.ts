import { nextTick, onActivated, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import * as echarts from 'echarts'

export interface ChartTokens {
  text: string
  text2: string
  text3: string
  text4: string
  line: string
  lineStrong: string
  up: string
  down: string
  brand: string
  warn: string
  warnText: string
  surface: string
  surface2: string
  bg2: string
  series: string[]
  ma: string[]
  grid: string
  axis: string
  label: string
  font: string
}

function readTokens(): ChartTokens {
  const cs = getComputedStyle(document.documentElement)
  const v = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback
  const seq = (prefix: string, count: number, fallbacks: string[]) =>
    Array.from({ length: count }, (_, i) => v(`${prefix}-${i + 1}`, fallbacks[i]))
  return {
    text: v('--text', '#171C21'),
    text2: v('--text-2', '#434B54'),
    text3: v('--text-3', '#67707A'),
    text4: v('--text-4', '#9AA2AB'),
    line: v('--line', '#E3E6EA'),
    lineStrong: v('--line-strong', '#D2D7DD'),
    up: v('--up', '#D8402F'),
    down: v('--down', '#0E8148'),
    brand: v('--brand', '#0C7BC0'),
    warn: v('--warn', '#F0A03C'),
    warnText: v('--warn-text', '#956A00'),
    surface: v('--surface', '#FFFFFF'),
    surface2: v('--surface-2', '#F8F9FB'),
    bg2: v('--bg-2', '#EEF0F3'),
    series: seq('--chart', 6, ['#0C7BC0', '#F0A03C', '#8677D6', '#2FB99E', '#D9697F', '#7A8BA6']),
    ma: seq('--ma', 4, ['#F0A03C', '#3D8FE8', '#C255B8', '#2FB99E']),
    grid: v('--chart-grid', '#ECEFF2'),
    axis: v('--chart-axis', '#C6CCD3'),
    label: v('--chart-label', '#67707A'),
    font: 'system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
  }
}

const tokens = ref<ChartTokens | null>(null)
let watching = false

// 主题（data-theme / data-color-scheme / 系统深浅色）一变就重读 CSS 变量，
// 所有依赖 tokens 的 computed option 随之重算，图表自动换色。
function ensureThemeWatch() {
  if (watching || typeof window === 'undefined') return
  watching = true
  tokens.value = readTokens()
  const refresh = () => { tokens.value = readTokens() }
  new MutationObserver(refresh).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme', 'data-color-scheme'],
  })
  const mql = window.matchMedia('(prefers-color-scheme: dark)')
  if (typeof mql.addEventListener === 'function') mql.addEventListener('change', refresh)
  else mql.addListener(refresh)
}

export function useChartTokens(): Ref<ChartTokens> {
  ensureThemeWatch()
  return tokens as Ref<ChartTokens>
}

/** 通用 tooltip / 坐标轴样式片段，各图表按需展开。 */
export function baseTooltip(t: ChartTokens) {
  return {
    backgroundColor: t.surface,
    borderColor: t.line,
    borderWidth: 1,
    textStyle: { color: t.text, fontSize: 12 },
  }
}

export function hexToRgba(hex: string, alpha: number): string {
  const m = hex.replace('#', '')
  if (!/^[0-9a-fA-F]{3,6}$/.test(m)) return hex
  const v = m.length === 3 ? m.split('').map(c => c + c).join('') : m
  const r = parseInt(v.slice(0, 2), 16)
  const g = parseInt(v.slice(2, 4), 16)
  const b = parseInt(v.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/**
 * ECharts 生命周期封装：init / ResizeObserver 自适应 / keep-alive 切回 resize / dispose。
 * `build` 返回 option；`deps` 是一个返回依赖值的函数，变化时重绘。
 */
export function useEcharts(
  el: Ref<HTMLElement | undefined>,
  build: () => echarts.EChartsOption | null | undefined,
  deps?: () => unknown,
) {
  let chart: echarts.ECharts | null = null
  let observer: ResizeObserver | null = null

  function render() {
    if (!el.value) return
    if (!chart) chart = echarts.init(el.value)
    const option = build()
    if (option) chart.setOption(option, true)
  }

  function resize() { chart?.resize() }

  onMounted(async () => {
    await nextTick()
    render()
    if (el.value && typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => resize())
      observer.observe(el.value)
    }
  })

  onActivated(() => { nextTick(resize) })

  onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
    chart?.dispose()
    chart = null
  })

  if (deps) watch(deps, () => render(), { deep: true })

  return { render, resize, getChart: () => chart }
}
