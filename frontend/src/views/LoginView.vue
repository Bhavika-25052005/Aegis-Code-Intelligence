<script setup lang="ts">
import { ref } from 'vue'
import { useAuth } from '../composables/useAuth'

const { login } = useAuth()

const email = ref('')
const password = ref('')
const showPassword = ref(false)
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  if (!email.value.trim() || !password.value) {
    error.value = 'Please enter your email and password.'
    return
  }
  loading.value = true
  await new Promise(r => setTimeout(r, 600))
  const ok = login(email.value.trim(), password.value)
  loading.value = false
  if (!ok) {
    error.value = 'Invalid email or password. Please try again.'
    password.value = ''
  }
}

function handleCreateAccount() {
  // dummy - no-op
}
</script>

<template>
  <div class="min-h-screen flex bg-gray-50 dark:bg-gray-900">

    <!-- Left panel: branding (blue accent, matches app primary) -->
    <div class="hidden lg:flex flex-col justify-between w-[44%] bg-blue-600 p-12 relative overflow-hidden">
      <!-- Subtle decorative shapes -->
      <div class="absolute inset-0 overflow-hidden pointer-events-none">
        <div class="absolute -top-16 -left-16 w-64 h-64 rounded-full bg-blue-500/40"></div>
        <div class="absolute bottom-0 right-0 w-80 h-80 rounded-full bg-blue-700/50"></div>
        <div class="absolute top-1/2 left-1/3 w-40 h-40 rounded-full bg-blue-400/20"></div>
      </div>

      <!-- Logo -->
      <div class="relative flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
          <i class="pi pi-code text-white text-xl"></i>
        </div>
        <span class="text-2xl font-bold text-white tracking-tight">Aegis</span>
      </div>

      <!-- Tagline -->
      <div class="relative">
        <h2 class="text-4xl font-bold text-white leading-snug mb-4">
          AI-Powered<br/>Code Generation
        </h2>
        <p class="text-blue-100 text-base leading-relaxed max-w-sm">
          From requirements to deployment-ready code, automated, traceable, and release-gated.
        </p>

        <!-- Feature list -->
        <div class="mt-8 space-y-3">
          <div v-for="item in ['Requirement Intelligence', 'Implementation Planning', 'Automated Testing', 'Quality &amp; Release Readiness']"
            :key="item" class="flex items-center gap-3 text-blue-50">
            <div class="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
              <i class="pi pi-check text-white" style="font-size: 0.6rem"></i>
            </div>
            <span class="text-sm">{{ item }}</span>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="relative text-blue-200 text-xs">
        &copy; {{ new Date().getFullYear() }} Aegis Platform
      </div>
    </div>

    <!-- Right panel: login form -->
    <div class="flex-1 flex items-center justify-center p-6 lg:p-12 bg-gray-50 dark:bg-gray-900">
      <div class="w-full max-w-md">

        <!-- Mobile logo -->
        <div class="flex items-center gap-3 mb-8 lg:hidden">
          <div class="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center">
            <i class="pi pi-code text-white text-lg"></i>
          </div>
          <span class="text-xl font-bold text-gray-800 dark:text-white">Aegis</span>
        </div>

        <!-- Card -->
        <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-md border border-gray-200 dark:border-gray-700 p-8">
          <div class="mb-7">
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Welcome back</h1>
            <p class="text-gray-500 dark:text-gray-400 text-sm mt-1">Sign in to your Aegis account</p>
          </div>

          <form @submit.prevent="handleLogin" class="space-y-5">

            <!-- Email -->
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Email address
              </label>
              <div class="relative">
                <i class="pi pi-envelope absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm"></i>
                <input
                  v-model="email"
                  type="email"
                  autocomplete="email"
                  placeholder="you@company.com"
                  :disabled="loading"
                  class="w-full pl-9 pr-4 py-2.5 text-sm rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-60 transition"
                />
              </div>
            </div>

            <!-- Password -->
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Password
              </label>
              <div class="relative">
                <i class="pi pi-lock absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm"></i>
                <input
                  v-model="password"
                  :type="showPassword ? 'text' : 'password'"
                  autocomplete="current-password"
                  placeholder="&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;"
                  :disabled="loading"
                  class="w-full pl-9 pr-10 py-2.5 text-sm rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-60 transition"
                />
                <button type="button" @click="showPassword = !showPassword" tabindex="-1"
                  class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition">
                  <i :class="showPassword ? 'pi pi-eye-slash' : 'pi pi-eye'" class="text-sm"></i>
                </button>
              </div>
            </div>

            <!-- Error message -->
            <div v-if="error" class="flex items-center gap-2 px-3 py-2.5 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl text-sm text-red-700 dark:text-red-300">
              <i class="pi pi-exclamation-circle flex-shrink-0"></i>
              {{ error }}
            </div>

            <!-- Sign in button -->
            <button
              type="submit"
              :disabled="loading"
              class="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-semibold text-sm rounded-xl transition disabled:opacity-60 disabled:cursor-not-allowed shadow-sm">
              <i v-if="loading" class="pi pi-spin pi-spinner"></i>
              <i v-else class="pi pi-sign-in"></i>
              {{ loading ? 'Signing in...' : 'Sign In' }}
            </button>

            <!-- Divider -->
            <div class="flex items-center gap-3 text-xs text-gray-400">
              <div class="flex-1 h-px bg-gray-200 dark:bg-gray-600"></div>
              <span>or</span>
              <div class="flex-1 h-px bg-gray-200 dark:bg-gray-600"></div>
            </div>

            <!-- Create account (dummy) -->
            <button
              type="button"
              @click="handleCreateAccount"
              class="w-full flex items-center justify-center gap-2 px-4 py-2.5 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 font-medium text-sm rounded-xl transition">
              <i class="pi pi-user-plus"></i>
              Create new account
            </button>

          </form>
        </div>

        <p class="text-center text-xs text-gray-400 dark:text-gray-500 mt-5">
          Aegis - AI-Powered Code Generation Platform
        </p>
      </div>
    </div>

  </div>
</template>
