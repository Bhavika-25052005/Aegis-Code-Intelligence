import { ref } from 'vue'

const VALID_EMAIL = 'Bhavika.Bandu@Philips.com'
const VALID_PASSWORD = 'test'
const STORAGE_KEY = 'aegis_auth_user'

const stored = localStorage.getItem(STORAGE_KEY)
const currentUser = ref<{ email: string; name: string } | null>(
  stored ? JSON.parse(stored) : null
)

export function useAuth() {
  function login(email: string, password: string): boolean {
    if (email.toLowerCase() === VALID_EMAIL.toLowerCase() && password === VALID_PASSWORD) {
      const user = { email: VALID_EMAIL, name: 'Bhavika Bandu' }
      currentUser.value = user
      localStorage.setItem(STORAGE_KEY, JSON.stringify(user))
      return true
    }
    return false
  }

  function logout() {
    currentUser.value = null
    localStorage.removeItem(STORAGE_KEY)
  }

  function getInitials(name: string): string {
    return name.split(' ').map(p => p[0]).join('').toUpperCase().slice(0, 2)
  }

  return { currentUser, login, logout, getInitials }
}
