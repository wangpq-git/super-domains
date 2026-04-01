<template>
  <router-view />
</template>

<style>
/* ============ Global Design Tokens ============ */
:root {
  /* Primary palette */
  --dm-primary: #4361ee;
  --dm-primary-light: #6c83f2;
  --dm-primary-dark: #3451d1;

  /* Sidebar */
  --dm-sidebar-bg: #1d2b36;
  --dm-sidebar-active: rgba(67, 97, 238, 0.15);
  --dm-sidebar-active-text: #4361ee;
  --dm-sidebar-text: #a3b1bf;
  --dm-sidebar-hover-bg: rgba(255, 255, 255, 0.06);

  /* Status colors */
  --dm-success: #10b981;
  --dm-warning: #f59e0b;
  --dm-danger: #ef4444;
  --dm-info: #6b7280;

  /* Card */
  --dm-card-radius: 8px;
  --dm-card-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
  --dm-card-shadow-hover: 0 10px 25px rgba(0, 0, 0, 0.08);

  /* Layout */
  --dm-page-bg: #f5f7fa;
  --dm-header-height: 56px;
  --dm-content-padding: 24px;

  /* Gradient presets */
  --dm-gradient-blue: linear-gradient(135deg, #4361ee 0%, #6c83f2 100%);
  --dm-gradient-orange: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%);
  --dm-gradient-red: linear-gradient(135deg, #ef4444 0%, #f87171 100%);
  --dm-gradient-green: linear-gradient(135deg, #10b981 0%, #34d399 100%);

  /* Typography */
  --dm-font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
}

/* ============ Global Resets ============ */
body {
  margin: 0;
  font-family: var(--dm-font-family);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ============ Element Plus Overrides ============ */
.el-card {
  border-radius: var(--dm-card-radius) !important;
  border: none !important;
  box-shadow: var(--dm-card-shadow) !important;
}

.el-card:hover {
  box-shadow: var(--dm-card-shadow-hover) !important;
}

.el-table {
  --el-table-border-color: #f0f0f0;
  --el-table-row-hover-bg-color: #f8fafc;
  font-size: 13px;
}

.el-table th.el-table__cell {
  background-color: #fafbfc !important;
  color: #606266;
  font-weight: 600;
  font-size: 13px;
}

.el-table .el-table__row {
  transition: background-color 0.2s ease;
}

.el-dialog {
  border-radius: 12px !important;
}

.el-dialog__header {
  border-bottom: 1px solid #f0f0f0;
  padding-bottom: 16px !important;
}

.el-dialog__footer {
  border-top: 1px solid #f0f0f0;
  padding-top: 16px !important;
}

/* Pagination */
.el-pagination {
  --el-pagination-font-size: 13px;
}

/* Tag refinements */
.el-tag--small {
  border-radius: 4px;
}

/* Transition for route views */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.25s ease;
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
