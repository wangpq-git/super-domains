import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as loginApi, getMe } from '@/api/auth'
import { invalidateCache } from '@/api/request'
import router from '@/router'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref<any>(null)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function login(username: string, password: string) {
    const { data } = await loginApi(username, password)
    token.value = data.access_token
    localStorage.setItem('token', data.access_token)
    invalidateCache()
    await fetchUser(true)
    router.push('/dashboard')
  }

  function logout() {
    invalidateCache()
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    router.push('/login')
  }

  async function fetchUser(force = false) {
    if (!token.value) return
    try {
      const { data } = await getMe(force)
      user.value = data
    } catch {
      logout()
    }
  }

  return { token, user, isAdmin, login, logout, fetchUser }
})
