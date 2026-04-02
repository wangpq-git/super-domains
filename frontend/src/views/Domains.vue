<template>
  <div class="domains-container">
    <el-card shadow="never" class="filter-card" style="margin-bottom: 0;">
      <el-form :inline="true" :model="store.filters" @submit.prevent>
        <el-form-item label="平台">
          <el-select v-model="store.filters.platform" placeholder="全部平台" clearable style="width: 160px" @change="handleFilter">
            <el-option v-for="p in platforms" :key="p" :label="platformLabel(p)" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="store.filters.status" placeholder="全部状态" clearable style="width: 120px" @change="handleFilter">
            <el-option label="活跃" value="active" />
            <el-option label="已过期" value="expired" />
            <el-option label="待续费" value="pending" />
          </el-select>
        </el-form-item>
        <el-form-item label="到期日期">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 240px"
            @change="handleDateChange"
          />
        </el-form-item>
        <el-form-item label="搜索">
          <el-input v-model="store.filters.search" placeholder="域名搜索" clearable style="width: 180px" @clear="handleFilter" @keyup.enter="handleFilter">
            <template #append><el-button :icon="Search" @click="handleFilter" /></template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <div v-if="selectedDomains.length > 0" class="batch-bar">
        <span class="batch-info">已选择 {{ selectedDomains.length }} 项</span>
        <el-button type="primary" :loading="batchLoading" @click="handleBatchSync">批量同步</el-button>
        <el-button v-if="authStore.isAdmin" type="warning" :loading="batchLoading" @click="showNsDialog = true">批量修改NS</el-button>
        <el-button @click="clearSelection">取消选择</el-button>
      </div>

      <div class="export-bar">
        <el-button :icon="Refresh" circle @click="handleRefresh" />
        <el-button :icon="Download" @click="handleExportCsv">导出CSV</el-button>
        <el-button :icon="Download" @click="handleExportXlsx">导出Excel</el-button>
      </div>

      <el-table
        ref="tableRef"
        v-loading="store.loading"
        :data="store.domains"
        stripe
        size="small"
        :row-style="{ height: '44px' }"
        style="width: 100%"
        @selection-change="handleSelectionChange"
        @sort-change="handleSortChange"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column prop="domain_name" label="域名" min-width="200" show-overflow-tooltip sortable="custom">
          <template #default="{ row }">
            <a class="domain-link" @click="gotoDns(row)">{{ row.domain_name }}</a>
          </template>
        </el-table-column>
        <el-table-column prop="platform" label="平台" width="130">
          <template #default="{ row }">
            <el-tag :type="platformTagType(row.platform)" size="small">{{ platformLabel(row.platform) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="account" label="账户" width="150" show-overflow-tooltip />
        <el-table-column prop="expiry_date" label="到期日期" width="120" sortable="custom">
          <template #default="{ row }">
            <span :class="expiryClass(row.expiry_date)">{{ formatDate(row.expiry_date) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" sortable="custom">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="NS记录" min-width="200">
          <template #default="{ row }">
            <div v-if="row.nameservers && row.nameservers.length" class="ns-list">
              <el-tag v-for="ns in row.nameservers.slice(0, 2)" :key="ns" size="small" type="info" class="ns-tag">{{ ns }}</el-tag>
              <el-tooltip v-if="row.nameservers.length > 2" :content="row.nameservers.join('\n')" placement="top" raw-content>
                <el-tag size="small" type="info">+{{ row.nameservers.length - 2 }}</el-tag>
              </el-tooltip>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="auto_renew" label="自动续费" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.auto_renew" type="success" size="small">开启</el-tag>
            <el-tag v-else type="info" size="small">关闭</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="store.filters.page"
          v-model:page-size="store.filters.page_size"
          :total="store.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="handleSizeChange"
          @current-change="store.fetchDomains()"
        />
      </div>
    </el-card>

    <el-dialog v-model="showNsDialog" title="批量修改 Nameservers" width="500px">
      <el-form label-width="100px">
        <el-form-item v-for="(_, idx) in nsForm" :key="idx" :label="`NS${idx + 1}`">
          <div style="display: flex; align-items: center; gap: 8px;">
            <el-input v-model="nsForm[idx]" placeholder="ns1.example.com" />
            <el-button v-if="nsForm.length > 2" :icon="Delete" type="danger" circle size="small" @click="removeNs(idx)" />
          </div>
        </el-form-item>
        <el-form-item>
          <el-button @click="addNs">+ 添加 NS</el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showNsDialog = false">取消</el-button>
        <el-button type="primary" :loading="batchLoading" @click="handleBatchNs">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Download, Delete, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { ElTable } from 'element-plus'
import { useDomainsStore } from '@/stores/domains'
import { useAuthStore } from '@/stores/auth'
import { batchUpdateNameservers, batchUpdateDns, batchSyncAccounts, exportDomainsCsv, exportDomainsXlsx } from '@/api/batch'
import { platformLabel, platformTagType, formatDate } from '@/utils/format'

interface DomainRow {
  id: number
  domain_name: string
  platform: string
  account: string
  account_id: number
  [key: string]: any
}

const router = useRouter()
const store = useDomainsStore()
const authStore = useAuthStore()
const dateRange = ref<string[]>([])
const tableRef = ref<InstanceType<typeof ElTable>>()
const selectedDomains = ref<DomainRow[]>([])
const batchLoading = ref(false)
const showNsDialog = ref(false)
const nsForm = reactive<string[]>(['', ''])

const platforms = ['cloudflare', 'namecom', 'dynadot', 'godaddy', 'namecheap', 'namesilo', 'openprovider', 'porkbun', 'spaceship']

function handleSelectionChange(rows: DomainRow[]) {
  selectedDomains.value = rows
}

function clearSelection() {
  tableRef.value?.clearSelection()
}

function addNs() {
  nsForm.push('')
}

function removeNs(idx: number) {
  nsForm.splice(idx, 1)
}

function statusLabel(status: string): string {
  const map: Record<string, string> = { active: '正常', expired: '已过期', pending: '待处理', locked: '已锁定', removed: '已移除' }
  return map[status] ?? status
}

function statusTagType(status: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = { active: 'success', expired: 'danger', pending: 'info', locked: 'warning', removed: 'info' }
  return map[status] ?? 'info'
}

function expiryClass(dateStr: string): string {
  if (!dateStr) return ''
  const diff = Math.ceil((new Date(dateStr).getTime() - Date.now()) / 86400000)
  if (diff < 0) return 'expiry-expired'
  if (diff <= 7) return 'expiry-danger'
  if (diff <= 30) return 'expiry-warning'
  return 'expiry-safe'
}

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  window.URL.revokeObjectURL(url)
}

async function handleExportCsv() {
  try {
    const res = await exportDomainsCsv()
    downloadBlob(res.data as Blob, 'domains.csv')
    ElMessage.success('CSV导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

async function handleExportXlsx() {
  try {
    const res = await exportDomainsXlsx()
    downloadBlob(res.data as Blob, 'domains.xlsx')
    ElMessage.success('Excel导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

async function handleBatchSync() {
  const accountIds = [...new Set(selectedDomains.value.map(d => d.account_id))]
  if (!accountIds.length) {
    ElMessage.warning('请选择域名')
    return
  }
  batchLoading.value = true
  try {
    const res = await batchSyncAccounts(accountIds)
    const results = (res.data as any).results || []
    const success = results.filter((r: any) => r.status === 'syncing').length
    const failed = results.filter((r: any) => r.status === 'error').length
    ElMessage.success(`同步已触发：成功 ${success}，失败 ${failed}`)
    clearSelection()
  } catch {
    ElMessage.error('批量同步失败')
  } finally {
    batchLoading.value = false
  }
}

async function handleBatchNs() {
  const nameservers = nsForm.filter(ns => ns.trim())
  if (nameservers.length < 2) {
    ElMessage.warning('请至少填写2个Nameserver')
    return
  }
  const domainIds = selectedDomains.value.map(d => d.id)
  batchLoading.value = true
  try {
    const res = await batchUpdateNameservers(domainIds, nameservers)
    const results = (res.data as any).results || []
    const success = results.filter((r: any) => r.status === 'success').length
    const failed = results.filter((r: any) => r.status === 'error').length
    ElMessage.success(`NS修改完成：成功 ${success}，失败 ${failed}`)
    showNsDialog.value = false
    clearSelection()
    store.fetchDomains()
  } catch {
    ElMessage.error('批量修改NS失败')
  } finally {
    batchLoading.value = false
  }
}

function handleSortChange({ prop, order }: { prop: string; order: string | null }) {
  if (order) {
    store.filters.sort_by = prop
    store.filters.sort_order = order === 'ascending' ? 'asc' : 'desc'
  } else {
    store.filters.sort_by = 'expiry_date'
    store.filters.sort_order = 'asc'
  }
  store.filters.page = 1
  store.fetchDomains()
}

function handleRefresh() {
  store.fetchDomains()
}

function handleDateChange(val: string[] | null) {
  store.filters.expiry_start = val?.[0] ?? ''
  store.filters.expiry_end = val?.[1] ?? ''
  store.filters.page = 1
  store.fetchDomains()
}

function handleSizeChange() {
  store.filters.page = 1
  store.fetchDomains()
}

function handleFilter() {
  store.filters.page = 1
  store.fetchDomains()
}

function handleReset() {
  dateRange.value = []
  store.resetFilters()
  store.fetchDomains()
}

function gotoDns(row: DomainRow) {
  router.push({ path: '/dns', query: { domain: row.domain_name, domain_id: String(row.id), auto_sync: '1' } })
}

onMounted(() => {
  store.fetchDomains()
})
</script>

<style scoped>
.domains-container {
  width: 100%;
}

.filter-card {
  margin-bottom: 0;
  border-radius: 8px !important;
}

.filter-card :deep(.el-card__body) {
  padding: 16px 20px;
}

.filter-card :deep(.el-form-item) {
  margin-bottom: 0;
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  padding: 10px 16px;
  background: linear-gradient(135deg, #eff6ff 0%, #eef2ff 100%);
  border-radius: 8px;
  border: 1px solid #dbeafe;
}

.batch-info {
  font-size: 13px;
  color: #4361ee;
  font-weight: 600;
  margin-right: 8px;
}

.export-bar {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-bottom: 14px;
}

.expiry-safe { color: #10b981; font-weight: 500; }
.expiry-warning { color: #f59e0b; font-weight: 600; }
.expiry-danger { color: #ef4444; font-weight: 600; }
.expiry-expired { color: #ef4444; font-weight: 600; text-decoration: line-through; }

.ns-list { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.ns-tag { max-width: 180px; overflow: hidden; text-overflow: ellipsis; }
.domain-link {
  color: #4361ee;
  cursor: pointer;
  text-decoration: none;
}
.domain-link:hover {
  text-decoration: underline;
}
.text-muted { color: #c0c4cc; }

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #f0f0f0;
}
</style>
