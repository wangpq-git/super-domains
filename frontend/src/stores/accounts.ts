import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAccounts } from '@/api/accounts'

export const useAccountsStore = defineStore('accounts', () => {
  const accounts = ref<any[]>([])
  const total = ref(0)
  const loading = ref(false)
  const sortBy = ref('created_at')
  const sortOrder = ref('desc')
  const page = ref(1)
  const pageSize = ref(20)
  const platform = ref('')
  const syncStatus = ref('')
  const keyword = ref('')

  async function fetchAccounts(force = false) {
    loading.value = true
    try {
      const { data } = await getAccounts({
        sort_by: sortBy.value,
        sort_order: sortOrder.value,
        page: page.value,
        page_size: pageSize.value,
        platform: platform.value || undefined,
        sync_status: syncStatus.value || undefined,
        keyword: keyword.value || undefined,
      }, force)
      accounts.value = data.items ?? data.data ?? data ?? []
      total.value = data.total ?? accounts.value.length
    } finally {
      loading.value = false
    }
  }

  return { accounts, total, loading, sortBy, sortOrder, page, pageSize, platform, syncStatus, keyword, fetchAccounts }
})
