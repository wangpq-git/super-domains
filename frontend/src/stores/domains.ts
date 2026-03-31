import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getDomains, getDomainStats } from '@/api/domains'
import type { DomainParams } from '@/api/domains'

export const useDomainsStore = defineStore('domains', () => {
  const domains = ref<any[]>([])
  const stats = ref<any>(null)
  const total = ref(0)
  const loading = ref(false)

  const filters = ref<DomainParams>({
    platform: '',
    status: '',
    search: '',
    expiry_start: '',
    expiry_end: '',
    page: 1,
    page_size: 20,
  })

  async function fetchDomains() {
    loading.value = true
    try {
      const { data } = await getDomains(filters.value)
      domains.value = data.items ?? data.data ?? []
      total.value = data.total ?? domains.value.length
    } finally {
      loading.value = false
    }
  }

  async function fetchStats() {
    try {
      const { data } = await getDomainStats()
      stats.value = data
    } catch {
      stats.value = null
    }
  }

  function resetFilters() {
    filters.value = {
      platform: '',
      status: '',
      search: '',
      expiry_start: '',
      expiry_end: '',
      page: 1,
      page_size: 20,
    }
  }

  return { domains, stats, total, loading, filters, fetchDomains, fetchStats, resetFilters }
})
