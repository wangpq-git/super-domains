import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue')
      },
      {
        path: 'domains',
        name: 'Domains',
        component: () => import('@/views/Domains.vue')
      },
      {
        path: 'accounts',
        name: 'Accounts',
        component: () => import('@/views/Accounts.vue')
      },
      {
        path: 'dns',
        name: 'DnsManage',
        component: () => import('@/views/DnsManage.vue')
      },
      {
        path: 'change-requests',
        name: 'ChangeRequests',
        component: () => import('@/views/ChangeRequests.vue')
      },
      {
        path: 'alerts',
        name: 'Alerts',
        component: () => import('@/views/Alerts.vue')
      },
      {
        path: 'service-discovery',
        name: 'ServiceDiscovery',
        component: () => import('@/views/ServiceDiscovery.vue')
      },
      {
        path: 'cos-discovery',
        name: 'CosDiscovery',
        component: () => import('@/views/CosDiscovery.vue')
      },
      {
        path: 'system-settings',
        name: 'SystemSettings',
        component: () => import('@/views/SystemSettings.vue')
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/Settings.vue')
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth !== false && !token) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
  } else if (to.name === 'Login' && token) {
    next({ name: 'Dashboard' })
  } else {
    next()
  }
})

export default router
