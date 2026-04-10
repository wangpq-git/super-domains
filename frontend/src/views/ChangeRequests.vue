<template>
  <div class="change-requests-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <div class="page-title">审批中心</div>
            <div class="page-subtitle">
              {{ authStore.isAdmin ? '管理员可审批全部变更单' : '查看并跟踪我的变更申请' }}
            </div>
          </div>
          <el-button type="primary" :loading="loading" @click="fetchChangeRequests">刷新</el-button>
        </div>
      </template>

      <el-form :inline="true" class="filter-bar">
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部状态" style="width: 180px">
            <el-option label="待审批" value="pending_approval" />
            <el-option label="执行成功" value="succeeded" />
            <el-option label="已拒绝" value="rejected" />
            <el-option label="执行失败" value="failed" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
        </el-form-item>
        <el-form-item label="操作">
          <el-select v-model="filters.operation_type" clearable placeholder="全部操作" style="width: 180px">
            <el-option label="DNS 新增" value="dns_create" />
            <el-option label="DNS 更新" value="dns_update" />
            <el-option label="DNS 删除" value="dns_delete" />
            <el-option label="批量 DNS" value="batch_dns_update" />
            <el-option label="批量 NS" value="batch_nameserver_update" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input
            v-model="filters.keyword"
            clearable
            placeholder="申请单号/申请人/操作"
            style="width: 220px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">筛选</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="requests" stripe style="width: 100%">
        <el-table-column prop="request_no" label="申请单号" width="140" />
        <el-table-column prop="operation_type" label="操作" width="160">
          <template #default="{ row }">
            <el-tag size="small">{{ row.operation_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="requester_name" label="申请人" width="130">
          <template #default="{ row }">{{ row.requester_name || row.requester_user_id }}</template>
        </el-table-column>
        <el-table-column prop="domain_id" label="域名ID" width="90" />
        <el-table-column prop="risk_level" label="风险" width="90">
          <template #default="{ row }">
            <el-tag :type="riskTagType(row.risk_level)" size="small">{{ row.risk_level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="140">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="280">
          <template #default="{ row }">
            <div class="summary-block">
              <div class="summary-line">目标: {{ summarizeTarget(row) }}</div>
              <div class="summary-line monospace">{{ compactPayload(row.payload) }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <div class="action-row">
              <el-button
                v-if="authStore.isAdmin && row.status === 'pending_approval'"
                size="small"
                type="success"
                :loading="actionLoadingId === row.id && actionType === 'approve'"
                @click="handleApprove(row.id)"
              >
                批准
              </el-button>
              <el-button
                v-if="authStore.isAdmin && row.status === 'pending_approval'"
                size="small"
                type="danger"
                :loading="actionLoadingId === row.id && actionType === 'reject'"
                @click="openRejectDialog(row.id)"
              >
                拒绝
              </el-button>
              <el-button
                v-if="!authStore.isAdmin && row.status === 'pending_approval'"
                size="small"
                :loading="actionLoadingId === row.id && actionType === 'cancel'"
                @click="handleCancel(row.id)"
              >
                撤销
              </el-button>
              <el-button size="small" @click="openDetail(row)">详情</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          layout="total, sizes, prev, pager, next"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          @current-change="fetchChangeRequests"
          @size-change="handlePageSizeChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="detailVisible" title="变更单详情" width="760px">
      <template v-if="currentRequest">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="申请单号">{{ currentRequest.request_no }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ currentRequest.status }}</el-descriptions-item>
          <el-descriptions-item label="操作类型">{{ currentRequest.operation_type }}</el-descriptions-item>
          <el-descriptions-item label="审批人">{{ currentRequest.approver_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="申请人">
            {{ currentRequest.requester_name || currentRequest.requester_user_id }}
          </el-descriptions-item>
          <el-descriptions-item label="风险等级">{{ currentRequest.risk_level }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(currentRequest.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="执行时间">{{ formatTime(currentRequest.executed_at) }}</el-descriptions-item>
        </el-descriptions>

        <div class="detail-section">
          <div class="detail-title">请求载荷</div>
          <pre class="json-box">{{ prettyJson(currentRequest.payload) }}</pre>
        </div>
        <div class="detail-section">
          <div class="detail-title">执行结果</div>
          <pre class="json-box">{{ prettyJson(currentRequest.execution_result) }}</pre>
        </div>
        <div class="detail-section" v-if="currentRequest.rejection_reason || currentRequest.error_message">
          <div class="detail-title">错误/拒绝原因</div>
          <div class="error-box">{{ currentRequest.rejection_reason || currentRequest.error_message }}</div>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="rejectVisible" title="拒绝变更单" width="460px">
      <el-form label-width="80px">
        <el-form-item label="原因">
          <el-input
            v-model="rejectReason"
            type="textarea"
            :rows="4"
            maxlength="200"
            show-word-limit
            placeholder="请输入拒绝原因"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectVisible = false">取消</el-button>
        <el-button
          type="danger"
          :loading="actionLoadingId === rejectTargetId && actionType === 'reject'"
          @click="handleReject"
        >
          确认拒绝
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'
import {
  approveChangeRequest,
  cancelChangeRequest,
  getChangeRequests,
  rejectChangeRequest,
  type ChangeRequest,
} from '@/api/changeRequests'

const authStore = useAuthStore()
const loading = ref(false)
const requests = ref<ChangeRequest[]>([])
const filters = ref({
  status: '',
  operation_type: '',
  keyword: '',
})
const pagination = ref({
  page: 1,
  page_size: 20,
  total: 0,
})
const detailVisible = ref(false)
const currentRequest = ref<ChangeRequest | null>(null)
const rejectVisible = ref(false)
const rejectTargetId = ref<number | null>(null)
const rejectReason = ref('')
const actionLoadingId = ref<number | null>(null)
const actionType = ref('')

function formatTime(value: string | null) {
  return formatDateTime(value)
}

function prettyJson(value: Record<string, any> | null | undefined) {
  return JSON.stringify(value || {}, null, 2)
}

function compactPayload(value: Record<string, any>) {
  const raw = JSON.stringify(value || {})
  return raw.length > 96 ? `${raw.slice(0, 96)}...` : raw
}

function summarizeTarget(row: ChangeRequest) {
  return row.target_id ? `${row.target_type} #${row.target_id}` : row.target_type
}

function statusTagType(status: string) {
  const mapping: Record<string, string> = {
    pending_approval: 'warning',
    approved: 'primary',
    rejected: 'danger',
    executing: 'primary',
    succeeded: 'success',
    failed: 'danger',
    cancelled: 'info',
  }
  return mapping[status] || 'info'
}

function riskTagType(level: string) {
  const mapping: Record<string, string> = {
    low: 'success',
    medium: 'warning',
    high: 'danger',
  }
  return mapping[level] || 'info'
}

async function fetchChangeRequests() {
  loading.value = true
  try {
    const { data } = await getChangeRequests({
      page: pagination.value.page,
      page_size: pagination.value.page_size,
      status: filters.value.status || undefined,
      operation_type: filters.value.operation_type || undefined,
      keyword: filters.value.keyword.trim() || undefined,
    })
    requests.value = data.items || []
    pagination.value.total = data.total
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '获取变更单失败')
    requests.value = []
    pagination.value.total = 0
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.value.page = 1
  fetchChangeRequests()
}

function resetFilters() {
  filters.value.status = ''
  filters.value.operation_type = ''
  filters.value.keyword = ''
  pagination.value.page = 1
  fetchChangeRequests()
}

function handlePageSizeChange() {
  pagination.value.page = 1
  fetchChangeRequests()
}

function openDetail(row: ChangeRequest) {
  currentRequest.value = row
  detailVisible.value = true
}

function openRejectDialog(requestId: number) {
  rejectTargetId.value = requestId
  rejectReason.value = ''
  rejectVisible.value = true
}

async function handleApprove(requestId: number) {
  actionLoadingId.value = requestId
  actionType.value = 'approve'
  try {
    await approveChangeRequest(requestId)
    ElMessage.success('审批完成')
    await fetchChangeRequests()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '审批失败')
  } finally {
    actionLoadingId.value = null
    actionType.value = ''
  }
}

async function handleReject() {
  if (!rejectTargetId.value) return
  if (!rejectReason.value.trim()) {
    ElMessage.warning('请输入拒绝原因')
    return
  }
  actionLoadingId.value = rejectTargetId.value
  actionType.value = 'reject'
  try {
    await rejectChangeRequest(rejectTargetId.value, rejectReason.value.trim())
    ElMessage.success('已拒绝该变更单')
    rejectVisible.value = false
    await fetchChangeRequests()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '拒绝失败')
  } finally {
    actionLoadingId.value = null
    actionType.value = ''
  }
}

async function handleCancel(requestId: number) {
  actionLoadingId.value = requestId
  actionType.value = 'cancel'
  try {
    await cancelChangeRequest(requestId)
    ElMessage.success('已撤销变更单')
    await fetchChangeRequests()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '撤销失败')
  } finally {
    actionLoadingId.value = null
    actionType.value = ''
  }
}

onMounted(() => {
  fetchChangeRequests()
})
</script>

<style scoped>
.change-requests-page {
  width: 100%;
  padding-bottom: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
}

.page-subtitle {
  margin-top: 4px;
  color: #7a869a;
  font-size: 13px;
}

.filter-bar {
  margin-bottom: 16px;
}

.summary-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-line {
  color: #3d4a5c;
}

.monospace {
  font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
  font-size: 12px;
  color: #5b6472;
}

.action-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pagination-bar {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.detail-section {
  margin-top: 16px;
}

.detail-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
}

.json-box {
  margin: 0;
  padding: 12px;
  border-radius: 10px;
  background: #0f172a;
  color: #dbeafe;
  overflow-x: auto;
  font-size: 12px;
}

.error-box {
  padding: 12px;
  border-radius: 10px;
  background: #fff1f2;
  color: #be123c;
}
</style>
