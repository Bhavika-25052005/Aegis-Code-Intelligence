<script setup lang="ts">
import { ref } from 'vue'
import { useAuth } from '../../composables/useAuth'

const { currentUser, logout, getInitials } = useAuth()
const menuOpen = ref(false)

function handleLogout() {
  menuOpen.value = false
  logout()
}
</script>

<template>
  <header class="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-3 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
        <i class="pi pi-code text-white text-sm"></i>
      </div>
      <h1 class="text-xl font-bold text-gray-800 dark:text-white">Aegis</h1>
    </div>

    <div class="flex items-center gap-4">
      <span class="hidden sm:block text-sm text-gray-500 dark:text-gray-400">AI-Powered Code Generation</span>

      <!-- Profile menu -->
      <div v-if="currentUser" class="relative">
        <button
          @click="menuOpen = !menuOpen"
          class="flex items-center gap-2.5 rounded-xl px-2 py-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 transition group"
          :aria-expanded="menuOpen">
          <!-- Avatar -->
          <div class="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center flex-shrink-0 shadow-sm">
            <span class="text-xs font-bold text-white">{{ getInitials(currentUser.name) }}</span>
          </div>
          <!-- Name (hidden on small screens) -->
          <span class="hidden md:block text-sm font-medium text-gray-700 dark:text-gray-200 max-w-[120px] truncate">
            {{ currentUser.name }}
          </span>
          <i class="pi pi-chevron-down text-xs text-gray-400 transition-transform" :class="{ 'rotate-180': menuOpen }"></i>
        </button>

        <!-- Dropdown -->
        <Transition
          enter-active-class="transition duration-100 ease-out"
          enter-from-class="opacity-0 scale-95 translate-y-1"
          enter-to-class="opacity-100 scale-100 translate-y-0"
          leave-active-class="transition duration-75 ease-in"
          leave-from-class="opacity-100 scale-100 translate-y-0"
          leave-to-class="opacity-0 scale-95 translate-y-1">
          <div v-if="menuOpen"
            class="absolute right-0 top-full mt-2 w-60 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-lg z-50 overflow-hidden origin-top-right">

            <!-- User info -->
            <div class="flex items-center gap-3 px-4 py-3 border-b border-gray-100 dark:border-gray-700">
              <div class="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center flex-shrink-0 shadow-sm">
                <span class="text-sm font-bold text-white">{{ getInitials(currentUser.name) }}</span>
              </div>
              <div class="min-w-0">
                <p class="text-sm font-semibold text-gray-800 dark:text-white truncate">{{ currentUser.name }}</p>
                <p class="text-xs text-gray-500 dark:text-gray-400 truncate">{{ currentUser.email }}</p>
              </div>
            </div>

            <!-- Actions -->
            <div class="p-1.5">
              <button
                @click="handleLogout"
                class="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition">
                <i class="pi pi-sign-out text-sm"></i>
                Sign out
              </button>
            </div>
          </div>
        </Transition>

        <!-- Click-outside overlay -->
        <div v-if="menuOpen" class="fixed inset-0 z-40" @click="menuOpen = false"></div>
      </div>
    </div>
  </header>
</template>
