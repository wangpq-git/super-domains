<template>
  <div class="dashboard-container page-stack" v-loading="loading">
    <PageHero
      eyebrow="OVERVIEW"
      title="运行概览"
      subtitle="聚合域名规模、到期风险和平台接入情况，帮助你先看最需要处理的资产。"
      tone="blue"
    >
      <template #meta>
        <el-tag effect="plain" round>共 {{ stats?.total_domains ?? 0 }} 个域名</el-tag>
      </template>
    </PageHero>

    <section class="page-grid-4">
      <el-card shadow="hover" class="stat-card stat-card--blue">
        <el-statistic title="域名总数" :value="stats?.total_domains ?? 0">
          <template #prefix><el-icon><Connection /></el-icon></template>
        </el-statistic>
      </el-card>
      <el-card shadow="hover" class="stat-card stat-card--orange">
        <el-statistic title="30 天内到期" :value="stats?.expiring_soon ?? 0">
          <template #prefix><el-icon><Warning /></el-icon></template>
        </el-statistic>
      </el-card>
      <el-card shadow="hover" class="stat-card stat-card--red">
        <el-statistic title="已过期" :value="stats?.expired ?? 0">
          <template #prefix><el-icon><CircleClose /></el-icon></template>
        </el-statistic>
      </el-card>
      <el-card shadow="hover" class="stat-card stat-card--green">
        <el-statistic title="接入平台" :value="stats?.platform_count ?? 0">
          <template #prefix><el-icon><Monitor /></el-icon></template>
        </el-statistic>
      </el-card>
    </section>

    <section class="page-grid-3 dashboard-insights">
      <el-card shadow="never" class="insight-card">
        <p class="insight-label">到期压力</p>
        <strong class="insight-value">{{ riskSummary }}</strong>
        <span class="insight-hint">根据 30 天内到期和过期数量自动计算。</span>
      </el-card>
      <el-card shadow="never" class="insight-card">
        <p class="insight-label">平台覆盖</p>
        <strong class="insight-value">{{ stats?.platform_count ?? 0 }} / 9</strong>
        <span class="insight-hint">当前已接入的注册商与 DNS 平台数量。</span>
      </el-card>
      <el-card shadow="never" class="insight-card">
        <p class="insight-label">优先动作</p>
        <strong class="insight-value">{{ nextAction }}</strong>
        <span class="insight-hint">建议先从到期风险最高的资产清单开始处理。</span>
      </el-card>
    </section>

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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { CircleClose, Connection, Monitor, Warning } from '@element-plus/icons-vue'
import { use } from 'echarts/core'
import { PieChart, BarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import PageHero from '@/components/PageHero.vue'
import { useDomainsStore } from '@/stores/domains'
import { platformLabel } from '@/utils/format'

use([PieChart, BarChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

const store = useDomainsStore()
const loading = ref(false)

const stats = computed(() => store.stats)
const riskSummary = computed(() => {
  const expiring = stats.value?.expiring_soon ?? 0
  const expired = stats.value?.expired ?? 0
  if (expired > 0) return '高风险'
  if (expiring > 10) return '中高风险'
  if (expiring > 0) return '可控'
  return '稳定'
})
const nextAction = computed(() => {
  if ((stats.value?.expired ?? 0) > 0) return '优先处理已过期域名'
  if ((stats.value?.expiring_soon ?? 0) > 0) return '安排近期续费检查'
  return '继续补齐平台接入'
})

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
    series: [{ type: 'pie', radius: ['42%', '72%'], avoidLabelOverlap: true, itemStyle: { borderRadius: 8 }, label: { show: true, formatter: '{b}\n{d}%' }, data: seriesData }],
  }
})

const barOption = computed(() => {
  const data = store.stats?.by_expiry
  if (!data) return {}
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: Object.keys(data), axisTick: { show: false } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#e2e8f0' } } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    series: [{ type: 'bar', data: Object.values(data).map(Number), barMaxWidth: 42, itemStyle: { borderRadius: [8, 8, 0, 0], color: '#4361ee' } }],
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

.dashboard-insights,
.dashboard-charts {
  align-items: stretch;
}

.stat-card {
  overflow: hidden;
  position: relative;
  border: none !important;
}

.stat-card :deep(.el-statistic) {
  text-align: left;
}

.stat-card :deep(.el-statistic__head) {
  color: rgba(255, 255, 255, 0.82) !important;
  font-size: 13px;
}

.stat-card :deep(.el-statistic__number) {
  color: #fff !important;
  font-size: 30px;
  font-weight: 700;
}

.stat-card :deep(.el-statistic__prefix) {
  color: rgba(255, 255, 255, 0.92);
}

.stat-card--blue { background: var(--dm-gradient-blue) !important; }
.stat-card--orange { background: var(--dm-gradient-orange) !important; }
.stat-card--red { background: var(--dm-gradient-red) !important; }
.stat-card--green { background: var(--dm-gradient-green) !important; }

.insight-card {
  min-height: 154px;
  padding: 4px;
}

.insight-label {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #64748b;
}

.insight-value {
  display: block;
  margin-top: 16px;
  font-size: 28px;
  color: #0f172a;
}

.insight-hint {
  display: block;
  margin-top: 12px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
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
  .insight-card {
    min-height: auto;
  }

  .chart-card {
    min-height: auto;
  }

  .chart-canvas {
    height: 300px;
  }
}
</style>
