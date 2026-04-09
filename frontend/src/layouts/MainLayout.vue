<template>
  <el-container class="layout-container">
    <el-aside :width="isCollapse ? '64px' : '220px'" class="aside">
      <div class="logo">
        <div class="logo-icon">
          <el-icon :size="20" color="#fff"><Monitor /></el-icon>
        </div>
        <span v-show="!isCollapse" class="logo-text">域名管理平台</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        router
        background-color="transparent"
        text-color="#a3b1bf"
        active-text-color="#4361ee"
        class="side-menu"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <template #title>仪表盘</template>
        </el-menu-item>
        <el-menu-item index="/domains">
          <el-icon><Connection /></el-icon>
          <template #title>域名管理</template>
        </el-menu-item>
        <el-menu-item index="/accounts">
          <el-icon><User /></el-icon>
          <template #title>账户管理</template>
        </el-menu-item>
        <el-menu-item index="/dns">
          <el-icon><Setting /></el-icon>
          <template #title>DNS管理</template>
        </el-menu-item>
        <el-menu-item index="/change-requests">
          <el-icon><Tickets /></el-icon>
          <template #title>审批中心</template>
        </el-menu-item>
        <el-menu-item index="/alerts">
          <el-icon><Bell /></el-icon>
          <template #title>告警规则</template>
        </el-menu-item>
        <el-menu-item v-if="authStore.isAdmin" index="/system-settings">
          <el-icon><Tools /></el-icon>
          <template #title>系统配置</template>
        </el-menu-item>
        <el-menu-item v-if="authStore.isAdmin" index="/users">
          <el-icon><UserFilled /></el-icon>
          <template #title>用户管理</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-icon
            :size="18"
            class="collapse-btn"
            @click="isCollapse = !isCollapse"
          >
            <Fold v-if="!isCollapse" />
            <Expand v-else />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="currentPageTitle">{{ currentPageTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-dropdown>
            <span class="user-info">
              <el-avatar :size="30" class="user-avatar">
                {{ avatarText }}
              </el-avatar>
              <span class="username">{{ displayName }}</span>
              <el-tag size="small" :type="authStore.isAdmin ? 'primary' : 'info'" style="margin-right: 8px">
                {{ authStore.isAdmin ? '管理员' : '普通用户' }}
              </el-tag>
              <el-icon :size="12"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="authStore.logout()">
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()
const isCollapse = ref(false)

onMounted(() => {
  if (authStore.token && !authStore.user) {
    authStore.fetchUser()
  }
})

const activeMenu = computed(() => route.path)

const displayName = computed(() => {
  return authStore.user?.display_name || authStore.user?.username || '管理员'
})

const avatarText = computed(() => {
  const name = displayName.value
  return name.charAt(0).toUpperCase()
})

const titleMap: Record<string, string> = {
  '/dashboard': '仪表盘',
  '/domains': '域名管理',
  '/accounts': '账户管理',
  '/dns': 'DNS管理',
  '/change-requests': '审批中心',
  '/alerts': '告警规则',
  '/system-settings': '系统配置',
  '/users': '用户管理',
}

const currentPageTitle = computed(() => titleMap[route.path] || '')
</script>

<style scoped>
.layout-container {
  height: 100vh;
}

.aside {
  background-color: #1d2b36;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.08);
  z-index: 10;
}

.logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.5px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  padding: 0 16px;
}

.logo-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: linear-gradient(135deg, #4361ee 0%, #6c83f2 100%);
  flex-shrink: 0;
}

.logo-text {
  white-space: nowrap;
  overflow: hidden;
}

.side-menu {
  border-right: none;
  height: calc(100vh - 56px);
  overflow-y: auto;
  padding: 8px 0;
}

/* Menu item with left highlight bar on active */
.side-menu :deep(.el-menu-item) {
  height: 44px;
  line-height: 44px;
  margin: 2px 8px;
  border-radius: 8px;
  font-size: 14px;
  transition: all 0.2s ease;
  position: relative;
  overflow: visible;
}

.side-menu :deep(.el-menu-item:hover) {
  background-color: rgba(255, 255, 255, 0.06) !important;
}

.side-menu :deep(.el-menu-item.is-active) {
  background-color: rgba(67, 97, 238, 0.15) !important;
  color: #4361ee !important;
  font-weight: 600;
}

.side-menu :deep(.el-menu-item.is-active::before) {
  content: '';
  position: absolute;
  left: -8px;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: #4361ee;
}

.side-menu::-webkit-scrollbar {
  width: 4px;
}
.side-menu::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  background: #fff;
  padding: 0 24px;
  height: 56px;
  z-index: 5;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.collapse-btn {
  cursor: pointer;
  color: #8c8c8c;
  transition: color 0.2s;
}

.collapse-btn:hover {
  color: #4361ee;
}

.header-right {
  display: flex;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #4a5568;
  font-size: 14px;
  padding: 4px 8px;
  border-radius: 8px;
  transition: background-color 0.2s;
}

.user-info:hover {
  background-color: #f7fafc;
}

.user-avatar {
  background: linear-gradient(135deg, #4361ee 0%, #6c83f2 100%);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
}

.username {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.main-content {
  background-color: #f5f7fa;
  padding: 24px;
  overflow-y: auto;
}

/* Route transition */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.25s ease;
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
