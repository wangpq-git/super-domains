<template>
  <div class="users-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>用户管理</span>
        </div>
      </template>

      <el-table v-loading="loading" :data="users" stripe style="width: 100%">
        <el-table-column prop="username" label="用户名" width="130" />
        <el-table-column prop="display_name" label="显示名" width="150">
          <template #default="{ row }">{{ row.display_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.email || '-' }}</template>
        </el-table-column>
        <el-table-column prop="role" label="角色" width="130">
          <template #default="{ row }">
            <el-select
              v-model="row.role"
              size="small"
              style="width: 100px"
              @change="handleRoleChange(row)"
            >
              <el-option label="管理员" value="admin" />
              <el-option label="观察者" value="viewer" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="auth_source" label="认证来源" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.auth_source === 'ldap' ? 'primary' : 'info'">
              {{ row.auth_source === 'ldap' ? 'LDAP' : '本地' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_active"
              @change="handleStatusChange(row)"
            />
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

async function fetchUsers() {
  loading.value = true
  try {
    const { data } = await getUsers()
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
  padding-bottom: 20px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-header span {
  font-size: 18px;
  font-weight: 600;
}
</style>
