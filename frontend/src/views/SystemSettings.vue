<template>
  <div class="system-settings-container">
    <el-alert
      title="这里适合配置审批、飞书、LDAP、通知等可热更新参数。数据库、Redis、加密主密钥这类启动级配置仍建议保留在部署环境中。"
      type="info"
      :closable="false"
      class="page-tip"
    />

    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">系统配置中心</div>
            <div class="card-subtitle">修改后优先保存到数据库，运行时优先生效。</div>
          </div>
          <div class="header-actions">
            <el-button @click="loadSettings">刷新</el-button>
            <el-button type="primary" :loading="saving" @click="saveCurrentCategory">
              保存当前分类
            </el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeCategory">
        <el-tab-pane
          v-for="category in categories"
          :key="category.key"
          :label="category.label"
          :name="category.key"
        >
          <div class="settings-grid">
            <el-card
              v-for="item in groupedSettings[category.key] || []"
              :key="item.key"
              shadow="hover"
              class="setting-card"
            >
              <div class="setting-header">
                <div>
                  <div class="setting-title">{{ item.label }}</div>
                  <div class="setting-key">{{ item.key }}</div>
                </div>
                <div class="setting-meta">
                  <el-tag size="small" :type="sourceTagType(item.source)">
                    {{ sourceLabel(item.source) }}
                  </el-tag>
                  <el-tag v-if="item.restart_required" size="small" type="warning">需重启</el-tag>
                  <el-tag v-if="item.is_secret" size="small" type="danger">敏感</el-tag>
                </div>
              </div>

              <div v-if="item.description" class="setting-description">{{ item.description }}</div>

              <div class="setting-field">
                <el-switch
                  v-if="item.value_type === 'boolean'"
                  v-model="draftMap[item.key]"
                />

                <el-input-number
                  v-else-if="item.value_type === 'integer'"
                  v-model="draftMap[item.key]"
                  :min="0"
                  :step="1"
                  controls-position="right"
                />

                <el-input
                  v-else-if="item.value_type === 'json'"
                  v-model="draftMap[item.key]"
                  type="textarea"
                  :rows="item.rows || 6"
                  placeholder='请输入 JSON，例如 {"ou_xxx":"admin"}'
                />

                <el-input
                  v-else-if="item.ui_type === 'textarea'"
                  v-model="draftMap[item.key]"
                  type="textarea"
                  :rows="item.rows || 8"
                  :placeholder="item.is_secret ? secretPlaceholder(item) : '请输入配置值'"
                />

                <el-input
                  v-else
                  v-model="draftMap[item.key]"
                  :type="item.is_secret ? 'password' : 'text'"
                  :placeholder="item.is_secret ? secretPlaceholder(item) : '请输入配置值'"
                  show-password
                >
                  <template v-if="item.is_secret && item.masked_value" #append>
                    <span class="masked-value">{{ item.masked_value }}</span>
                  </template>
                </el-input>
              </div>

              <div class="setting-footer">
                <span class="config-state" :class="{ configured: item.is_configured }">
                  {{ item.is_configured ? '已配置' : '未配置' }}
                </span>
              </div>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSystemSettings, updateSystemSettings, type SystemSettingItem } from '@/api/systemSettings'

type SourceType = 'database' | 'environment' | 'default'

const categories = [
  { key: 'approval', label: '审批策略' },
  { key: 'feishu', label: '飞书审批' },
  { key: 'ldap', label: 'LDAP 登录' },
  { key: 'service_discovery', label: '服务解析' },
  { key: 'notification', label: '通知配置' }
]

const activeCategory = ref('approval')
const loading = ref(false)
const saving = ref(false)
const settings = ref<SystemSettingItem[]>([])
const draftMap = ref<Record<string, any>>({})

function normalizeDraft(item: SystemSettingItem) {
  if (item.value_type === 'json') {
    return JSON.stringify(item.value ?? {}, null, 2)
  }
  if (item.is_secret) {
    return ''
  }
  if (item.value_type === 'integer') {
    return Number(item.value ?? 0)
  }
  if (item.value_type === 'boolean') {
    return Boolean(item.value)
  }
  return item.value ?? ''
}

function buildDrafts(items: SystemSettingItem[]) {
  const next: Record<string, any> = {}
  items.forEach((item) => {
    next[item.key] = normalizeDraft(item)
  })
  draftMap.value = next
}

const groupedSettings = computed(() => {
  const result: Record<string, SystemSettingItem[]> = {}
  settings.value.forEach((item) => {
    if (!result[item.category]) {
      result[item.category] = []
    }
    result[item.category].push(item)
  })
  return result
})

function sourceLabel(source: SourceType) {
  if (source === 'database') return '数据库'
  if (source === 'environment') return '环境变量'
  return '默认值'
}

function sourceTagType(source: SourceType) {
  if (source === 'database') return 'success'
  if (source === 'environment') return 'warning'
  return 'info'
}

function secretPlaceholder(item: SystemSettingItem) {
  return item.masked_value ? '留空表示保持当前密钥' : '请输入敏感配置'
}

async function loadSettings() {
  loading.value = true
  try {
    const { data } = await getSystemSettings()
    settings.value = data.items || []
    buildDrafts(settings.value)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载系统配置失败')
  } finally {
    loading.value = false
  }
}

async function saveCurrentCategory() {
  const items = groupedSettings.value[activeCategory.value] || []
  const payload: Array<{ key: string; value: any }> = []

  try {
    items.forEach((item) => {
      const draftValue = draftMap.value[item.key]
      if (item.is_secret) {
        if (draftValue !== '') {
          payload.push({ key: item.key, value: draftValue })
        }
        return
      }

      if (item.value_type === 'json') {
        payload.push({ key: item.key, value: draftValue ? JSON.parse(draftValue) : {} })
        return
      }

      payload.push({ key: item.key, value: draftValue })
    })
  } catch {
    ElMessage.error('JSON 配置格式不正确，请先修正后再保存')
    return
  }

  if (payload.length === 0) {
    ElMessage.info('当前分类没有可保存的变更')
    return
  }

  saving.value = true
  try {
    const { data } = await updateSystemSettings(payload)
    settings.value = data.items || []
    buildDrafts(settings.value)
    ElMessage.success('配置保存成功')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
.system-settings-container {
  width: 100%;
  padding-bottom: 20px;
}

.page-tip {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
}

.card-subtitle {
  margin-top: 6px;
  color: #909399;
  font-size: 13px;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.setting-card {
  min-height: 220px;
}

.setting-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.setting-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.setting-key {
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  word-break: break-all;
}

.setting-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.setting-description {
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 14px;
}

.setting-field {
  margin-bottom: 12px;
}

.setting-footer {
  display: flex;
  justify-content: flex-end;
}

.config-state {
  color: #909399;
  font-size: 12px;
}

.config-state.configured {
  color: #67c23a;
}

.masked-value {
  min-width: 88px;
  text-align: center;
  color: #909399;
  font-size: 12px;
}
</style>
