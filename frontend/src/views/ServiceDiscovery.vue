<template>
  <div class="service-discovery-container">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-copy">
          <div class="page-title">服务解析</div>
          <div class="page-subtitle">查看已配置命名空间中的 Ingress 域名与 LB 地址映射。</div>
          <div class="page-description">
            数据来自配置中心中预设的 K8s kubeconfig 与命名空间白名单。
          </div>
        </div>

        <div class="toolbar-actions">
          <el-select
            v-model="selectedNamespace"
            class="namespace-select"
            placeholder="请选择命名空间"
            :disabled="!namespaceOptions.length || loading"
          >
            <el-option
              v-for="item in namespaceOptions"
              :key="item.namespace"
              :label="item.label"
              :value="item.namespace"
            />
          </el-select>
          <el-button :loading="loadingConfig" @click="loadConfig">刷新配置</el-button>
          <el-button type="primary" :loading="loading" :disabled="!selectedNamespace" @click="loadIngresses">
            查询 Ingress
          </el-button>
          <el-button
            v-if="authStore.isAdmin"
            type="success"
            plain
            @click="router.push('/system-settings')"
          >
            去配置中心
          </el-button>
        </div>
      </div>
    </el-card>

    <el-empty
      v-if="!configured"
      description="尚未配置 K8s kubeconfig，请先到系统配置中心填写相关参数。"
      class="empty-state"
    />

    <template v-else>
      <div class="stats-grid">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="命名空间" :value="namespaceOptions.length" />
        </el-card>
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="Ingress 数量" :value="ingressCount" />
        </el-card>
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="域名数量" :value="hostCount" />
        </el-card>
      </div>

      <el-card shadow="never" class="table-card">
        <template #header>
          <div class="table-header">
            <div class="table-heading">
              <div class="table-title-row">
                <div class="table-title">Ingress 列表</div>
                <el-tag effect="plain" type="success">当前命名空间：{{ currentNamespaceLabel }}</el-tag>
              </div>
              <div class="table-subtitle">支持按 Ingress 名称、域名或 LB 地址快速筛选。</div>
            </div>
            <div class="table-tools">
              <el-input
                v-model="keyword"
                class="search-input"
                clearable
                placeholder="搜索 Ingress / 域名 / LB 地址"
                @input="handleKeywordChange"
                @clear="handleKeywordChange"
              />
              <el-tag type="info">共 {{ filteredIngressItems.length }} 条</el-tag>
              <el-select v-model="pageSize" class="page-size-select" @change="handlePageSizeChange">
                <el-option
                  v-for="size in pageSizeOptions"
                  :key="size"
                  :label="`${size} / 页`"
                  :value="size"
                />
              </el-select>
            </div>
          </div>
        </template>

        <el-table
          v-loading="loading"
          :data="pagedIngressItems"
          empty-text="暂无 Ingress 数据"
          border
          stripe
          class="ingress-table"
        >
          <el-table-column prop="name" label="Ingress 名称" min-width="220" show-overflow-tooltip />
          <el-table-column label="域名" min-width="320">
            <template #default="{ row }">
              <div class="tag-list">
                <el-tag v-for="host in row.hosts" :key="host" class="host-tag" type="success">
                  {{ host }}
                </el-tag>
                <span v-if="!row.hosts.length" class="placeholder-text">未配置域名</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="LB 地址" min-width="320">
            <template #default="{ row }">
              <div class="tag-list">
                <el-tag v-for="item in row.load_balancers" :key="item" class="host-tag" type="info">
                  {{ item }}
                </el-tag>
                <span v-if="!row.load_balancers.length" class="placeholder-text">-</span>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="filteredIngressItems.length" class="pagination-wrap">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            background
            layout="total, prev, pager, next, jumper"
            :total="filteredIngressItems.length"
          />
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  getServiceDiscoveryConfig,
  getServiceIngresses,
  type ServiceDiscoveryIngressItem,
  type ServiceDiscoveryNamespaceOption,
} from '@/api/serviceDiscovery'

const router = useRouter()
const authStore = useAuthStore()

