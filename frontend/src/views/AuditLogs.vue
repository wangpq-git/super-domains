<template>
  <div class="audit-logs-page page-stack">
    <PageHero
      eyebrow="AUDIT CENTER"
      title="日志中心"
      subtitle="统一记录用户操作和域名修改轨迹，支持按范围、动作和关键词快速回溯。"
      tone="blue"
    >
      <template #meta>
        <el-tag effect="plain" round>总计 {{ pagination.total }}</el-tag>
        <el-tag effect="plain" round type="success">域名修改 {{ domainCount }}</el-tag>
      </template>
      <div class="hero-metrics">
        <span>当前页 {{ logs.length }}</span>
        <span>操作日志 {{ operationCount }}</span>
        <span>最近动作 {{ latestAction }}</span>
      </div>
      <template #actions>
        <el-button type="primary" :loading="loading" @click="fetchLogs(true)">刷新</el-button>
      </template>
    </PageHero>

    <el-card shadow="never" class="data-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="page-title">审计日志</div>
            <div class="page-subtitle">操作日志和域名修改记录共用一套检索入口，管理员可查看全部，普通用户仅查看自己的记录。</div>
          </div>
          <el-segmented v-model="scope" :options="scopeOptions" />
        </div>
      </template>

      <el-form :inline="true" class="filter-bar">
        <el-form-item label="动作">
          <el-select v-model="filters.action" clearable filterable placeholder="全部动作" style="width: 220px">
            <el-option v-for="item in actionOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标类型">
          <el-select v-model="filters.target_type" clearable placeholder="全部目标" style="width: 160px">
            <el-option label="域名" value="domain" />
            <el-option label="DNS记录" value="dns_record" />
            <el-option label="账户" value="platform_account" />
            <el-option label="用户" value="user" />
            <el-option label="变更单" value="change_request" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input
            v-model="filters.keyword"
            clearable
            placeholder="操作人 / 动作 / 域名"
            style="width: 240px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">筛选</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="logs" stripe style="width: 100%">
        <el-table-column label="时间" width="176">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作人" width="120">
          <template #default="{ row }">{{ row.actor_name || row.user_id || '系统' }}</template>
        </el-table-column>
        <el-table-column label="动作" width="210">
          <template #default="{ row }">
            <el-tag :type="actionTagType(row.action)" effect="plain">{{ actionLabel(row.action) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="域名" min-width="180">
          <template #default="{ row }">{{ row.domain_name || extractDomainName(row.detail) || '-' }}</template>
        </el-table-column>
        <el-table-column label="目标" width="140">
          <template #default="{ row }">{{ targetLabel(row.target_type) }}</template>
        </el-table-column>
        <el-table-column label="摘要" min-width="320">
          <template #default="{ row }">
            <div class="summary-block">
              <div class="summary-line">{{ summarizeDetail(row) }}</div>
              <div v-if="row.detail?.change_request_no" class="summary-line summary-line--muted">
                变更单 {{ row.detail.change_request_no }}
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)">详情</el-button>
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
          @current-change="fetchLogs"
          @size-change="handlePageSizeChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="detailVisible" title="日志详情" width="820px">
      <template v-if="currentLog">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="时间">{{ formatDateTime(currentLog.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="操作人">{{ currentLog.actor_name || currentLog.user_id || '系统' }}</el-descriptions-item>
          <el-descriptions-item label="动作">{{ actionLabel(currentLog.action) }}</el-descriptions-item>
          <el-descriptions-item label="目标">{{ targetLabel(currentLog.target_type) }}</el-descriptions-item>
          <el-descriptions-item label="域名">{{ currentLog.domain_name || extractDomainName(currentLog.detail) || '-' }}</el-descriptions-item>
          <el-descriptions-item label="目标 ID">{{ currentLog.target_id ?? '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="detail-section" v-if="detailCompare.before || detailCompare.after">
          <div class="detail-title">变更对比</div>
          <div class="compare-grid">
            <div class="compare-box">
              <div class="compare-box__title">变更前</div>
              <pre class="json-box">{{ prettyJson(detailCompare.before) }}</pre>
            </div>
            <div class="compare-box">
              <div class="compare-box__title">变更后</div>
              <pre class="json-box">{{ prettyJson(detailCompare.after) }}</pre>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-title">原始日志</div>
          <pre class="json-box">{{ prettyJson(currentLog.detail) }}</pre>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import PageHero from '@/components/PageHero.vue'
import { getAuditLogs, type AuditLogItem } from '@/api/auditLogs'
import { formatDateTime } from '@/utils/format'

const loading = ref(false)
const logs = ref<AuditLogItem[]>([])
const scope = ref<'all' | 'operation' | 'domain'>('all')
const filters = ref({
  action: '',
  target_type: '',
  keyword: '',
})
const pagination = ref({
  page: 1,
  page_size: 20,
  total: 0,
})
const detailVisible = ref(false)
const currentLog = ref<AuditLogItem | null>(null)

const scopeOptions = [
  { label: '全部', value: 'all' },
  { label: '操作日志', value: 'operation' },
  { label: '域名修改', value: 'domain' },
]

const actionOptions = [
  { label: '登录', value: 'auth.login' },
  { label: '修改密码', value: 'auth.password_change' },
  { label: '用户更新', value: 'user.update' },
  { label: '账户创建', value: 'platform.create' },
  { label: '账户更新', value: 'platform.update' },
  { label: '账户删除', value: 'platform.delete' },
  { label: '账户同步', value: 'platform.sync' },
  { label: '批量同步', value: 'platform.batch_sync' },
  { label: 'DNS新增', value: 'dns.create' },
  { label: 'DNS修改', value: 'dns.update' },
  { label: 'DNS删除', value: 'dns.delete' },
  { label: '批量DNS', value: 'dns.batch_update' },
  { label: 'NS修改', value: 'domain.nameserver_update' },
  { label: 'Cloudflare接入', value: 'domain.cloudflare_onboard' },
  { label: '审批通过', value: 'change_request.approve' },
  { label: '审批拒绝', value: 'change_request.reject' },
  { label: '审批取消', value: 'change_request.cancel' },
]

const domainCount = computed(() => logs.value.filter((item) => item.action.startsWith('dns.') || item.action.startsWith('domain.')).length)
const operationCount = computed(() => logs.value.length - domainCount.value)
const latestAction = computed(() => (logs.value[0] ? actionLabel(logs.value[0].action) : '暂无'))
const detailCompare = computed(() => ({
  before: currentLog.value?.detail?.before || null,
  after: currentLog.value?.detail?.after || null,
}))

watch(scope, () => {
  pagination.value.page = 1
  fetchLogs(true)
})

onMounted(() => {
  fetchLogs()
})

async function fetchLogs(force = false) {
  loading.value = true
  try {
    const { data } = await getAuditLogs(
      {
        page: pagination.value.page,
        page_size: pagination.value.page_size,
        keyword: filters.value.keyword || undefined,
        action: filters.value.action || undefined,
        target_type: filters.value.target_type || undefined,
        scope: scope.value,
      },
      force,
    )
    logs.value = data.items
    pagination.value.total = data.total
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '日志加载失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.value.page = 1
  fetchLogs(true)
}

function resetFilters() {
  filters.value = {
    action: '',
    target_type: '',
    keyword: '',
  }
  pagination.value.page = 1
  fetchLogs(true)
}

function handlePageSizeChange() {
  pagination.value.page = 1
  fetchLogs(true)
}

function openDetail(row: AuditLogItem) {
  currentLog.value = row
  detailVisible.value = true
}

function extractDomainName(detail?: Record<string, any>) {
  return detail?.domain_name || detail?.domain?.domain_name || detail?.payload?.domain_name || null
}

function actionLabel(action: string) {
  return actionOptions.find((item) => item.value === action)?.label || action
}

function actionTagType(action: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  if (action.startsWith('dns.') || action.startsWith('domain.')) return 'success'
  if (action.startsWith('change_request.')) return 'warning'
  if (action.startsWith('auth.')) return 'info'
  return ''
}

function targetLabel(targetType: string | null) {
  const map: Record<string, string> = {
    domain: '域名',
    dns_record: 'DNS记录',
    platform_account: '账户',
    user: '用户',
    change_request: '变更单',
  }
  return targetType ? map[targetType] || targetType : '-'
}

function summarizeDetail(row: AuditLogItem) {
  const detail = row.detail || {}
  if (detail.status === 'error' && detail.message) return `执行失败：${detail.message}`
  if (detail.status === 'success' && detail.after?.nameservers) return `NS 已更新为 ${detail.after.nameservers.join(', ')}`
  if (detail.after?.content) return `${detail.after.record_type || ''} ${detail.after.name || '@'} -> ${detail.after.content}`.trim()
  if (detail.after?.account_name) return `切换到 ${detail.after.account_name}`
  if (detail.before || detail.after) return '包含变更前后快照，可展开查看详情'
  if (detail.account_name) return `${detail.platform || '-'} / ${detail.account_name}`
  if (detail.record_count) return `涉及 ${detail.record_count} 条记录`
  return '查看详情获取完整上下文'
}

function prettyJson(value: Record<string, any> | null | undefined) {
  try {
    return JSON.stringify(value || {}, null, 2)
  } catch {
    return '{}'
  }
}
</script>

<style scoped>
.audit-logs-page {
  gap: 20px;
}

.hero-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  color: rgba(255, 255, 255, 0.84);
  font-size: 13px;
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 18px;
  font-weight: 700;
  color: #102a43;
}

.page-subtitle {
  margin-top: 6px;
  color: #6b7c93;
  font-size: 13px;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 0;
  margin-bottom: 18px;
}

.summary-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-line {
  color: #243b53;
  line-height: 1.55;
}

.summary-line--muted {
  color: #829ab1;
  font-size: 12px;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

.detail-section {
  margin-top: 18px;
}

.detail-title,
.compare-box__title {
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 700;
  color: #102a43;
}

.compare-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.compare-box,
.json-box {
  border-radius: 16px;
  background: #0f172a;
  color: #dbeafe;
}

.compare-box {
  padding: 14px;
}

.json-box {
  margin: 0;
  padding: 16px;
  max-height: 320px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 900px) {
  .compare-grid {
    grid-template-columns: 1fr;
  }
}
</style>
