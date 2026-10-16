import { createRouter, createWebHistory } from 'vue-router'
import GlobalShell from '@/views/GlobalShell.vue'
import CommandCenterView from '@/views/CommandCenterView.vue'
import AnalysisWorkspace from '@/views/AnalysisWorkspace.vue'
import BacktestLabView from '@/views/BacktestLabView.vue'
import WatchlistView from '@/views/WatchlistView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: GlobalShell,
      children: [
        {
          path: '',
          redirect: '/command-center',
        },
        {
          path: 'command-center',
          name: 'command-center',
          component: CommandCenterView,
          meta: { title: '驾驶舱 · AlphaForge' },
        },
        {
          path: 'analysis/:symbol?',
          name: 'analysis',
          component: AnalysisWorkspace,
          meta: { title: '智能分析 · AlphaForge' },
        },
        {
          path: 'backtest',
          name: 'backtest',
          component: BacktestLabView,
          meta: { title: '回测实验室 · AlphaForge' },
        },
        {
          path: 'watchlist',
          name: 'watchlist',
          component: WatchlistView,
          meta: { title: '雷达监控 · AlphaForge' },
        },
      ],
    },
  ],
})

router.afterEach((to) => {
  document.title = (to.meta.title as string | undefined) ?? 'AlphaForge'
})
