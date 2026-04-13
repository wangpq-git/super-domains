<template>
  <el-config-provider :locale="locale">
    <router-view />
  </el-config-provider>
</template>

<script setup lang="ts">
import zhCn from 'element-plus/es/locale/lang/zh-cn'

const locale = zhCn
</script>

<style>
:root {
  --dm-primary: #4361ee;
  --dm-primary-light: #6c83f2;
  --dm-primary-dark: #3451d1;
  --dm-success: #10b981;
  --dm-warning: #f59e0b;
  --dm-danger: #ef4444;
  --dm-info: #64748b;

  --dm-sidebar-bg: #172633;
  --dm-sidebar-active: rgba(67, 97, 238, 0.18);
  --dm-sidebar-active-text: #dbe7ff;
  --dm-sidebar-text: #9fb0c1;
  --dm-sidebar-hover-bg: rgba(255, 255, 255, 0.06);

  --dm-card-radius: 14px;
  --dm-card-shadow: 0 12px 32px rgba(15, 23, 42, 0.06), 0 2px 8px rgba(15, 23, 42, 0.04);
  --dm-card-shadow-hover: 0 20px 42px rgba(15, 23, 42, 0.1);

  --dm-page-bg: linear-gradient(180deg, #f4f7fb 0%, #eef3f9 100%);
  --dm-header-height: 64px;
  --dm-content-padding: 28px;
  --dm-content-max-width: 1600px;

  --dm-surface-soft: #f8fafc;
  --dm-border: rgba(148, 163, 184, 0.18);
  --dm-text-primary: #0f172a;
  --dm-text-secondary: #475569;
  --dm-text-tertiary: #64748b;

  --dm-gradient-blue: linear-gradient(135deg, #4361ee 0%, #6c83f2 100%);
  --dm-gradient-orange: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%);
  --dm-gradient-red: linear-gradient(135deg, #ef4444 0%, #f87171 100%);
  --dm-gradient-green: linear-gradient(135deg, #10b981 0%, #34d399 100%);

  --dm-font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  margin: 0;
  min-height: 100%;
}

body {
  font-family: var(--dm-font-family);
  color: var(--dm-text-primary);
  background: #eef3f9;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

a {
  color: inherit;
}

.page-stack {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.page-grid-4 {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.page-grid-3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.data-card {
  border-radius: 18px;
  overflow: hidden;
}

.data-card :where(.el-card__header) {
  padding-bottom: 14px;
}

.section-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--dm-text-primary);
}

.section-subtitle {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--dm-text-tertiary);
}

.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 70px;
}

.el-card {
  border-radius: var(--dm-card-radius) !important;
  border: 1px solid var(--dm-border) !important;
  box-shadow: var(--dm-card-shadow) !important;
  backdrop-filter: blur(8px);
}

.el-card:hover {
  box-shadow: var(--dm-card-shadow-hover) !important;
}

.el-table {
  --el-table-border-color: #edf2f7;
  --el-table-row-hover-bg-color: #f8fbff;
  font-size: 13px;
}

.el-table th.el-table__cell {
  background-color: #f8fafc !important;
  color: #5b6778;
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.02em;
}

.el-table .el-table__row {
  transition: background-color 0.2s ease;
}

.el-dialog {
  border-radius: 16px !important;
  overflow: hidden;
}

.el-dialog__header {
  border-bottom: 1px solid #eef2f7;
  padding-bottom: 16px !important;
}

.el-dialog__footer {
  border-top: 1px solid #eef2f7;
  padding-top: 16px !important;
}

.el-pagination {
  --el-pagination-font-size: 13px;
}

.el-tag--small {
  border-radius: 999px;
}

.el-empty {
  padding: 48px 0;
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

@media (max-width: 1200px) {
  .page-grid-4 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .page-grid-3 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  :root {
    --dm-content-padding: 16px;
  }

  .page-grid-4,
  .page-grid-3 {
    grid-template-columns: 1fr;
  }

  .table-toolbar {
    align-items: stretch;
  }
}
</style>
