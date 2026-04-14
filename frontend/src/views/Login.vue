<template>
  <div class="login-container">
    <div class="login-bg-pattern"></div>
    <el-card class="login-card" shadow="never">
      <div class="login-brand">
        <div class="login-logo">
          <div class="login-logo-mark" aria-hidden="true">
            <span class="logo-orbit logo-orbit--outer"></span>
            <span class="logo-orbit logo-orbit--inner"></span>
            <span class="logo-node logo-node--top"></span>
            <span class="logo-node logo-node--right"></span>
            <span class="logo-node logo-node--bottom"></span>
            <span class="logo-node logo-node--left"></span>
            <span class="logo-core"></span>
          </div>
        </div>
        <h2 class="login-title">域名管理平台</h2>
        <p class="login-subtitle">使用公司 LDAP 账号登录</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="0" size="large" class="login-form">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名">
            <template #prefix>
              <el-icon><User /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" show-password @keyup.enter="handleLogin">
            <template #prefix>
              <el-icon><Lock /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" class="login-btn" @click="handleLogin">
            {{ loading ? '登录中...' : '登 录' }}
          </el-button>
        </el-form-item>
      </el-form>
      <div class="login-footer">
        <el-icon :size="14" color="#909399"><InfoFilled /></el-icon>
        <span>如忘记密码，请联系 IT 管理员重置</span>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { InfoFilled, Lock, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from '@/utils/message'
import type { FormInstance } from 'element-plus'

const authStore = useAuthStore()
const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  await formRef.value?.validate()
  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    ElMessage.success('登录成功')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 40%, #312e81 100%);
  position: relative;
  overflow: hidden;
}

.login-bg-pattern {
  position: absolute;
  top: -50%;
  right: -30%;
  width: 80%;
  height: 200%;
  background: radial-gradient(ellipse at center, rgba(67, 97, 238, 0.15) 0%, transparent 70%);
  pointer-events: none;
}

.login-card {
  width: 420px;
  border-radius: 16px !important;
  backdrop-filter: blur(20px);
  background: rgba(255, 255, 255, 0.97) !important;
  box-shadow: 0 25px 50px rgba(0, 0, 0, 0.25) !important;
  animation: fadeInUp 0.6s cubic-bezier(0.16, 1, 0.3, 1);
  padding: 8px 12px;
  z-index: 1;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.login-brand {
  text-align: center;
  margin-bottom: 32px;
}

.login-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border-radius: 22px;
  background:
    radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.28), transparent 36%),
    linear-gradient(145deg, #3b82f6 0%, #4f46e5 45%, #1d4ed8 100%);
  margin-bottom: 16px;
  box-shadow:
    0 12px 24px rgba(37, 99, 235, 0.34),
    inset 0 1px 1px rgba(255, 255, 255, 0.25);
}

.login-logo-mark {
  position: relative;
  width: 40px;
  height: 40px;
}

.logo-orbit,
.logo-core,
.logo-node {
  position: absolute;
  inset: 0;
}

.logo-orbit {
  border-radius: 999px;
  border: 1.6px solid rgba(255, 255, 255, 0.82);
}

.logo-orbit--outer {
  transform: rotate(18deg);
}

.logo-orbit--inner {
  inset: 7px;
  border-color: rgba(191, 219, 254, 0.92);
  transform: rotate(-18deg);
}

.logo-core {
  inset: 14px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 0 12px rgba(255, 255, 255, 0.35);
}

.logo-node {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #dbeafe;
  box-shadow: 0 0 10px rgba(219, 234, 254, 0.7);
}

.logo-node--top {
  top: 1px;
  left: 50%;
  transform: translateX(-50%);
}

.logo-node--right {
  top: 50%;
  right: 1px;
  transform: translateY(-50%);
}

.logo-node--bottom {
  bottom: 1px;
  left: 50%;
  transform: translateX(-50%);
}

.logo-node--left {
  top: 50%;
  left: 1px;
  transform: translateY(-50%);
}

.login-title {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: 0.5px;
}

.login-subtitle {
  margin: 0;
  font-size: 14px;
  color: #94a3b8;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px #e2e8f0 inset;
  padding: 4px 12px;
  transition: box-shadow 0.2s ease;
}

.login-form :deep(.el-input__prefix-inner) {
  color: #64748b;
}

.login-form :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #cbd5e1 inset;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px rgba(67, 97, 238, 0.3) inset;
}

.login-btn {
  width: 100%;
  height: 46px;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  background: var(--dm-gradient-blue, linear-gradient(135deg, #4361ee 0%, #6c83f2 100%));
  border: none;
  transition: all 0.3s ease;
  letter-spacing: 2px;
}

.login-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(67, 97, 238, 0.35);
}

.login-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}
</style>
