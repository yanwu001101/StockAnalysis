import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    icon?: string
    /** 不进侧栏 / 底栏（详情页） */
    hidden?: boolean
    /** 手机底栏文案 / 图标，不填则沿用 title / icon */
    mobileTitle?: string
    mobileIcon?: string
  }
}

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
        meta: { title: '盘面', icon: 'Odometer', mobileIcon: 'DataLine' },
      },
      {
        path: 'screener',
        name: 'Screener',
        component: () => import('@/views/Screener.vue'),
        meta: { title: '选股', icon: 'Search' },
      },
      {
        path: 'market',
        name: 'Market',
        component: () => import('@/views/Market.vue'),
        meta: { title: '资金', icon: 'Money' },
      },
      {
        path: 'my',
        name: 'My',
        component: () => import('@/views/My.vue'),
        meta: { title: '自选', icon: 'Star' },
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/Settings.vue'),
        meta: { title: '设置', icon: 'Setting', mobileTitle: '我的', mobileIcon: 'User' },
      },
      {
        path: 'stock/:code',
        name: 'StockDetail',
        component: () => import('@/views/StockDetail.vue'),
        meta: { title: '个股详情', icon: 'DataLine', hidden: true },
      },

      // ---- 旧路由：全部重定向到合并后的页面 / tab，保证收藏与外链可用 ----
      { path: 'conditions', redirect: { path: '/screener', query: { tab: 'condition' } } },
      { path: 'expression', redirect: { path: '/screener', query: { tab: 'expression' } } },
      { path: 'strategy', redirect: { path: '/screener', query: { tab: 'lab', sub: 'weights' } } },
      { path: 'backtest', redirect: { path: '/screener', query: { tab: 'lab', sub: 'backtest' } } },
      { path: 'moneyflow', redirect: { path: '/market' } },
      { path: 'lhb', redirect: { path: '/market', query: { tab: 'lhb' } } },
      { path: 'watchlist', redirect: { path: '/my' } },
      { path: 'portfolio', redirect: { path: '/my', query: { tab: 'portfolio' } } },
      {
        path: 'pro-signal/:code',
        redirect: to => ({ path: `/stock/${to.params.code}`, query: { tab: 'predict' } }),
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

router.beforeEach(async (to, _from, next) => {
  document.title = `${to.meta.title || 'A股智能选股'} - A股智能选股平台`

  const user = useUserStore()
  if (to.path === '/login') {
    if (user.token) {
      await user.hydrate()
      if (user.isLoggedIn) return next('/dashboard')
    }
    return next()
  }

  if (!user.token) return next('/login')
  await user.hydrate()
  if (!user.isLoggedIn) return next('/login')

  next()
})

export default router
