import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAccounts } from '@/api/accounts'

export const useAccountsStore = defineStore('accounts', () => {
  const accounts = ref<any[]>([])
  const loading = ref(false)

  async function fetchAccounts() {
    loading.value = true
    try {
      const { data } = await getAccounts()
      accounts.value = data.items ?? data.data ?? data ?? []
    } finally {
      loading.value = false
    }
  }

  return { accounts, loading, fetchAccounts }
})
