<script setup lang="ts">
import AppLayout from './components/layout/AppLayout.vue'
import LoginView from './views/LoginView.vue'
import { useAuth } from './composables/useAuth'

const { currentUser } = useAuth()
</script>

<template>
  <LoginView v-if="!currentUser" />
  <AppLayout v-else>
    <router-view />
  </AppLayout>
</template>
