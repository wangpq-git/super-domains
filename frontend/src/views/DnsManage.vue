<template>
  <div class="dns-manage">
    <el-card shadow="never" class="selector-card">
      <el-form :inline="true">
        <el-form-item label="选择域名">
          <el-select
            v-model="selectedDomainId"
            placeholder="输入域名搜索"
            filterable
            remote
            :remote-method="handleSearch"
            clearable
            :loading="searchLoading"
            style="width: 360px"
            @change="handleDomainChange"
          >
            <el-option
              v-for="d in domainList"
              :key="d.id"
              :label="d.domain_name"
              :value="d.id"
            >
              <span>{{ d.domain_name }}</span>
              <el-tag size="small" style="margin-left: 8px">{{ d.platform }}</el-tag>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button :icon="Refresh" circle :disabled="!selectedDomainId" @click="fetchRecords" />
          <el-button type="primary" :icon="Refresh" :loading="syncing" :disabled="!selectedDomainId" @click="handleSync">同步记录</el-button>
          <el-button v-if="authStore.isAdmin" type="success" :icon="Plus" :disabled="!selectedDomainId" @click="openDialog()">添加记录</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <template v-if="selectedDomainId">
        <el-table v-if="records.length > 0 || loading" v-loading="loading" :data="records" stripe style="width: 100%" @sort-change="handleSortChange">
          <el-table-column prop="record_type" label="类型" width="90" sortable="custom">
            <template #default="{ row }">
              <el-tag :type="recordTypeTag(row.record_type)" size="small">{{ row.record_type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip sortable="custom" />
          <el-table-column prop="content" label="内容" min-width="250" show-overflow-tooltip sortable="custom" />
          <el-table-column prop="ttl" label="TTL" width="90" align="center" sortable="custom" />
          <el-table-column prop="priority" label="优先级" width="80" align="center">
            <template #default="{ row }">{{ row.priority ?? '-' }}</template>
          </el-table-column>
          <el-table-column prop="proxied" label="代理" width="70" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.proxied" type="warning" size="small">开</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="sync_status" label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.sync_status === 'synced'" type="success" size="small">已同步</el-tag>
              <el-tag v-else type="info" size="small">{{ row.sync_status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button v-if="authStore.isAdmin" size="small" type="primary" :icon="Edit" @click="openDialog(row)">编辑</el-button>
              <el-popconfirm v-if="authStore.isAdmin" title="确定删除该DNS记录吗？" @confirm="handleDelete(row)">
                <template #reference>
                  <el-button size="small" type="danger" :icon="Delete">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="该域名暂无 DNS 记录" :image-size="80">
          <el-button type="primary" :icon="Refresh" :loading="syncing" @click="handleSync">从平台同步记录</el-button>
        </el-empty>
      </template>
      <el-empty v-else description="请先选择域名" :image-size="100" />
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑DNS记录' : '添加DNS记录'" width="520px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="记录类型" prop="record_type">
          <el-select v-model="form.record_type" placeholder="选择类型" style="width: 100%" :disabled="isEdit">
            <el-option v-for="t in recordTypes" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如 @ 或 www" :disabled="isEdit" />
        </el-form-item>
        <el-form-item label="内容" prop="content">
          <el-input v-model="form.content" placeholder="记录值" />
        </el-form-item>
        <el-form-item label="TTL" prop="ttl">
          <el-input-number v-model="form.ttl" :min="60" :max="86400" :step="60" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="showPriority" label="优先级" prop="priority">
          <el-input-number v-model="form.priority" :min="0" :max="65535" style="width: 100%" />
        </el-form-item>
        <el-form-item label="代理" prop="proxied">
          <el-switch v-model="form.proxied" />
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
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { Plus, Edit, Delete, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { getDomains } from '@/api/domains'
import {
  getDnsRecords,
  createDnsRecord,
  updateDnsRecord,
  deleteDnsRecord,
  syncDnsRecords,
} from '@/api/dns'
import type { DnsRecord } from '@/api/dns'

const authStore = useAuthStore()
const domainList = ref<any[]>([])
const selectedDomainId = ref<number | null>(null)
const records = ref<DnsRecord[]>([])
const loading = ref(false)
const syncing = ref(false)
const searchLoading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref<number | null>(null)
const submitting = ref(false)
const formRef = ref<FormInstance>()

const dnsSortBy = ref('record_type')
const dnsSortOrder = ref('asc')

const recordTypes = ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV', 'CAA']

const defaultForm = { record_type: 'A', name: '', content: '', ttl: 3600, priority: 0, proxied: false }
const form = ref({ ...defaultForm })

const showPriority = computed(() => ['MX', 'SRV'].includes(form.value.record_type))

const rules = {
  record_type: [{ required: true, message: '请选择记录类型', trigger: 'change' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  content: [{ required: true, message: '请输入内容', trigger: 'blur' }],
}

function recordTypeTag(type: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
    A: 'success',
    AAAA: 'success',
    CNAME: '',
    MX: 'warning',
    TXT: 'info',
    NS: 'info',
    SRV: 'warning',
    CAA: 'danger',
  }
  return map[type] ?? ''
}

async function fetchDomains(search?: string) {
  try {
    const params: any = { page: 1, page_size: 50 }
    if (search) params.search = search
    const { data } = await getDomains(params)
    domainList.value = data.items ?? data.data ?? []
  } catch {
    domainList.value = []
  }
}

async function handleSearch(query: string) {
  if (!query) {
    domainList.value = []
    return
  }
  searchLoading.value = true
  try {
    await fetchDomains(query)
  } finally {
    searchLoading.value = false
  }
}

async function fetchRecords() {
  if (!selectedDomainId.value) return
  loading.value = true
  try {
    const { data } = await getDnsRecords(selectedDomainId.value, { sort_by: dnsSortBy.value, sort_order: dnsSortOrder.value })
    records.value = data ?? []
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '获取DNS记录失败')
    records.value = []
  } finally {
    loading.value = false
  }
}

function handleSortChange({ prop, order }: { prop: string; order: string | null }) {
  if (order) {
    dnsSortBy.value = prop
    dnsSortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  } else {
    dnsSortBy.value = 'record_type'
    dnsSortOrder.value = 'asc'
  }
  fetchRecords()
}

function handleDomainChange() {
  records.value = []
  if (selectedDomainId.value) {
    fetchRecords()
  }
}

async function handleSync() {
  if (!selectedDomainId.value) return
  syncing.value = true
  try {
    const { data } = await syncDnsRecords(selectedDomainId.value)
    if (data.error) {
      ElMessage.warning(`同步完成，但有错误：${data.error}`)
    } else {
      ElMessage.success(`同步完成：更新 ${data.upserted} 条，移除 ${data.removed} 条`)
    }
    await fetchRecords()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '同步失败')
  } finally {
    syncing.value = false
  }
}

function openDialog(row?: DnsRecord) {
  isEdit.value = !!row
  editId.value = row?.id ?? null
  if (row) {
    form.value = {
      record_type: row.record_type,
      name: row.name,
      content: row.content,
      ttl: row.ttl,
      priority: row.priority ?? 0,
      proxied: row.proxied ?? false,
    }
  } else {
    form.value = { ...defaultForm }
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value?.validate()
  submitting.value = true
  try {
    if (isEdit.value && editId.value) {
      const payload: any = { content: form.value.content, ttl: form.value.ttl, proxied: form.value.proxied }
      if (showPriority.value) payload.priority = form.value.priority
      await updateDnsRecord(editId.value, payload)
      ElMessage.success('更新成功')
    } else {
      const payload: any = {
        record_type: form.value.record_type,
        name: form.value.name,
        content: form.value.content,
        ttl: form.value.ttl,
        proxied: form.value.proxied,
      }
      if (showPriority.value) payload.priority = form.value.priority
      await createDnsRecord(selectedDomainId.value!, payload)
      ElMessage.success('添加成功')
    }
    dialogVisible.value = false
    await fetchRecords()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row: DnsRecord) {
  try {
    await deleteDnsRecord(row.id)
    ElMessage.success('删除成功')
    await fetchRecords()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

onMounted(() => {
  fetchDomains()
})
</script>

<style scoped>
.dns-manage {
  width: 100%;
}

.selector-card {
  margin-bottom: 0;
}

:deep(.el-empty) {
  padding: 40px 0;
}
</style>
