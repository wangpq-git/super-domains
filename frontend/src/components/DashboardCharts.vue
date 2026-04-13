<template>
  <section class="page-grid-3 dashboard-charts">
    <el-card shadow="never" class="chart-card chart-card--wide">
      <template #header>
        <div>
          <h3 class="section-title">域名平台分布</h3>
          <p class="section-subtitle">观察域名在哪些平台集中，便于后续同步和权限收口。</p>
        </div>
      </template>
      <div class="chart-wrapper">
        <v-chart v-if="stats?.by_platform" :option="pieOption" autoresize class="chart-canvas" />
        <el-empty v-else description="暂无平台分布数据" />
      </div>
    </el-card>

    <el-card shadow="never" class="chart-card chart-card--wide">
      <template #header>
        <div>
          <h3 class="section-title">到期时间分布</h3>
          <p class="section-subtitle">快速判断近期续费窗口是否集中，避免集中到期造成风险。</p>
        </div>
      </template>
      <div class="chart-wrapper">
        <v-chart v-if="stats?.by_expiry" :option="barOption" autoresize class="chart-canvas" />
        <el-empty v-else description="暂无到期分布数据" />
      </div>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { use } from 'echarts/core'
import { PieChart, BarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { platformLabel } from '@/utils/format'

interface DashboardStats {
  by_platform?: Record<string, number>
  by_expiry?: Record<string, number>
}

const props = defineProps<{
  stats: DashboardStats | null
}>()

use([PieChart, BarChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

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
  const data = props.stats?.by_platform
  if (!data) return {}
  const seriesData = Object.entries(data).map(([name, value]) => ({
    name: platformLabel(name),
    value: value as number,
    itemStyle: { color: platformColors[name] || '#909399' },
  }))
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0 },
    series: [{ type: 'pie', radius: ['42%', '72%'], avoidLabelOverlap: true, itemStyle: { borderRadius: 8 }, label: { show: true, formatter: '{b}\n{d}%' }, data: seriesData }],
  }
})

const barOption = computed(() => {
  const data = props.stats?.by_expiry
  if (!data) return {}
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: Object.keys(data), axisTick: { show: false } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#e2e8f0' } } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    series: [{ type: 'bar', data: Object.values(data).map(Number), barMaxWidth: 42, itemStyle: { borderRadius: [8, 8, 0, 0], color: '#4361ee' } }],
  }
})
</script>

<style scoped>
.dashboard-charts {
  align-items: stretch;
}

.chart-card {
  min-height: 420px;
}

.chart-card--wide {
  grid-column: span 1;
}

.chart-wrapper {
  min-height: 340px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chart-canvas {
  height: 360px;
  width: 100%;
}

@media (max-width: 768px) {
  .chart-card {
    min-height: auto;
  }

  .chart-wrapper,
  .chart-canvas {
    min-height: 280px;
    height: 280px;
  }
}
</style>
