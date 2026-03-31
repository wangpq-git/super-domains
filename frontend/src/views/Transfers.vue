<template>
  <div class="transfers">
    <el-card shadow="never">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>域名转移管理</span>
          <el-button type="primary" :icon="Plus" @click="dialogVisible = true">发起转移</el-button>
        </div>
      </template>

      <el-table v-loading="loading" :data="transfers" stripe>
        <el-table-column prop="domain_name" label="域名" min-width="180" show-overflow-tooltip />
        <el-table-column prop="from_platform" label="源平台" width="120">
          <template #default="{ row }"><el-tag size="small">{{ row.from_platform || '-' }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="to_platform" label="目标平台" width="120">
          <template #default="{ row }"><el-tag type="success" size="small">{{ row.to_platform }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="auth_code" label="授权码" width="140">
          <template #default="{ row }">
            <span v-if="row.auth_code">{{ showCode ? row.auth_code : '••••••' }}
              <el-button link size="small" @click="showCode = !showCode">{{ showCode ? '隐藏' : '显示' }}</el-button>
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="initiated_at" label="发起时间" width="160" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-select v-if="row.status === 'pending' || row.status === 'in_progress'" v-model="row._newStatus" placeholder="更新状态" size="small" style="width:110px;margin-right:8px" @change="handleUpdateStatus(row)">
              <el-option label="进行中" value="in_progress" />
              <el-option label="已完成" value="completed" />
              <el-option label="失败" value="failed" />
            </el-select>
            <el-popconfirm v-if="row.status === 'pending'" title="确定取消此转移？" @confirm="handleCancel(row.id)">
              <template #reference><el-button size="small" type="danger">取消</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" style="margin-top:16px" @change="fetchTransfers" />
    </el-card>

    <el-dialog v-model="dialogVisible" title="发起域名转移" width="480px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="80px">
        <el-form-item label="域名ID" prop="domain_id">
          <el-input-number v-model="form.domain_id" :min="1" style="width:100%" placeholder="输入域名ID" />
        </el-form-item>
        <el-form-item label="目标平台" prop="to_platform">
          <el-select v-model="form.to_platform" style="width:100%">
            <el-option v-for="p in platforms" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标账号">
          <el-input v-model="form.to_account" placeholder="目标平台账号名" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getTransfers, createTransfer, updateTransfer, cancelTransfer } from '@/api/transfers'

const transfers = ref<any[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const dialogVisible = ref(false)
const submitting = ref(false)
const showCode = ref(false)
const platforms = ['cloudflare', 'namecom', 'dynadot', 'godaddy', 'namecheap', 'namesilo', 'openprovider', 'porkbun', 'spaceship']
const form = ref({ domain_id: 0, to_platform: '', to_account: '' })

function statusType(s: string) {
  const m: Record<string, string> = { pending: 'info', in_progress: 'warning', completed: 'success', failed: 'danger', cancelled: 'info' }
  return (m[s] || '') as any
}
function statusLabel(s: string) {
  const m: Record<string, string> = { pending: '待处理', in_progress: '进行中', completed: '已完成', failed: '失败', cancelled: '已取消' }
  return m[s] || s
}

async function fetchTransfers() {
  loading.value = true
  try {
    const { data } = await getTransfers({ page: page.value, page_size: 20 })
    transfers.value = (data.items ?? []).map((t: any) => ({ ...t, _newStatus: '' }))
    total.value = data.total ?? 0
  } finally { loading.value = false }
}

async function handleCreate() {
  submitting.value = true
  try {
    await createTransfer(form.value)
    ElMessage.success('转移已发起')
    dialogVisible.value = false
    await fetchTransfers()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '操作失败') }
  finally { submitting.value = false }
}

async function handleUpdateStatus(row: any) {
  if (!row._newStatus) return
  try {
    await updateTransfer(row.id, { status: row._newStatus })
    ElMessage.success('状态已更新')
    await fetchTransfers()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}

async function handleCancel(id: number) {
  try {
    await cancelTransfer(id)
    ElMessage.success('已取消转移')
    await fetchTransfers()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}

onMounted(fetchTransfers)
</script>