const configured = ref(false)
const loadingConfig = ref(false)
const loading = ref(false)
const namespaceOptions = ref<ServiceDiscoveryNamespaceOption[]>([])
const selectedNamespace = ref('')
const ingressItems = ref<ServiceDiscoveryIngressItem[]>([])
const keyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const pageSizeOptions = [10, 20, 50, 100]

const ingressCount = computed(() => ingressItems.value.length)
const hostCount = computed(() => ingressItems.value.reduce((sum, item) => sum + item.hosts.length, 0))
const filteredIngressItems = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) {
    return ingressItems.value
  }

  return ingressItems.value.filter((item) => {
    return [item.name, ...item.hosts, ...item.load_balancers].some((value) => {
      return value.toLowerCase().includes(query)
    })
  })
})
const pagedIngressItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredIngressItems.value.slice(start, start + pageSize.value)
})
const currentNamespaceLabel = computed(() => {
  const matched = namespaceOptions.value.find((item) => item.namespace === selectedNamespace.value)
  return matched?.label || selectedNamespace.value || '-'
})

function handleKeywordChange() {
  currentPage.value = 1
}

function handlePageSizeChange() {
  currentPage.value = 1
}

async function loadConfig() {
  loadingConfig.value = true
  try {
    const { data } = await getServiceDiscoveryConfig()
    configured.value = data.configured
    namespaceOptions.value = data.namespace_options || []

    if (!namespaceOptions.value.length) {
      selectedNamespace.value = ''
      ingressItems.value = []
      keyword.value = ''
      currentPage.value = 1
      return
    }

    const exists = namespaceOptions.value.some((item) => item.namespace === selectedNamespace.value)
    if (!exists) {
      selectedNamespace.value = namespaceOptions.value[0].namespace
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载服务解析配置失败')
  } finally {
    loadingConfig.value = false
  }
}

async function loadIngresses() {
  if (!selectedNamespace.value) {
    ElMessage.warning('请先选择命名空间')
    return
  }

  loading.value = true
  try {
    const { data } = await getServiceIngresses(selectedNamespace.value)
    ingressItems.value = data.items || []
    keyword.value = ''
    currentPage.value = 1
  } catch (error: any) {
    ingressItems.value = []
    keyword.value = ''
    currentPage.value = 1
    ElMessage.error(error.response?.data?.detail || '读取 Ingress 失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadConfig()
  if (configured.value && selectedNamespace.value) {
    loadIngresses()
  }
})
</script>

<style scoped>
.service-discovery-container {
  width: 100%;
  padding-bottom: 20px;
}

.toolbar-card {
  margin-bottom: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  background: linear-gradient(135deg, #f8fbff 0%, #ffffff 100%);
}

.toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}

.toolbar-copy {
  max-width: 560px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: #111827;
}

.page-subtitle {
  margin-top: 6px;
  font-size: 14px;
  color: #4b5563;
}

.page-description {
  margin-top: 10px;
  color: #6b7280;
  line-height: 1.6;
}

.toolbar-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.namespace-select {
  width: 240px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.stat-card {
  border-radius: 14px;
}

.table-card {
  border-radius: 18px;
}

.table-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.table-heading {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.table-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.table-tools {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.search-input {
  width: 320px;
}

.page-size-select {
  width: 110px;
}

.table-title {
  font-size: 16px;
  font-weight: 600;
}

.table-subtitle {
  font-size: 13px;
  color: #6b7280;
}

.ingress-table :deep(.el-table__header th) {
  background: #f8fafc;
  color: #374151;
}

.ingress-table :deep(.el-table__cell) {
  vertical-align: top;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.host-tag {
  margin: 0;
}

.placeholder-text {
  color: #9ca3af;
}

.empty-state {
  margin-top: 12px;
  padding: 32px 0;
  background: #fff;
  border-radius: 12px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

@media (max-width: 900px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .namespace-select {
    width: 100%;
  }

  .toolbar-actions {
    width: 100%;
  }

  .table-tools {
    width: 100%;
    justify-content: flex-start;
  }

  .search-input,
  .page-size-select {
    width: 100%;
  }

  .pagination-wrap {
    justify-content: center;
  }
}
</style>
