import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      imports: ['vue', 'vue-router'],
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
      dts: 'src/auto-imports.d.ts',
      eslintrc: {
        enabled: false,
      },
    }),
    Components({
      resolvers: [ElementPlusResolver({ importStyle: 'css', directives: true })],
      dts: 'src/components.d.ts',
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          if (id.includes('echarts') || id.includes('zrender') || id.includes('vue-echarts')) {
            return 'charts-vendor'
          }

          if (id.includes('@element-plus/icons-vue')) {
            return 'element-icons'
          }

          if (id.includes('element-plus') || id.includes('@ctrl/tinycolor')) {
            return 'element-plus'
          }

          if (id.includes('vue') || id.includes('pinia') || id.includes('vue-router')) {
            return 'vue-core'
          }

          return 'vendor'
        },
      }
    }
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://app:8000',
        changeOrigin: true,
      }
    }
  }
})
