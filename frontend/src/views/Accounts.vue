<template>
  <div class="accounts-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>平台账户管理</span>
          <div>
            <el-button :icon="Refresh" circle @click="handleRefresh" />
            <el-button type="success" :icon="Refresh" :loading="syncingAll" @click="handleSyncAll">一键同步所有</el-button>
            <el-button v-if="authStore.isAdmin" type="primary" :icon="Plus" @click="openDialog()">添加账户</el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="store.loading" :data="store.accounts" stripe style="width: 100%" @sort-change="handleSortChange">
        <el-table-column prop="platform" label="平台" width="140" sortable="custom">
          <template #default="{ row }">
            <el-tag :type="platformTagType(row.platform)" size="small">{{ platformLabel(row.platform) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="account_name" label="账户名称" min-width="180" show-overflow-tooltip sortable="custom" />
        <el-table-column prop="domain_count" label="域名数量" width="110" align="center" />
        <el-table-column prop="last_sync_at" label="最后同步" width="180" sortable="custom">
          <template #default="{ row }">{{ row.last_sync_at ? formatDateTime(row.last_sync_at) : '从未同步' }}</template>
        </el-table-column>
        <el-table-column prop="sync_status" label="同步状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.sync_status === 'success'" type="success" size="small">成功</el-tag>
            <el-tag v-else-if="row.sync_status === 'failed'" type="danger" size="small">失败</el-tag>
            <el-tag v-else-if="row.sync_status === 'syncing'" type="primary" size="small">同步中</el-tag>
            <el-tag v-else type="info" size="small">未知</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button v-if="authStore.isAdmin" size="small" :icon="Connection" @click="handleTest(row)">测试</el-button>
            <el-button size="small" type="primary" :icon="Refresh" @click="handleSync(row)">同步</el-button>
            <el-dropdown v-if="authStore.isAdmin" trigger="click">
              <el-button size="small">
                更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item :icon="Edit" @click="openDialog(row)">编辑</el-dropdown-item>
                  <el-dropdown-item :icon="Delete" divided @click="confirmDelete(row)">删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑账户' : '添加账户'" width="500px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="平台" prop="platform">
          <el-select v-model="form.platform" placeholder="选择平台" style="width: 100%" :disabled="isEdit">
            <el-option v-for="p in platforms" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="账户名称" prop="name">
          <el-input v-model="form.name" placeholder="输入账户名称" />
        </el-form-item>
        <el-form-item v-for="field in currentCredentialFields" :key="field.key" :label="field.label" :prop="'credentials.' + field.key" :rules="field.required ? [{required: true, message: `请输入${field.label}`, trigger: 'blur'}] : []">
          <el-input v-model="form.credentials[field.key]" :placeholder="field.placeholder" :type="field.type || 'text'" show-password />
        </el-form-item>
        <el-form-item v-if="isEdit">
          <el-alert type="info" :closable="false" description="留空表示不修改已有凭证" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Edit, Delete, Refresh, Connection, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { useAccountsStore } from '@/stores/accounts'
import { useAuthStore } from '@/stores/auth'
import { createAccount, updateAccount, deleteAccount, testAccount, syncAccount, syncAllAccounts } from '@/api/accounts'
import { platformLabel, formatDateTime, platformTagType } from '@/utils/format'

const store = useAccountsStore()
const authStore = useAuthStore()
const formRef = ref<FormInstance>()
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref<number | null>(null)
const submitting = ref(false)
const syncingAll = ref(false)

const platforms = [
  { value: 'cloudflare', label: 'Cloudflare' },
  { value: 'namecom', label: 'Name.com' },
  { value: 'dynadot', label: 'Dynadot' },
  { value: 'godaddy', label: 'GoDaddy' },
  { value: 'namecheap', label: 'Namecheap' },
  { value: 'namesilo', label: 'NameSilo' },
  { value: 'openprovider', label: 'OpenProvider' },
  { value: 'porkbun', label: 'Porkbun' },
  { value: 'spaceship', label: 'Spaceship' },
]

const platformCredentialFields: Record<string, Array<{key: string, label: string, placeholder: string, required: boolean, type?: string}>> = {
  cloudflare: [
    { key: 'api_key', label: 'API Key', placeholder: '输入 Cloudflare Global API Key', required: true },
    { key: 'email', label: 'Email', placeholder: '输入 Cloudflare 账户邮箱', required: true },
    { key: 'account_id', label: 'Account ID', placeholder: '输入 Cloudflare Account ID', required: false },
  ],
  namecom: [
    { key: 'username', label: '用户名', placeholder: '输入 Name.com 用户名', required: true },
    { key: 'api_token', label: 'API Token', placeholder: '输入 API Token', required: true },
  ],
  godaddy: [
    { key: 'api_key', label: 'API Key', placeholder: '输入 GoDaddy API Key', required: true },
    { key: 'api_secret', label: 'API Secret', placeholder: '输入 API Secret', required: true },
  ],
  namecheap: [
    { key: 'username', label: '用户名', placeholder: '输入 Namecheap 用户名', required: true },
    { key: 'api_key', label: 'API Key', placeholder: '输入 API Key', required: true },
    { key: 'client_ip', label: '白名单 IP', placeholder: '服务器出口 IP', required: true },
  ],
  porkbun: [
    { key: 'api_key', label: 'API Key', placeholder: '输入 Porkbun API Key', required: true },
    { key: 'secret_key', label: 'Secret Key', placeholder: '输入 Secret Key', required: true },
  ],
  namesilo: [
    { key: 'api_key', label: 'API Key', placeholder: '输入 NameSilo API Key', required: true },
  ],
  dynadot: [
    { key: 'api_key', label: 'API Key', placeholder: '输入 Dynadot API Key', required: true },
  ],
  openprovider: [
    { key: 'username', label: '用户名', placeholder: '输入 OpenProvider 用户名', required: true },
    { key: 'password', label: '密码', placeholder: '输入密码', required: true, type: 'password' },
    { key: 'ip', label: '白名单 IP', placeholder: '服务器出口 IP（如 190.92.203.219）', required: false },
  ],
  spaceship: [
    { key: 'api_key', label: 'API Key', placeholder: '输入 Spaceship API Key', required: true },
    { key: 'api_secret', label: 'API Secret', placeholder: '输入 API Secret', required: true },
  ],
}

const defaultForm = { platform: '', name: '', credentials: {} as Record<string, string> }
const form = reactive({ ...defaultForm, credentials: {} as Record<string, string> })

const currentCredentialFields = computed(() => {
  return form.platform ? (platformCredentialFields[form.platform] || []) : []
})

const rules = {
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }],
  name: [{ required: true, message: '请输入账户名称', trigger: 'blur' }],
}

