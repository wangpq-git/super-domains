<template>
  <div class="accounts-container">
    <section class="hero-panel">
      <div class="hero-copy">
        <p class="hero-eyebrow">ACCOUNT CENTER</p>
        <div class="hero-title-row">
          <h1>平台账户管理</h1>
          <el-tag type="info" effect="plain" round>共 {{ store.total || store.accounts.length }} 个账户</el-tag>
        </div>
        <p class="hero-subtitle">集中维护各平台凭证、同步状态与域名规模，异常账户可以更快定位和处理。</p>
      </div>
      <div class="hero-actions">
        <el-button :icon="Refresh" circle @click="handleRefresh" />
        <el-button type="success" plain :icon="Refresh" :loading="syncingAll" @click="handleSyncAll">一键同步所有</el-button>
        <el-button v-if="authStore.isAdmin" type="primary" :icon="Plus" @click="openDialog()">添加账户</el-button>
      </div>
    </section>

    <section class="stats-grid">
      <article class="stat-card stat-card--primary">
        <span class="stat-label">已接入平台</span>
        <strong class="stat-value">{{ platformStats.connected }}</strong>
        <span class="stat-hint">当前列表中不同平台数量</span>
      </article>
      <article class="stat-card">
        <span class="stat-label">域名总量</span>
        <strong class="stat-value">{{ platformStats.domains }}</strong>
        <span class="stat-hint">已同步账户域名累计</span>
      </article>
      <article class="stat-card">
        <span class="stat-label">同步成功</span>
        <strong class="stat-value">{{ platformStats.success }}</strong>
        <span class="stat-hint">最近一次同步状态正常</span>
      </article>
      <article class="stat-card stat-card--warn">
        <span class="stat-label">待关注</span>
        <strong class="stat-value">{{ platformStats.needsAttention }}</strong>
        <span class="stat-hint">失败、同步中或未同步账户</span>
      </article>
    </section>

    <el-card shadow="never" class="accounts-card">
      <template #header>
        <div class="card-header">
          <div>
            <span>账户列表</span>
            <p class="card-subtitle">优先查看异常状态和最近未同步的账户，批量同步前可先测试连接。</p>
          </div>
          <el-tag type="info" effect="plain">{{ store.accounts.length }} 条当前记录</el-tag>
        </div>
      </template>

      <div class="table-shell">
        <el-table
          v-loading="store.loading"
          :data="store.accounts"
          stripe
          class="accounts-table"
          @sort-change="handleSortChange"
        >
          <el-table-column prop="platform" label="平台" width="140" sortable="custom">
            <template #default="{ row }">
              <el-tag :type="platformTagType(row.platform)" size="small" effect="light">{{ platformLabel(row.platform) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="account_name" label="账户名称" min-width="240" show-overflow-tooltip sortable="custom">
            <template #default="{ row }">
              <div class="account-cell">
                <span class="account-name">{{ row.account_name }}</span>
                <span class="account-meta">{{ row.domain_count || 0 }} 个域名</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="domain_count" label="域名数量" width="110" align="center" />
          <el-table-column prop="last_sync_at" label="最后同步" min-width="200" sortable="custom">
            <template #default="{ row }">
              <div class="sync-cell">
                <span>{{ row.last_sync_at ? formatDateTime(row.last_sync_at) : '从未同步' }}</span>
                <span class="sync-hint">{{ formatSyncHint(row.sync_status) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="sync_status" label="同步状态" width="120" align="center">
            <template #default="{ row }">
              <el-tag :type="syncStatusType(row.sync_status)" size="small" effect="light" :class="syncStatusClass(row.sync_status)">
                {{ syncStatusLabel(row.sync_status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="180" align="center">
            <template #default="{ row }">
              <div class="action-row">
                <el-button v-if="authStore.isAdmin" size="small" text class="action-btn" :icon="Connection" @click="handleTest(row)">测试</el-button>
                <el-button size="small" type="primary" class="action-btn" :icon="Refresh" @click="handleSync(row)">同步</el-button>
                <el-dropdown v-if="authStore.isAdmin" trigger="click">
                  <el-button size="small" class="action-btn action-more">
                    更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item :icon="Edit" @click="openDialog(row)">编辑</el-dropdown-item>
                      <el-dropdown-item :icon="Delete" divided @click="confirmDelete(row)">删除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="store.page"
          v-model:page-size="store.pageSize"
          :total="store.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="handleSizeChange"
          @current-change="store.fetchAccounts()"
        />
      </div>
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

const platformStats = computed(() => {
  const rows = store.accounts || []
  const platforms = new Set(rows.map((row: any) => row.platform).filter(Boolean))
  const success = rows.filter((row: any) => row.sync_status === 'success').length
  const needsAttention = rows.filter((row: any) => row.sync_status !== 'success').length
  const domains = rows.reduce((sum: number, row: any) => sum + (Number(row.domain_count) || 0), 0)

  return {
    connected: platforms.size,
    success,
    needsAttention,
    domains,
  }
})

const rules = {
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }],
  name: [{ required: true, message: '请输入账户名称', trigger: 'blur' }],
}

function handleSortChange({ prop, order }: { prop: string; order: string | null }) {
  store.page = 1
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

function syncStatusType(status?: string) {
  if (status === 'success') return 'success'
  if (status === 'failed' || status === 'error') return 'danger'
  if (status === 'syncing') return 'primary'
  return 'info'
}

function syncStatusLabel(status?: string) {
  if (status === 'success') return '成功'
  if (status === 'failed' || status === 'error') return '失败'
  if (status === 'syncing') return '同步中'
  if (!status) return '未同步'
  return '未知'
}

function syncStatusClass(status?: string) {
  if (status === 'success') return 'status-tag status-tag--success'
  if (status === 'failed' || status === 'error') return 'status-tag status-tag--danger'
  if (status === 'syncing') return 'status-tag status-tag--primary'
  return 'status-tag status-tag--muted'
}

function formatSyncHint(status?: string) {
  if (status === 'success') return '最近一次同步完成'
  if (status === 'failed' || status === 'error') return '建议优先检查凭证和接口状态'
  if (status === 'syncing') return '任务正在后台执行'
  return '尚未发起同步'
}

function handleSizeChange() {
  store.page = 1
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
    if (data.status && data.status !== 'success') {
      throw new Error(data.error || '同步失败')
    }
    const count = data.synced ?? data.domain_count ?? data.domains?.length ?? 0
    ElMessage.success(`同步完成，共 ${count} 个域名`)
    store.fetchAccounts()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.response?.data?.message || e.message || '同步失败')
  }
}

async function handleSyncAll() {
  syncingAll.value = true
  try {
    const { data } = await syncAllAccounts()
    const success = data.results?.filter((r: any) => r.status === 'success' || !r.error).length ?? data.success ?? 0
    const failed = data.results?.filter((r: any) => r.status === 'failed' || !!r.error).length ?? data.failed ?? 0
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
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero-panel {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 24px 28px;
  border-radius: 20px;
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.28), transparent 32%),
    linear-gradient(135deg, #17324d 0%, #244d6e 42%, #2d6b73 100%);
  color: #fff;
  box-shadow: 0 18px 48px rgba(23, 50, 77, 0.18);
}

.hero-copy {
  max-width: 760px;
}

.hero-eyebrow {
  margin: 0 0 10px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
  color: rgba(255, 255, 255, 0.72);
}

.hero-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.hero-title-row h1 {
  margin: 0;
  font-size: 28px;
  line-height: 1.15;
}

.hero-subtitle {
  margin: 12px 0 0;
  max-width: 620px;
  font-size: 14px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.82);
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px 20px;
  border: 1px solid rgba(18, 39, 61, 0.06);
  border-radius: 16px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}

.stat-card--primary {
  background: linear-gradient(135deg, rgba(67, 97, 238, 0.1) 0%, rgba(108, 131, 242, 0.04) 100%);
}

.stat-card--warn {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(255, 255, 255, 0.96) 100%);
}

.stat-label {
  font-size: 12px;
  font-weight: 600;
  color: #667085;
  letter-spacing: 0.04em;
}

.stat-value {
  font-size: 30px;
  line-height: 1;
  color: #162234;
}

.stat-hint {
  font-size: 13px;
  color: #7b8794;
}

.accounts-card {
  overflow: hidden;
}

.accounts-table {
  width: 100%;
}

.table-shell {
  overflow-x: auto;
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.card-header span {
  font-size: 18px;
  font-weight: 600;
}

.card-subtitle {
  margin: 6px 0 0;
  font-size: 13px;
  color: #8a94a6;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.action-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.action-btn {
  padding: 5px 10px;
}

.action-more {
  min-width: 58px;
}

.account-cell,
.sync-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.account-name {
  font-weight: 600;
  color: #1f2937;
}

.account-meta,
.sync-hint {
  font-size: 12px;
  color: #8a94a6;
}

.status-tag {
  min-width: 64px;
  justify-content: center;
  border: none;
}

.status-tag--success {
  background: rgba(16, 185, 129, 0.12);
}

.status-tag--danger {
  background: rgba(239, 68, 68, 0.12);
}

.status-tag--primary {
  background: rgba(67, 97, 238, 0.12);
}

.status-tag--muted {
  background: rgba(100, 116, 139, 0.12);
}

@media (max-width: 1080px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .hero-panel {
    padding: 20px;
    border-radius: 16px;
    flex-direction: column;
    align-items: stretch;
  }

  .hero-title-row h1 {
    font-size: 24px;
  }

  .hero-actions {
    justify-content: stretch;
  }

  .hero-actions :deep(.el-button) {
    flex: 1;
    min-width: 0;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .card-header {
    align-items: stretch;
  }

  .pagination-wrapper {
    justify-content: center;
  }

  .action-row {
    flex-wrap: wrap;
  }
}
</style>
