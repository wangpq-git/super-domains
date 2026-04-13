<template>
  <el-container class="layout-container">
    <el-aside :width="isCollapse ? '78px' : '248px'" class="aside">
      <div class="logo">
        <div class="logo-icon">
          <el-icon :size="20" color="#fff"><Monitor /></el-icon>
        </div>
        <div v-show="!isCollapse" class="logo-copy">
          <span class="logo-text">域名管理平台</span>
          <small class="logo-subtitle">Domain Console</small>
        </div>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        router
        background-color="transparent"
        text-color="#a3b1bf"
        active-text-color="#dbe7ff"
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
        <el-menu-item index="/service-discovery">
          <el-icon><Share /></el-icon>
          <template #title>服务解析</template>
        </el-menu-item>
        <el-menu-item index="/cos-discovery">
          <el-icon><Files /></el-icon>
          <template #title>COS解析</template>
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
          <button type="button" class="collapse-btn" @click="isCollapse = !isCollapse">
            <el-icon :size="18">
              <Fold v-if="!isCollapse" />
              <Expand v-else />
            </el-icon>
          </button>
          <div class="header-copy">
            <el-breadcrumb separator="/" class="header-breadcrumb">
              <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
              <el-breadcrumb-item v-if="currentPageTitle">{{ currentPageTitle }}</el-breadcrumb-item>
            </el-breadcrumb>
            <div class="header-title-row">
              <span class="header-title">{{ currentPageTitle || '域名管理平台' }}</span>
              <el-tag size="small" effect="plain" class="header-status">{{ currentDateLabel }}</el-tag>
            </div>
          </div>
        </div>
        <div class="header-right">
          <el-dropdown>
            <span class="user-info">
              <el-avatar :size="34" class="user-avatar">{{ avatarText }}</el-avatar>
              <span class="user-copy">
                <span class="username">{{ displayName }}</span>
                <span class="user-role">{{ authStore.isAdmin ? '管理员' : '普通用户' }}</span>
              </span>
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
        <div class="content-shell">
          <router-view v-slot="{ Component }">
            <transition name="fade-slide" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </div>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import {
  ArrowDown,
  Bell,
  Connection,
  DataAnalysis,
  Expand,
  Files,
  Fold,
  Monitor,
  Setting,
  Share,
  SwitchButton,
  Tickets,
  Tools,
  User,
  UserFilled,
} from '@element-plus/icons-vue'
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
  '/service-discovery': '服务解析',
  '/cos-discovery': 'COS解析',
  '/system-settings': '系统配置',
  '/users': '用户管理',
}

const currentPageTitle = computed(() => titleMap[route.path] || '')
const currentDateLabel = computed(() => {
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  }).format(new Date())
})
</script>

<style scoped>
.layout-container {
  height: 100vh;
  background: #edf3f9;
}

.aside {
  background:
    radial-gradient(circle at top left, rgba(108, 131, 242, 0.16), transparent 28%),
    linear-gradient(180deg, #162430 0%, #172c38 100%);
  transition: width 0.26s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  box-shadow: 10px 0 30px rgba(15, 23, 42, 0.12);
  z-index: 10;
}

.logo {
  height: 72px;
  display: flex;
  align-items: center;
  gap: 12px;
  color: #fff;
  padding: 0 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.logo-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: linear-gradient(135deg, #4361ee 0%, #6c83f2 100%);
  box-shadow: 0 8px 20px rgba(67, 97, 238, 0.35);
  flex-shrink: 0;
}

.logo-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.logo-text {
  white-space: nowrap;
  overflow: hidden;
  font-size: 15px;
  font-weight: 700;
}

.logo-subtitle {
  margin-top: 2px;
  color: rgba(255, 255, 255, 0.52);
  font-size: 11px;
  letter-spacing: 0.08em;
}

.side-menu {
  border-right: none;
  height: calc(100vh - 72px);
  overflow-y: auto;
  padding: 10px 0;
}

.side-menu :deep(.el-menu-item) {
  height: 46px;
  line-height: 46px;
  margin: 4px 10px;
  border-radius: 12px;
  font-size: 14px;
  transition: all 0.2s ease;
  position: relative;
  overflow: visible;
}

.side-menu :deep(.el-menu-item .el-icon) {
  font-size: 16px;
}

.side-menu :deep(.el-menu-item:hover) {
  background-color: rgba(255, 255, 255, 0.08) !important;
}

.side-menu :deep(.el-menu-item.is-active) {
  background-color: rgba(67, 97, 238, 0.2) !important;
  color: #dbe7ff !important;
  font-weight: 600;
}

.side-menu :deep(.el-menu-item.is-active::before) {
  content: '';
  position: absolute;
  left: -10px;
  top: 8px;
  bottom: 8px;
  width: 4px;
  border-radius: 0 4px 4px 0;
  background: linear-gradient(180deg, #6c83f2 0%, #8db0ff 100%);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(16px);
  padding: 0 24px;
  height: 72px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.8);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.collapse-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 0;
  border-radius: 12px;
  background: #f8fafc;
  color: #5b6778;
  cursor: pointer;
  transition: all 0.2s ease;
}

.collapse-btn:hover {
  color: #4361ee;
  background: #edf3ff;
}

.header-copy {
  min-width: 0;
}

.header-breadcrumb {
  margin-bottom: 6px;
}

.header-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.header-title {
  font-size: 20px;
  font-weight: 700;
  color: #0f172a;
}

.header-status {
  color: #64748b;
}

.header-right {
  display: flex;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  color: #334155;
  font-size: 14px;
  padding: 8px 10px;
  border-radius: 14px;
  transition: background-color 0.2s ease;
}

.user-info:hover {
  background-color: #f8fafc;
}

.user-avatar {
  background: linear-gradient(135deg, #4361ee 0%, #6c83f2 100%);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
}

.user-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.username {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}

.user-role {
  color: #64748b;
  font-size: 12px;
}

.main-content {
  background: var(--dm-page-bg);
  padding: var(--dm-content-padding);
  overflow-y: auto;
}

.content-shell {
  max-width: var(--dm-content-max-width);
  margin: 0 auto;
}

@media (max-width: 900px) {
  .aside {
    width: 78px !important;
  }

  .header {
    padding: 0 16px;
  }

  .header-title {
    font-size: 18px;
  }

  .user-copy {
    display: none;
  }
}

@media (max-width: 768px) {
  .header {
    height: auto;
    min-height: 72px;
    align-items: flex-start;
    gap: 12px;
    padding: 14px 16px;
  }

  .header-left {
    align-items: flex-start;
  }
}
</style>
