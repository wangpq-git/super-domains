<template>
  <div class="dashboard-container" v-loading="loading">
    <el-row :gutter="20" class="stat-row">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card stat-card--blue">
          <el-statistic title="域名总数" :value="stats?.total_domains ?? 0">
            <template #prefix><el-icon color="#409eff"><Connection /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card stat-card--orange">
          <el-statistic title="即将到期（30天内）" :value="stats?.expiring_soon ?? 0">
            <template #prefix><el-icon color="#e6a23c"><Warning /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card stat-card--red">
          <el-statistic title="已过期" :value="stats?.expired ?? 0">
            <template #prefix><el-icon color="#f56c6c"><CircleClose /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card stat-card--green">
          <el-statistic title="接入平台" :value="stats?.platform_count ?? 0">
            <template #prefix><el-icon color="#67c23a"><Monitor /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="chart-row">
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header><span class="chart-header">域名平台分布</span></template>
          <div class="chart-wrapper">
            <v-chart v-if="stats?.by_platform" :option="pieOption" autoresize style="height: 350px" />
            <el-empty v-else description="暂无数据" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header><span class="chart-header">到期时间分布</span></template>
          <div class="chart-wrapper">
            <v-chart v-if="stats?.by_expiry" :option="barOption" autoresize style="height: 350px" />
            <el-empty v-else description="暂无数据" />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { use } from 'echarts/core'
import { PieChart, BarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { useDomainsStore } from '@/stores/domains'
import { platformLabel } from '@/utils/format'

use([PieChart, BarChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

const store = useDomainsStore()
const loading = ref(false)

const stats = computed(() => store.stats)

const platformColors: Record<string, string> = {
  cloudflare: '#f6821f',
  namecom: '#42b983',
  dynadot: '#5470c6',
  godaddy: '#1db954',
  namecheap: '#de4040',
  namesilo: '#6366f1',
  openprovider: '#0ea5e9',
  porkbun: '#ec4899',
  spaceship: '#8b5cf6',
}

const pieOption = computed(() => {
  const data = store.stats?.by_platform
  if (!data) return {}
  const seriesData = Object.entries(data).map(([name, value]) => ({
    name: platformLabel(name),
    value: value as number,
    itemStyle: { color: platformColors[name] || '#909399' },
  }))
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0 },
    series: [{ type: 'pie', radius: ['40%', '70%'], avoidLabelOverlap: true, itemStyle: { borderRadius: 6 }, label: { show: true, formatter: '{b}\n{d}%' }, data: seriesData }],
  }
})

const barOption = computed(() => {
  const data = store.stats?.by_expiry
  if (!data) return {}
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: Object.keys(data) },
    yAxis: { type: 'value', minInterval: 1 },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    series: [{ type: 'bar', data: Object.values(data).map(Number), itemStyle: { borderRadius: [4, 4, 0, 0], color: '#409eff' } }],
  }
})

onMounted(async () => {
  loading.value = true
  try {
    await store.fetchStats()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.dashboard-container {
  width: 100%;
}

.stat-row {
  margin-bottom: 24px;
}

.stat-card {
  text-align: center;
  border-radius: 12px !important;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border: none !important;
  overflow: hidden;
  position: relative;
}

.stat-card--blue {
  background: linear-gradient(135deg, #4361ee 0%, #6c83f2 100%) !important;
}

.stat-card--orange {
  background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%) !important;
}

.stat-card--red {
  background: linear-gradient(135deg, #ef4444 0%, #f87171 100%) !important;
}

.stat-card--green {
  background: linear-gradient(135deg, #10b981 0%, #34d399 100%) !important;
}

.stat-card :deep(.el-statistic__head) {
  color: rgba(255, 255, 255, 0.85) !important;
  font-size: 13px;
}

.stat-card :deep(.el-statistic__number) {
  color: #fff !important;
  font-size: 28px;
  font-weight: 700;
}

.stat-card :deep(.el-statistic__prefix .el-icon) {
  color: rgba(255, 255, 255, 0.9) !important;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15) !important;
}

.chart-row {
  margin-top: 0;
}

.chart-card {
  border-radius: 12px !important;
}

.chart-header {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
}

.chart-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 350px;
}
</style>
