<template>
  <div class="alerts-container page-stack">
    <PageHero
      eyebrow="RISK AUTOMATION"
      title="告警规则"
      subtitle="统一管理到期提醒策略、通知渠道和手动检查入口，避免高风险域名漏报。"
      tone="gold"
    >
      <template #meta>
        <el-tag effect="plain" round>启用 {{ enabledRuleCount }} / {{ rules.length }}</el-tag>
      </template>
      <div class="hero-metrics">
        <span>规则 {{ rules.length }}</span>
        <span>临期域名 {{ expiringTotal }}</span>
        <span>检查窗口 {{ expiringDays }} 天</span>
      </div>
      <template #actions>
        <el-button type="warning" :icon="Bell" :loading="checking" @click="handleCheck">手动检查</el-button>
        <el-button type="primary" :icon="Plus" @click="openDialog()">添加规则</el-button>
      </template>
    </PageHero>

    <section class="page-grid-3">
      <el-card shadow="never" class="overview-card">
        <p class="overview-label">已启用规则</p>
        <strong class="overview-value">{{ enabledRuleCount }}</strong>
        <span class="overview-hint">优先检查高等级和自动触发规则是否覆盖关键平台。</span>
      </el-card>
      <el-card shadow="never" class="overview-card">
        <p class="overview-label">手动检查</p>
        <strong class="overview-value">{{ checking ? '执行中' : '可执行' }}</strong>
        <span class="overview-hint">用于在部署或配置修改后立即验证通知链路。</span>
      </el-card>
      <el-card shadow="never" class="overview-card">
        <p class="overview-label">临期域名</p>
        <strong class="overview-value">{{ expiringTotal }}</strong>
        <span class="overview-hint">当前查询窗口内的到期域名总量。</span>
      </el-card>
    </section>

    <el-card shadow="never" class="data-card">
      <template #header>
        <div class="card-header">
          <div>
            <span>规则列表</span>
            <p class="card-subtitle">覆盖通知频率、渠道和适用范围，建议避免重复规则造成提醒噪声。</p>
          </div>
          <el-tag type="info" effect="plain">共 {{ rules.length }} 条</el-tag>
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
        <el-table-column prop="severity" label="等级" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.severity === 'urgent'" type="danger" size="small">🔴 紧急</el-tag>
            <el-tag v-else-if="row.severity === 'warning'" type="warning" size="small">🟡 警告</el-tag>
            <el-tag v-else type="success" size="small">🟢 提醒</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="schedule" label="发送频率" width="140" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="(typeof row.schedule === 'object' ? row.schedule?.type : row.schedule) === 'manual' ? 'info' : 'primary'">
              {{ scheduleLabel(row.schedule) }}
            </el-tag>
          </template>
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

    <el-card shadow="never" class="data-card">
      <template #header>
        <div>
          <span>即将到期域名</span>
          <p class="card-subtitle">按剩余天数快速查看风险分布，可结合规则策略确认是否需要提早提醒。</p>
        </div>
      </template>
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
        <el-form-item label="告警等级">
          <el-radio-group v-model="form.severity">
            <el-radio-button value="urgent"><span style="color: #f56c6c">🔴 紧急</span></el-radio-button>
            <el-radio-button value="warning"><span style="color: #e6a23c">🟡 警告</span></el-radio-button>
            <el-radio-button value="info"><span style="color: #67c23a">🟢 提醒</span></el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="发送频率">
          <div style="width: 100%">
            <el-select v-model="form.schedule.type" style="width: 100%; margin-bottom: 8px" @change="onScheduleTypeChange">
              <el-option label="手动触发" value="manual" />
              <el-option label="每天" value="daily" />
              <el-option label="每周" value="weekly" />
              <el-option label="每月" value="monthly" />
            </el-select>
            <el-checkbox-group v-if="form.schedule.type === 'weekly'" v-model="form.schedule.days">
              <el-checkbox-button :value="1">周一</el-checkbox-button>
              <el-checkbox-button :value="2">周二</el-checkbox-button>
              <el-checkbox-button :value="3">周三</el-checkbox-button>
              <el-checkbox-button :value="4">周四</el-checkbox-button>
              <el-checkbox-button :value="5">周五</el-checkbox-button>
              <el-checkbox-button :value="6">周六</el-checkbox-button>
              <el-checkbox-button :value="0">周日</el-checkbox-button>
            </el-checkbox-group>
            <el-select v-if="form.schedule.type === 'monthly'" v-model="form.schedule.days" multiple placeholder="选择日期" style="width: 100%">
              <el-option v-for="d in 28" :key="d" :label="d + '号'" :value="d" />
            </el-select>
            <el-time-picker
              v-if="form.schedule.type !== 'manual'"
              v-model="form.schedule.time"
              style="width: 100%; margin-top: 8px"
              format="HH:mm:ss"
              value-format="HH:mm:ss"
              placeholder="选择发送时间"
            />
          </div>
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
        <el-form-item v-if="form.apply_to_all" label="排除平台">
          <el-select v-model="form.excluded_platforms" multiple placeholder="选择要排除的平台（可选）" style="width: 100%">
            <el-option v-for="p in platforms" :key="p" :label="p" :value="p" />
          </el-select>
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
import { ref, reactive, onMounted, computed } from 'vue'
import { Plus, Edit, Delete, Bell } from '@element-plus/icons-vue'
import { ElMessage } from '@/utils/message'
import PageHero from '@/components/PageHero.vue'
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
  excluded_platforms: [] as string[],
  severity: 'warning' as string,
  schedule: { type: 'manual', days: [], time: '09:00:00' } as { type: string; days: number[]; time: string },
}

