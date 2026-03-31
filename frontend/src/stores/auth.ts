import { defineStore } from 'pinia'
import { ref } from 'vue'
import { login as loginApi, getMe } from '@/api/auth'
import router from '@/router'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref<any>(null)

  async function login(username: string, password: string) {
    const { data } = await loginApi(username, password)
    token.value = data.access_token
    localStorage.setItem('token', data.access_token)
    await fetchUser()
    router.push('/dashboard')
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    router.push('/login')
  }

  async function fetchUser() {
    if (!token.value) return
    try {
      const { data } = await getMe()
      user.value = data
    } catch {
      logout()
    }
  }

  return { token, user, login, logout, fetchUser }
})
