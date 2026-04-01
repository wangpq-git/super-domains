import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAccounts } from '@/api/accounts'

export const useAccountsStore = defineStore('accounts', () => {
  const accounts = ref<any[]>([])
  const loading = ref(false)
  const sortBy = ref('created_at')
  const sortOrder = ref('desc')

  async function fetchAccounts() {
    loading.value = true
    try {
      const { data } = await getAccounts({ sort_by: sortBy.value, sort_order: sortOrder.value })
      accounts.value = data.items ?? data.data ?? data ?? []
    } finally {
      loading.value = false
    }
  }

  return { accounts, loading, sortBy, sortOrder, fetchAccounts }
})
