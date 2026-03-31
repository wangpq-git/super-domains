<template>
  <div class="accounts-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>平台账户管理</span>
          <el-button type="primary" :icon="Plus" @click="openDialog()">添加账户</el-button>
        </div>
      </template>

      <el-table v-loading="store.loading" :data="store.accounts" stripe style="width: 100%">
        <el-table-column prop="platform" label="平台" width="140">
          <template #default="{ row }">
            <el-tag :type="platformTagType(row.platform)" size="small">{{ row.platform }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="account_name" label="账户名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="domain_count" label="域名数量" width="110" align="center" />
        <el-table-column prop="last_sync_at" label="最后同步" width="180">
          <template #default="{ row }">{{ row.last_sync_at || '从未同步' }}</template>
        </el-table-column>
        <el-table-column prop="sync_status" label="同步状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.sync_status === 'success'" type="success" size="small">成功</el-tag>
            <el-tag v-else-if="row.sync_status === 'failed'" type="danger" size="small">失败</el-tag>
            <el-tag v-else-if="row.sync_status === 'syncing'" type="primary" size="small">同步中</el-tag>
            <el-tag v-else type="info" size="small">未知</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button size="small" :icon="Connection" @click="handleTest(row)">测试</el-button>
            <el-button size="small" type="primary" :icon="Refresh" @click="handleSync(row)">同步</el-button>
            <el-button size="small" type="warning" :icon="Edit" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除该账户吗？" @confirm="handleDelete(row)">
              <template #reference>
                <el-button size="small" type="danger" :icon="Delete">删除</el-button>
              </template>
            </el-popconfirm>
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
        <el-form-item label="API Key" prop="api_key">
          <el-input v-model="form.api_key" placeholder="输入API Key" show-password />
        </el-form-item>
        <el-form-item label="API Secret" prop="api_secret">
          <el-input v-model="form.api_secret" placeholder="输入API Secret（可选）" show-password />
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
import { ref, reactive, onMounted } from 'vue'
import { Plus, Edit, Delete, Refresh, Connection } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { useAccountsStore } from '@/stores/accounts'
import { createAccount, updateAccount, deleteAccount, testAccount, syncAccount } from '@/api/accounts'

const store = useAccountsStore()
const formRef = ref<FormInstance>()
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref<number | null>(null)
const submitting = ref(false)

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

const defaultForm = { platform: '', name: '', api_key: '', api_secret: '' }
const form = reactive({ ...defaultForm })

const rules = {
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }],
  name: [{ required: true, message: '请输入账户名称', trigger: 'blur' }],
  api_key: [{ required: true, message: '请输入API Key', trigger: 'blur' }],
}

function platformTagType(platform: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
    cloudflare: 'warning',
    namecom: 'success',
    dynadot: '',
    godaddy: 'success',
    namecheap: 'danger',
    namesilo: 'info',
    openprovider: 'info',
    porkbun: 'danger',
    spaceship: 'info',
  }
  return map[platform] ?? ''
}

function openDialog(row?: any) {
  isEdit.value = !!row
  editId.value = row?.id ?? null
  Object.assign(form, row ? { platform: row.platform, name: row.account_name || row.name, api_key: '', api_secret: '' } : { ...defaultForm })
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value?.validate()
  submitting.value = true
  try {
    if (isEdit.value && editId.value) {
      const payload: any = { account_name: form.name }
      if (form.api_key) {
        const creds: any = { api_key: form.api_key }
        if (form.api_secret) creds.api_secret = form.api_secret
        payload.credentials = creds
      }
      await updateAccount(editId.value, payload)
      ElMessage.success('更新成功')
    } else {
      const credentials: any = { api_key: form.api_key }
      if (form.api_secret) credentials.api_secret = form.api_secret
      await createAccount({ platform: form.platform, account_name: form.name, credentials })
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
    await syncAccount(row.id)
    ElMessage.success('同步完成')
    store.fetchAccounts()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '同步失败')
  }
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
  max-width: 1200px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