const form = reactive({ ...defaultForm })
const enabledRuleCount = computed(() => rules.value.filter((rule) => rule.is_enabled).length)

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

function scheduleLabel(s: any): string {
  if (!s || typeof s === 'string') {
    const map: Record<string, string> = { manual: '手动', daily: '每天', weekly_mon: '每周一', monthly_1st: '每月1号' }
    return map[s] ?? String(s)
  }
  const t = s.type
  if (t === 'manual') return '手动'
  const timeText = s.time ? ` ${s.time}` : ''
  if (t === 'daily') return `每天${timeText}`
  if (t === 'weekly') {
    const dayNames = ['日', '一', '二', '三', '四', '五', '六']
    const days = (s.days || []).map((d: number) => '周' + dayNames[d]).join('、')
    return `${days || '每周'}${timeText}`
  }
  if (t === 'monthly') {
    const days = (s.days || []).map((d: number) => d + '号').join('、')
    return `${days || '每月'}${timeText}`
  }
  return '手动'
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

async function fetchRules(force = false) {
  loading.value = true
  try {
    const { data } = await getAlertRules(force)
    rules.value = data ?? []
  } catch {
    rules.value = []
  } finally {
    loading.value = false
  }
}

async function fetchExpiring(force = false) {
  try {
    const { data } = await getExpiringDomains(expiringDays.value, expiringPage.value, expiringPageSize.value, force)
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

function onScheduleTypeChange() {
  form.schedule.days = []
  if (!form.schedule.time) {
    form.schedule.time = '09:00:00'
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
    form.excluded_platforms = [...(row.excluded_platforms ?? [])]
    form.severity = row.severity ?? 'warning'
    const sched = row.schedule ?? { type: 'manual' }
    form.schedule = {
      type: (typeof sched === 'object' ? sched.type : sched) || 'manual',
      days: [...((typeof sched === 'object' ? sched.days : undefined) || [])],
      time: (typeof sched === 'object' ? sched.time : undefined) || '09:00:00',
    }
  } else {
    Object.assign(form, { ...defaultForm, channels: [], recipients: [''], schedule: { type: 'manual', days: [], time: '09:00:00' } })
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
      excluded_platforms: form.apply_to_all ? form.excluded_platforms : [],
      severity: form.severity,
      schedule: form.schedule,
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
}

.hero-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: rgba(255, 255, 255, 0.82);
  font-size: 13px;
}

.overview-card {
  min-height: 148px;
}

.overview-label {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.overview-value {
  display: block;
  margin-top: 16px;
  font-size: 28px;
  color: #0f172a;
}

.overview-hint {
  display: block;
  margin-top: 12px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
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

.days-safe { color: #67c23a; font-weight: 600; }
.days-warning { color: #e6a23c; font-weight: 600; }
.days-danger { color: #f56c6c; font-weight: 600; }
</style>
