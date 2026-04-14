<template>
  <div class="change-requests-page page-stack">
    <PageHero
      eyebrow="APPROVAL HUB"
      title="审批中心"
      :subtitle="authStore.isAdmin ? '统一查看、审批和追踪全部变更单，适合集中处理待审批和失败任务。' : '查看、撤销并跟踪我提交的变更申请。'"
      tone="green"
    >
      <template #meta>
        <el-tag effect="plain" round>待审批 {{ pendingCount }}</el-tag>
      </template>
      <div class="hero-metrics">
        <span>总数 {{ pagination.total }}</span>
        <span>成功 {{ successCount }}</span>
        <span>失败 {{ failedCount }}</span>
      </div>
      <template #actions>
        <el-button type="primary" :loading="loading" @click="fetchChangeRequests(true)">刷新</el-button>
      </template>
    </PageHero>

    <el-card shadow="never" class="filter-card data-card">
      <template #header>
        <div>
          <h3 class="section-title">筛选条件</h3>
          <p class="section-subtitle">按状态、操作类型和关键词快速定位目标申请单，适合批量审批前先做预检。</p>
        </div>
      </template>

      <el-form :inline="true" class="filter-bar">
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部状态" style="width: 180px">
            <el-option label="待审批" value="pending_approval" />
            <el-option label="已批准" value="approved" />
            <el-option label="执行中" value="executing" />
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
            <el-option label="接入 Cloudflare" value="cloudflare_onboard" />
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
    </el-card>

    <el-card shadow="never" class="data-card">
      <template #header>
        <div class="table-toolbar">
          <div>
            <h3 class="section-title">变更单列表</h3>
            <p class="section-subtitle">详情弹窗中可查看完整载荷、执行结果和审批处理状态。</p>
          </div>
          <el-tag type="info" effect="plain">当前 {{ requests.length }} 条</el-tag>
        </div>
      </template>

      <el-table v-loading="loading" :data="requests" stripe style="width: 100%">
        <el-table-column prop="request_no" label="申请单号" width="140" />
        <el-table-column prop="operation_type" label="操作" width="160">
          <template #default="{ row }">
            <el-tag size="small">{{ operationLabel(row.operation_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="requester_name" label="申请人" width="130">
          <template #default="{ row }">{{ row.requester_name || row.requester_user_id }}</template>
        </el-table-column>
        <el-table-column prop="domain_id" label="域名ID" width="90" />
        <el-table-column prop="risk_level" label="风险" width="90">
          <template #default="{ row }">
            <el-tag :type="riskTagType(row.risk_level)" size="small">{{ riskLabel(row.risk_level) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="140">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
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
          <el-descriptions-item label="状态">{{ statusLabel(currentRequest.status) }}</el-descriptions-item>
          <el-descriptions-item label="操作类型">{{ operationLabel(currentRequest.operation_type) }}</el-descriptions-item>
          <el-descriptions-item label="审批人">{{ currentRequest.approver_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="申请人">
            {{ currentRequest.requester_name || currentRequest.requester_user_id }}
          </el-descriptions-item>
          <el-descriptions-item label="风险等级">{{ riskLabel(currentRequest.risk_level) }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(currentRequest.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="执行时间">{{ formatTime(currentRequest.executed_at) }}</el-descriptions-item>
        </el-descriptions>

        <div class="detail-section">
          <div class="detail-title">处理状态</div>
          <div class="result-box" :class="resultBoxClass(currentRequest.status)">
            {{ requestOutcome(currentRequest) }}
          </div>
        </div>

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
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from '@/utils/message'
import PageHero from '@/components/PageHero.vue'
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
const pendingCount = computed(() => requests.value.filter((item) => item.status === 'pending_approval').length)
const successCount = computed(() => requests.value.filter((item) => item.status === 'succeeded').length)
const failedCount = computed(() => requests.value.filter((item) => item.status === 'failed').length)

function formatTime(value: string | null) {
  return formatDateTime(value)
}

function prettyJson(value: Record<string, any> | null | undefined) {
  try {
    return JSON.stringify(value || {}, null, 2)
  } catch {
    return '{}'
  }
}

function compactPayload(value: Record<string, any>) {
  const raw = JSON.stringify(value || {})
  return raw.length > 96 ? `${raw.slice(0, 96)}...` : raw
}

function operationLabel(operationType: string) {
  const mapping: Record<string, string> = {
    dns_create: 'DNS 新增',
    dns_update: 'DNS 修改',
    dns_delete: 'DNS 删除',
    batch_dns_update: '批量 DNS',
    batch_nameserver_update: '批量 NS',
    cloudflare_onboard: '接入 Cloudflare',
  }
  return mapping[operationType] || operationType
}

function summarizeTarget(row: ChangeRequest) {
  return row.target_id ? `${row.target_type} #${row.target_id}` : row.target_type
}

function statusLabel(status: string) {
  const mapping: Record<string, string> = {
    pending_approval: '待审批',
    approved: '已批准',
    rejected: '已拒绝',
    executing: '执行中',
    succeeded: '执行成功',
    failed: '执行失败',
    cancelled: '已取消',
  }
  return mapping[status] || status
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

function riskLabel(level: string) {
  const mapping: Record<string, string> = {
    low: '低',
    medium: '中',
    high: '高',
  }
  return mapping[level] || level
}

function requestOutcome(row: ChangeRequest) {
  if (row.status === 'failed') {
    return row.error_message ? `审批已通过，但执行失败：${row.error_message}` : '审批已通过，但执行失败'
  }
  if (row.status === 'succeeded') {
    return row.approver_name ? `已由 ${row.approver_name} 审批通过并执行成功` : '已审批通过并执行成功'
  }
  if (row.status === 'rejected') {
    return row.rejection_reason ? `审批已拒绝：${row.rejection_reason}` : '审批已拒绝'
  }
  if (row.status === 'executing') return '审批已通过，正在执行'
  if (row.status === 'approved') return '审批已通过，等待系统执行'
  if (row.status === 'cancelled') return '申请人已撤销该变更单'
  return '等待审批'
}

function resultBoxClass(status: string) {
  const mapping: Record<string, string> = {
    succeeded: 'result-box--success',
    failed: 'result-box--danger',
    rejected: 'result-box--danger',
    executing: 'result-box--info',
    approved: 'result-box--info',
    cancelled: 'result-box--muted',
    pending_approval: 'result-box--warning',
  }
  return mapping[status] || 'result-box--info'
}

async function fetchChangeRequests(force = false) {
  loading.value = true
  try {
    const { data } = await getChangeRequests({
      page: pagination.value.page,
      page_size: pagination.value.page_size,
      status: filters.value.status || undefined,
      operation_type: filters.value.operation_type || undefined,
      keyword: filters.value.keyword.trim() || undefined,
    }, force)
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
    const { data } = await approveChangeRequest(requestId)
    if (data.status === 'failed') {
      ElMessage.error(data.error_message || '审批已通过，但执行失败')
    } else if (data.status === 'succeeded') {
      ElMessage.success('审批通过，执行成功')
    } else {
      ElMessage.success(`审批完成，当前状态：${statusLabel(data.status)}`)
    }
    if (currentRequest.value?.id === data.id) {
      currentRequest.value = data
    }
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
}

.filter-card {
  border-radius: 18px !important;
}

.filter-card :deep(.el-card__body) {
  padding: 16px 20px;
}

.hero-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: rgba(255, 255, 255, 0.82);
  font-size: 13px;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 0;
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

.result-box {
  border-radius: 14px;
  padding: 14px 16px;
  font-size: 13px;
  line-height: 1.7;
}

.result-box--success {
  background: #ecfdf3;
  color: #0f766e;
}

.result-box--danger {
  background: #fef2f2;
  color: #b42318;
}

.result-box--info {
  background: #eef4ff;
  color: #1d4ed8;
}

.result-box--warning {
  background: #fff7e6;
  color: #b45309;
}

.result-box--muted {
  background: #f3f4f6;
  color: #4b5563;
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
