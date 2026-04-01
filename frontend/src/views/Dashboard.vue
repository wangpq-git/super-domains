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
  padding: 20px;
}

.stat-row {
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
  border-radius: 8px;
  transition: all 0.3s;
  border-left: 4px solid transparent;
}

.stat-card--blue {
  border-left-color: #409eff;
}

.stat-card--orange {
  border-left-color: #e6a23c;
}

.stat-card--red {
  border-left-color: #f56c6c;
}

.stat-card--green {
  border-left-color: #67c23a;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.chart-row {
  margin-top: 20px;
}

.chart-card {
  border-radius: 8px;
}

.chart-header {
  font-size: 16px;
  font-weight: 600;
}

.chart-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 350px;
}
</style>
