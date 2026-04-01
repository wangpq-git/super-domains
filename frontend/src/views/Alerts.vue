<template>
  <div class="alerts-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>告警规则管理</span>
          <div>
            <el-button type="warning" :icon="Bell" :loading="checking" @click="handleCheck">手动检查</el-button>
            <el-button type="primary" :icon="Plus" @click="openDialog()">添加规则</el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="rules" stripe style="width: 100%">
        <el-table-column prop="name" label="规则名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="rule_type" label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ ruleTypeLabel(row.rule_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="days_before" label="提前天数" width="100" align="center">
          <template #default="{ row }">{{ row.days_before ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="channels" label="通知渠道" width="200">
          <template #default="{ row }">
            <el-tag v-for="ch in (row.channels ?? [])" :key="ch" size="small" style="margin-right: 4px">{{ channelLabel(ch) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="apply_to_all" label="适用范围" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.apply_to_all" type="success" size="small">全部域名</el-tag>
            <el-tag v-else type="warning" size="small">指定域名</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.is_enabled" @change="handleToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" :icon="Edit" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除该规则吗？" @confirm="handleDelete(row)">
              <template #reference>
                <el-button size="small" type="danger" :icon="Delete">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header><span>即将到期域名</span></template>
      <el-form :inline="true" style="margin-bottom: 12px">
        <el-form-item label="查询天数">
          <el-input-number v-model="expiringDays" :min="1" :max="365" @change="fetchExpiring" />
        </el-form-item>
      </el-form>
      <el-table :data="expiringDomains" stripe style="width: 100%">
        <el-table-column prop="domain_name" label="域名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="platform" label="平台" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.platform ?? '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="expiry_date" label="到期日期" width="130" />
        <el-table-column prop="days_left" label="剩余天数" width="100" align="center">
          <template #default="{ row }">
            <span :class="daysClass(row.days_left)">{{ row.days_left }} 天</span>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-if="expiringTotal > expiringPageSize"
        style="margin-top: 16px; justify-content: flex-end"
        :current-page="expiringPage"
        :page-size="expiringPageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="expiringTotal"
        layout="total, sizes, prev, pager, next"
        @current-change="(val: number) => { expiringPage = val; fetchExpiring() }"
        @size-change="(val: number) => { expiringPageSize = val; expiringPage = 1; fetchExpiring() }"
      />
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑告警规则' : '添加告警规则'" width="560px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="规则名称" prop="name">
          <el-input v-model="form.name" placeholder="输入规则名称" />
        </el-form-item>
        <el-form-item label="规则类型" prop="rule_type">
          <el-select v-model="form.rule_type" style="width: 100%">
            <el-option label="域名到期提醒" value="domain_expiry" />
          </el-select>
        </el-form-item>
        <el-form-item label="提前天数" prop="days_before">
          <el-input-number v-model="form.days_before" :min="1" :max="365" style="width: 100%" />
        </el-form-item>
        <el-form-item label="通知渠道" prop="channels">
          <el-checkbox-group v-model="form.channels">
            <el-checkbox label="email">邮件</el-checkbox>
            <el-checkbox label="dingtalk">钉钉</el-checkbox>
            <el-checkbox label="wechat">企业微信</el-checkbox>
            <el-checkbox label="feishu">飞书</el-checkbox>
            <el-checkbox label="webhook">Webhook</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="接收地址" prop="recipients">
          <div style="width: 100%">
            <div v-for="(r, idx) in form.recipients" :key="idx" style="display: flex; gap: 8px; margin-bottom: 8px">
              <el-input v-model="form.recipients[idx]" :placeholder="recipientPlaceholder(idx)" />
              <el-button :icon="Delete" @click="form.recipients.splice(idx, 1)" />
            </div>
            <el-button size="small" :icon="Plus" @click="form.recipients.push('')">添加接收地址</el-button>
          </div>
        </el-form-item>
        <el-form-item label="适用范围">
          <el-switch v-model="form.apply_to_all" active-text="全部域名" inactive-text="指定域名" />
        </el-form-item>
        <el-form-item v-if="!form.apply_to_all" label="指定平台">
          <el-select v-model="form.specific_platforms" multiple placeholder="选择平台" style="width: 100%">
            <el-option v-for="p in platforms" :key="p" :label="p" :value="p" />
          </el-select>
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
import { Plus, Edit, Delete, Bell } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import {
  getAlertRules,
  createAlertRule,
  updateAlertRule,
  deleteAlertRule,
  checkAlerts,
  getExpiringDomains,
} from '@/api/alerts'
import type { AlertRule, ExpiringDomain } from '@/api/alerts'

const rules = ref<AlertRule[]>([])
const expiringDomains = ref<ExpiringDomain[]>([])
const expiringDays = ref(30)
const expiringPage = ref(1)
const expiringPageSize = ref(20)
const expiringTotal = ref(0)
const loading = ref(false)
const checking = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref<number | null>(null)
const submitting = ref(false)
const formRef = ref<FormInstance>()

const platforms = ['cloudflare', 'namecom', 'dynadot', 'godaddy', 'namecheap', 'namesilo', 'openprovider', 'porkbun', 'spaceship']

const defaultForm = {
  name: '',
  rule_type: 'domain_expiry',
  days_before: 30,
  is_enabled: true,
  channels: [] as string[],
  recipients: [''] as string[],
  apply_to_all: true,
  specific_platforms: [] as string[],
}

const form = reactive({ ...defaultForm })

const formRules = {
  name: [{ required: true, message: '请输入规则名称', trigger: 'blur' }],
  rule_type: [{ required: true, message: '请选择规则类型', trigger: 'change' }],
  days_before: [{ required: true, message: '请输入提前天数', trigger: 'blur' }],
  channels: [{ required: true, message: '请选择通知渠道', trigger: 'change', type: 'array', min: 1 }],
}

function ruleTypeLabel(type: string): string {
  const map: Record<string, string> = { domain_expiry: '域名到期' }
  return map[type] ?? type
}

function channelLabel(ch: string): string {
  const map: Record<string, string> = { email: '邮件', dingtalk: '钉钉', wechat: '企业微信', feishu: '飞书', webhook: 'Webhook' }
  return map[ch] ?? ch
}

function recipientPlaceholder(idx: number): string {
  const channels = form.channels
  if (channels.includes('email')) return '邮箱地址'
  if (channels.includes('dingtalk')) return '钉钉 Webhook URL'
  if (channels.includes('feishu')) return '飞书 Webhook URL'
  if (channels.includes('wechat')) return '企业微信 Webhook URL'
  if (channels.includes('webhook')) return 'Webhook URL'
  return '接收地址'
}

function daysClass(days: number): string {
  if (days <= 3) return 'days-danger'
  if (days <= 7) return 'days-warning'
  return 'days-safe'
}

async function fetchRules() {
  loading.value = true
  try {
    const { data } = await getAlertRules()
    rules.value = data ?? []
  } catch {
    rules.value = []
  } finally {
    loading.value = false
  }
}

async function fetchExpiring() {
  try {
    const { data } = await getExpiringDomains(expiringDays.value, expiringPage.value, expiringPageSize.value)
    expiringDomains.value = data.items ?? []
    expiringTotal.value = data.total ?? 0
  } catch {
    expiringDomains.value = []
    expiringTotal.value = 0
  }
}

async function handleCheck() {
  checking.value = true
  try {
    const { data } = await checkAlerts()
    ElMessage.success(`检查完成，发送 ${data.notifications_sent} 条通知`)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '检查失败')
  } finally {
    checking.value = false
  }
}

async function handleToggle(row: AlertRule) {
  try {
    await updateAlertRule(row.id, { is_enabled: row.is_enabled })
    ElMessage.success(row.is_enabled ? '已启用' : '已禁用')
  } catch (e: any) {
    row.is_enabled = !row.is_enabled
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

function openDialog(row?: AlertRule) {
  isEdit.value = !!row
  editId.value = row?.id ?? null
  if (row) {
    form.name = row.name
    form.rule_type = row.rule_type
    form.days_before = row.days_before ?? 30
    form.is_enabled = row.is_enabled
    form.channels = [...(row.channels ?? [])]
    form.recipients = [...(row.recipients ?? [])]
    form.apply_to_all = row.apply_to_all ?? true
    form.specific_platforms = [...(row.specific_platforms ?? [])]
  } else {
    Object.assign(form, { ...defaultForm, channels: [], recipients: [''] })
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value?.validate()
  submitting.value = true
  try {
    const payload: any = {
      name: form.name,
      rule_type: form.rule_type,
      days_before: form.days_before,
      is_enabled: form.is_enabled,
      channels: form.channels,
      recipients: form.recipients.filter((r) => r.trim()),
      apply_to_all: form.apply_to_all,
      specific_platforms: form.apply_to_all ? [] : form.specific_platforms,
    }
    if (isEdit.value && editId.value) {
      await updateAlertRule(editId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await createAlertRule(payload)
      ElMessage.success('添加成功')
    }
    dialogVisible.value = false
    await fetchRules()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row: AlertRule) {
  try {
    await deleteAlertRule(row.id)
    ElMessage.success('删除成功')
    await fetchRules()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

onMounted(() => {
  fetchRules()
  fetchExpiring()
})
</script>

<style scoped>
.alerts-container {
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
.days-safe { color: #67c23a; font-weight: 600; }
.days-warning { color: #e6a23c; font-weight: 600; }
.days-danger { color: #f56c6c; font-weight: 600; }
</style>
