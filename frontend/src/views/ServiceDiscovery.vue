<template>
  <div class="service-discovery-container">
    <el-alert
      title="从配置中心读取 K8s kubeconfig 和允许访问的命名空间，展示指定 namespace 下的 Ingress 名称与域名。"
      type="info"
      :closable="false"
      class="page-tip"
    />

    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div>
          <div class="page-title">服务解析</div>
          <div class="page-subtitle">查看已配置命名空间中的 Ingress 域名映射。</div>
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

      <el-card shadow="never">
        <template #header>
          <div class="table-header">
            <div>
              <div class="table-title">Ingress 列表</div>
              <div class="table-subtitle">当前命名空间：{{ currentNamespaceLabel }}</div>
            </div>
            <div class="table-meta">
              <el-tag type="info">共 {{ ingressItems.length }} 条</el-tag>
              <el-select v-model="pageSize" class="page-size-select">
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

        <el-table v-loading="loading" :data="pagedIngressItems" empty-text="暂无 Ingress 数据" border>
          <el-table-column prop="name" label="Ingress 名称" min-width="180" />
          <el-table-column label="域名" min-width="280">
            <template #default="{ row }">
              <div class="tag-list">
                <el-tag v-for="host in row.hosts" :key="host" class="host-tag" type="success">
                  {{ host }}
                </el-tag>
                <span v-if="!row.hosts.length" class="placeholder-text">未配置域名</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="TLS 域名" min-width="220">
            <template #default="{ row }">
              <div class="tag-list">
                <el-tag v-for="host in row.tls_hosts" :key="host" class="host-tag" type="warning">
                  {{ host }}
                </el-tag>
                <span v-if="!row.tls_hosts.length" class="placeholder-text">-</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="ingress_class_name" label="Ingress Class" min-width="140">
            <template #default="{ row }">
              {{ row.ingress_class_name || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="LB 地址" min-width="220">
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

        <div v-if="ingressItems.length" class="pagination-wrap">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            background
            layout="total, prev, pager, next, jumper"
            :total="ingressItems.length"
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
const currentPage = ref(1)
const pageSize = ref(20)
const pageSizeOptions = [10, 20, 50, 100]

const ingressCount = computed(() => ingressItems.value.length)
const hostCount = computed(() => ingressItems.value.reduce((sum, item) => sum + item.hosts.length, 0))
const pagedIngressItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return ingressItems.value.slice(start, start + pageSize.value)
})
const currentNamespaceLabel = computed(() => {
  const matched = namespaceOptions.value.find((item) => item.namespace === selectedNamespace.value)
  return matched?.label || selectedNamespace.value || '-'
})

async function loadConfig() {
  loadingConfig.value = true
  try {
    const { data } = await getServiceDiscoveryConfig()
    configured.value = data.configured
    namespaceOptions.value = data.namespace_options || []

    if (!namespaceOptions.value.length) {
      selectedNamespace.value = ''
      ingressItems.value = []
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
    currentPage.value = 1
  } catch (error: any) {
    ingressItems.value = []
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

.page-tip {
  margin-bottom: 16px;
}

.toolbar-card {
  margin-bottom: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #1f2937;
}

.page-subtitle {
  margin-top: 6px;
  color: #6b7280;
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

.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.table-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-size-select {
  width: 110px;
}

.table-title {
  font-size: 16px;
  font-weight: 600;
}

.table-subtitle {
  margin-top: 4px;
  font-size: 13px;
  color: #6b7280;
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

  .table-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .table-meta {
    width: 100%;
    justify-content: space-between;
  }

  .pagination-wrap {
    justify-content: center;
  }
}
</style>
