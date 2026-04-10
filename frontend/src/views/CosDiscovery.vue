<template>
  <div class="cos-discovery-container">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-copy">
          <div class="page-title">COS 解析</div>
          <div class="page-subtitle">查看腾讯云 COS 存储桶已配置的自定义域名、源站类型与 CNAME 值。</div>
          <div class="page-description">
            账号密钥从配置中心读取，页面只展示已配置自定义域名的存储桶记录。
          </div>
        </div>

        <div class="toolbar-actions">
          <el-button :loading="loadingConfig" @click="loadConfig">刷新配置</el-button>
          <el-button type="primary" :loading="loading" :disabled="!configured" @click="loadDomains">
            查询 COS
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
      description="尚未配置腾讯云 SecretId / SecretKey，请先到系统配置中心填写。"
      class="empty-state"
    />

    <template v-else>
      <div class="stats-grid">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="域名记录数" :value="domainCount" />
        </el-card>
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="存储桶数" :value="bucketCount" />
        </el-card>
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="当前页大小" :value="pageSize" />
        </el-card>
      </div>

      <el-card shadow="never" class="table-card">
        <template #header>
          <div class="table-header">
            <div class="table-heading">
              <div class="table-title">COS 自定义域名列表</div>
              <div class="table-subtitle">仅展示已配置自定义域名的 COS 存储桶。</div>
            </div>
            <div class="table-tools">
              <el-tag type="info">共 {{ domainItems.length }} 条</el-tag>
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
          :data="pagedDomainItems"
          empty-text="暂无 COS 域名数据"
          border
          stripe
          class="domain-table"
        >
          <el-table-column prop="bucket_name" label="存储桶名" min-width="220" show-overflow-tooltip />
          <el-table-column prop="custom_domain" label="自定义域名" min-width="280" show-overflow-tooltip />
          <el-table-column prop="origin_type" label="源站类型" min-width="160" />
          <el-table-column prop="cname" label="CNAME 值" min-width="360" show-overflow-tooltip />
        </el-table>

        <div v-if="domainItems.length" class="pagination-wrap">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            background
            layout="total, prev, pager, next, jumper"
            :total="domainItems.length"
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
  getCosDiscoveryConfig,
  getCosDomains,
  type CosDiscoveryDomainItem,
} from '@/api/cosDiscovery'

const router = useRouter()
const authStore = useAuthStore()

const configured = ref(false)
const loadingConfig = ref(false)
const loading = ref(false)
const domainItems = ref<CosDiscoveryDomainItem[]>([])
const currentPage = ref(1)
const pageSize = ref(20)
const pageSizeOptions = [10, 20, 50, 100]

const domainCount = computed(() => domainItems.value.length)
const bucketCount = computed(() => new Set(domainItems.value.map((item) => item.bucket_name)).size)
const pagedDomainItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return domainItems.value.slice(start, start + pageSize.value)
})

function handlePageSizeChange() {
  currentPage.value = 1
}

async function loadConfig() {
  loadingConfig.value = true
  try {
    const { data } = await getCosDiscoveryConfig()
    configured.value = data.configured
    if (!configured.value) {
      domainItems.value = []
      currentPage.value = 1
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载 COS 配置失败')
  } finally {
    loadingConfig.value = false
  }
}

async function loadDomains() {
  loading.value = true
  try {
    const { data } = await getCosDomains()
    domainItems.value = data.items || []
    currentPage.value = 1
  } catch (error: any) {
    domainItems.value = []
    currentPage.value = 1
    ElMessage.error(error.response?.data?.detail || '读取 COS 域名失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadConfig()
  if (configured.value) {
    loadDomains()
  }
})
</script>

<style scoped>
.cos-discovery-container {
  width: 100%;
  padding-bottom: 20px;
}

.toolbar-card {
  margin-bottom: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  background: linear-gradient(135deg, #f7fbff 0%, #ffffff 100%);
}

.toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}

.toolbar-copy {
  max-width: 620px;
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

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.stat-card,
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
  gap: 6px;
}

.table-title {
  font-size: 16px;
  font-weight: 600;
}

.table-subtitle {
  font-size: 13px;
  color: #6b7280;
}

.table-tools {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.page-size-select {
  width: 110px;
}

.domain-table :deep(.el-table__header th) {
  background: #f8fafc;
  color: #374151;
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

  .toolbar-actions,
  .table-tools,
  .page-size-select {
    width: 100%;
  }

  .table-tools {
    justify-content: flex-start;
  }

  .pagination-wrap {
    justify-content: center;
  }
}
</style>