function handleSortChange({ prop, order }: { prop: string; order: string | null }) {
  if (order) {
    store.sortBy = prop
    store.sortOrder = order === 'ascending' ? 'asc' : 'desc'
  } else {
    store.sortBy = 'created_at'
    store.sortOrder = 'desc'
  }
  store.fetchAccounts()
}

function handleRefresh() {
  store.fetchAccounts()
}

function openDialog(row?: any) {
  isEdit.value = !!row
  editId.value = row?.id ?? null
  form.credentials = {}
  Object.assign(form, row ? { platform: row.platform, name: row.account_name || row.name } : { ...defaultForm, credentials: {} })
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value?.validate()
  submitting.value = true
  try {
    const filledCredentials: Record<string, string> = {}
    for (const [k, v] of Object.entries(form.credentials)) {
      if (v) filledCredentials[k] = v
    }
    if (isEdit.value && editId.value) {
      const payload: any = { account_name: form.name }
      if (Object.keys(filledCredentials).length > 0) {
        payload.credentials = filledCredentials
      }
      await updateAccount(editId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await createAccount({ platform: form.platform, account_name: form.name, credentials: filledCredentials })
      ElMessage.success('添加成功')
    }
    dialogVisible.value = false
    store.fetchAccounts()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '操作失败')
  } finally {
    submitting.value = false
  }
}

async function handleTest(row: any) {
  try {
    await testAccount(row.id)
    ElMessage.success('测试连接成功')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '测试连接失败')
  }
}

async function handleSync(row: any) {
  try {
    ElMessage.info('开始同步...')
    const { data } = await syncAccount(row.id)
    const count = data.domain_count ?? data.domains?.length ?? 0
    ElMessage.success(`同步完成，共 ${count} 个域名`)
    store.fetchAccounts()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '同步失败')
  }
}

async function handleSyncAll() {
  syncingAll.value = true
  try {
    const { data } = await syncAllAccounts()
    const success = data.results?.filter((r: any) => r.status === 'success').length ?? 0
    const failed = data.results?.filter((r: any) => r.status === 'failed').length ?? 0
    ElMessage.success(`同步完成: ${success} 成功, ${failed} 失败`)
    store.fetchAccounts()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '同步失败')
  } finally {
    syncingAll.value = false
  }
}

function confirmDelete(row: any) {
  ElMessageBox.confirm('确定删除该账户吗？', '确认删除', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(() => {
    handleDelete(row)
  }).catch(() => {})
}

async function handleDelete(row: any) {
  try {
    await deleteAccount(row.id)
    ElMessage.success('删除成功')
    store.fetchAccounts()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '删除失败')
  }
}

onMounted(() => {
  store.fetchAccounts()
})
</script>

<style scoped>
.accounts-container {
  width: 100%;
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