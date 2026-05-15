import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/components/layout/AppLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '仪表盘', icon: 'Odometer' },
      },
      {
        path: 'screener',
        name: 'Screener',
        component: () => import('@/views/Screener.vue'),
        meta: { title: '智能选股', icon: 'Search' },
      },
      {
        path: 'stock/:code',
        name: 'StockDetail',
        component: () => import('@/views/StockDetail.vue'),
        meta: { title: '个股详情', icon: 'DataLine', hidden: true },
      },
      {
        path: 'strategy',
        name: 'StrategyLab',
        component: () => import('@/views/StrategyLab.vue'),
        meta: { title: '策略实验室', icon: 'SetUp' },
      },
      {
        path: 'watchlist',
        name: 'Watchlist',
        component: () => import('@/views/Watchlist.vue'),
        meta: { title: '自选股', icon: 'Star' },
      },
      {
        path: 'backtest',
        name: 'Backtest',
        component: () => import('@/views/Backtest.vue'),
        meta: { title: '策略回测', icon: 'TrendCharts' },
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/Settings.vue'),
        meta: { title: '设置', icon: 'Setting' },
      },
    ],
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  document.title = `${to.meta.title || 'A股智能选股'} - A股智能选股平台`
  next()
})

export default router
