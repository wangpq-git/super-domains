<template>
  <div class="cos-discovery-container page-stack">
    <PageHero
      eyebrow="OBJECT STORAGE"
      title="COS 解析"
      subtitle="查看腾讯云 COS 存储桶的自定义域名、源站类型与 CNAME 值，适合做对象存储域名盘点。"
      tone="blue"
    >
      <template #meta>
        <el-tag effect="plain" round>桶 {{ bucketCount }} / 域名 {{ domainCount }}</el-tag>
      </template>
      <div class="hero-metrics">
        <span>域名记录 {{ domainCount }}</span>
        <span>存储桶 {{ bucketCount }}</span>
        <span>跳过 {{ skippedBucketCount }}</span>
      </div>
    </PageHero>

    <el-empty
      v-if="!configured"
      description="尚未配置腾讯云 SecretId / SecretKey，请先到系统配置中心填写。"
      class="empty-state"
    />

    <template v-else>
      <div class="page-grid-3">
        <el-card shadow="never" class="stat-card">
          <el-statistic title="域名记录数" :value="domainCount" />
        </el-card>
        <el-card shadow="never" class="stat-card">
          <el-statistic title="存储桶数" :value="bucketCount" />
        </el-card>
        <el-card shadow="never" class="stat-card">
          <el-statistic title="已跳过桶数" :value="skippedBucketCount" />
        </el-card>
      </div>

      <el-card shadow="never" class="table-card data-card">
        <template #header>
          <div class="table-header">
            <div class="table-heading">
              <div class="table-title-row">
                <div class="table-title">COS 自定义域名列表</div>
                <el-tag v-if="skippedBucketCount" type="warning" effect="plain">
                  已跳过 {{ skippedBucketCount }} 个无权限访问的桶
                </el-tag>
              </div>
              <div class="table-subtitle">支持按存储桶名、自定义域名或 CNAME 值快速筛选。</div>
            </div>
            <div class="table-tools">
              <el-input
                v-model="keyword"
                class="search-input"
                clearable
                placeholder="搜索存储桶名 / 域名 / CNAME"
                @input="handleKeywordChange"
                @clear="handleKeywordChange"
              />
              <el-tag type="info">共 {{ filteredDomainItems.length }} 条</el-tag>
              <el-select v-model="pageSize" class="page-size-select" @change="handlePageSizeChange">
                <el-option
                  v-for="size in pageSizeOptions"
                  :key="size"
                  :label="`${size} / 页`"
                  :value="size"
                />
              </el-select>
              <el-button :loading="loadingConfig" @click="loadConfig(true)">刷新配置</el-button>
              <el-button type="primary" :loading="loading" :disabled="!configured" @click="loadDomains(true)">
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
        </template>

        <div class="table-shell">
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
        </div>

        <div v-if="filteredDomainItems.length" class="pagination-wrap">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            background
            layout="total, prev, pager, next, jumper"
            :total="filteredDomainItems.length"
          />
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from '@/utils/message'
import { useRouter } from 'vue-router'
import PageHero from '@/components/PageHero.vue'
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
const skippedBucketCount = ref(0)
const keyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const pageSizeOptions = [10, 20, 50, 100]

const domainCount = computed(() => domainItems.value.length)
const bucketCount = computed(() => new Set(domainItems.value.map((item) => item.bucket_name)).size)
const filteredDomainItems = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) {
    return domainItems.value
  }

  return domainItems.value.filter((item) => {
    return [item.bucket_name, item.custom_domain, item.cname].some((value) => value.toLowerCase().includes(query))
  })
})
const pagedDomainItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredDomainItems.value.slice(start, start + pageSize.value)
})

function handleKeywordChange() {
  currentPage.value = 1
}

function handlePageSizeChange() {
  currentPage.value = 1
}

async function loadConfig(force = false) {
  loadingConfig.value = true
  try {
    const { data } = await getCosDiscoveryConfig(force)
    configured.value = data.configured
    if (!configured.value) {
      domainItems.value = []
      skippedBucketCount.value = 0
      keyword.value = ''
      currentPage.value = 1
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载 COS 配置失败')
  } finally {
    loadingConfig.value = false
  }
}

async function loadDomains(force = false) {
  loading.value = true
  try {
    const { data } = await getCosDomains(force)
    domainItems.value = data.items || []
    skippedBucketCount.value = data.skipped_bucket_count || 0
    keyword.value = ''
    currentPage.value = 1
  } catch (error: any) {
    domainItems.value = []
    skippedBucketCount.value = 0
    keyword.value = ''
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
}

.hero-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: rgba(255, 255, 255, 0.82);
  font-size: 13px;
}

.stat-card,
.table-card {
  border-radius: 18px;
}

.stat-card {
  min-height: 126px;
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

.table-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
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

.search-input {
  width: 320px;
}

.page-size-select {
  width: 110px;
}

.table-shell {
  overflow-x: auto;
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
  .table-tools {
    width: 100%;
  }

  .search-input,
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
