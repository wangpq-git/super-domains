<template>
  <div class="users-container page-stack">
    <PageHero
      eyebrow="ACCESS CONTROL"
      title="用户管理"
      subtitle="维护平台用户角色、可用状态和认证来源，保证操作权限边界清晰。"
      tone="slate"
    >
      <template #meta>
        <el-tag effect="plain" round>共 {{ users.length }} 名用户</el-tag>
      </template>
    </PageHero>

    <el-card shadow="never" class="data-card">
      <template #header>
        <div class="card-header">
          <div>
            <h3 class="section-title">用户列表</h3>
            <p class="section-subtitle">角色修改会立即生效，建议优先检查管理员数量与禁用状态。</p>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="users" stripe style="width: 100%">
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column prop="display_name" label="显示名" width="160">
          <template #default="{ row }">{{ row.display_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.email || '-' }}</template>
        </el-table-column>
        <el-table-column prop="role" label="角色" width="140">
          <template #default="{ row }">
            <el-select
              v-model="row.role"
              size="small"
              style="width: 108px"
              @change="handleRoleChange(row)"
            >
              <el-option label="管理员" value="admin" />
              <el-option label="观察者" value="viewer" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="auth_source" label="认证来源" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.auth_source === 'ldap' ? 'primary' : 'info'" effect="light">
              {{ row.auth_source === 'ldap' ? 'LDAP' : '本地' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.is_active" @change="handleStatusChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import PageHero from '@/components/PageHero.vue'
import { getUsers, updateUser } from '@/api/users'
import { formatDateTime } from '@/utils/format'

interface UserItem {
  id: number
  username: string
  display_name: string | null
  email: string | null
  role: string
  is_active: boolean
  auth_source: string
  created_at: string
}

const users = ref<UserItem[]>([])
const loading = ref(false)

function formatTime(val: string): string {
  return formatDateTime(val)
}

async function fetchUsers(force = false) {
  loading.value = true
  try {
    const { data } = await getUsers(force)
    users.value = data ?? []
  } catch {
    users.value = []
  } finally {
    loading.value = false
  }
}

async function handleRoleChange(row: UserItem) {
  try {
    await updateUser(row.id, { role: row.role })
    ElMessage.success('角色更新成功')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
    await fetchUsers()
  }
}

async function handleStatusChange(row: UserItem) {
  try {
    await updateUser(row.id, { is_active: row.is_active })
    ElMessage.success(row.is_active ? '已启用' : '已禁用')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
    await fetchUsers()
  }
}

onMounted(() => {
  fetchUsers()
})
</script>

<style scoped>
.users-container {
  width: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
