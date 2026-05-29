import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes: RouteRecordRaw[] = [
  { path: '/login', component: () => import('@/views/Login.vue') },
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '仪表盘' } },
      { path: 'users', component: () => import('@/views/users/UserList.vue'), meta: { title: '用户管理' } },
      { path: 'tasks', component: () => import('@/views/tasks/TaskCenter.vue'), meta: { title: '任务中心' } },
      { path: 'configs', component: () => import('@/views/configs/ConfigList.vue'), meta: { title: '通用配置' } },
      { path: 'configs/stock-list', component: () => import('@/views/configs/StockListPage.vue'), meta: { title: '股票名单' } },
      { path: 'monitor/health', component: () => import('@/views/monitor/Health.vue'), meta: { title: '健康检查' } },
      { path: 'monitor/access-log', component: () => import('@/views/monitor/AccessLog.vue'), meta: { title: '访问日志' } },
      { path: 'monitor/audit-log', component: () => import('@/views/monitor/AuditLog.vue'), meta: { title: '审计日志' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const user = useUserStore()
  if (to.path === '/login') {
    if (user.token && user.isAdmin) return '/dashboard'
    return true
  }
  if (!user.token) return '/login'
  // role 不一定立刻知道(刷新页面瞬间);allow through, AdminLayout 再做硬校验
  return true
})

export default router
