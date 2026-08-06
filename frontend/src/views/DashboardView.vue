<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '../stores/project'

const router = useRouter()
const projectStore = useProjectStore()

onMounted(() => {
  projectStore.fetchProjects()
})

function getStatusColor(status: string) {
  switch (status) {
    case 'completed': return 'text-green-600 bg-green-50'
    case 'running': return 'text-blue-600 bg-blue-50'
    case 'failed': return 'text-red-600 bg-red-50'
    default: return 'text-gray-600 bg-gray-50'
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h2 class="text-2xl font-bold text-gray-800 dark:text-white">Dashboard</h2>
      <button
        @click="router.push('/projects/new')"
        class="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
      >
        <i class="pi pi-plus"></i>
        New Project
      </button>
    </div>

    <div v-if="projectStore.loading" class="flex justify-center py-12">
      <i class="pi pi-spin pi-spinner text-3xl text-blue-600"></i>
    </div>

    <div v-else-if="projectStore.projects.length === 0" class="text-center py-12">
      <i class="pi pi-folder-open text-5xl text-gray-300 mb-4"></i>
      <p class="text-gray-500 text-lg">No projects yet</p>
      <p class="text-gray-400 text-sm mt-1">Create your first project to get started</p>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="project in projectStore.projects"
        :key="project.id"
        class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 hover:shadow-md transition-shadow cursor-pointer"
        @click="router.push(`/projects/${project.id}/backlog`)"
      >
        <div class="flex items-start justify-between mb-3">
          <h3 class="font-semibold text-gray-800 dark:text-white">{{ project.name }}</h3>
          <span
            class="text-xs px-2 py-1 rounded-full font-medium"
            :class="getStatusColor(project.is_repo_cloned ? 'completed' : 'pending')"
          >
            {{ project.is_repo_cloned ? 'Ready' : 'Setup' }}
          </span>
        </div>
        <p class="text-sm text-gray-500 dark:text-gray-400 truncate">{{ project.github_repo_url || 'No repo configured' }}</p>
        <div class="flex items-center gap-4 mt-3 text-xs text-gray-400">
          <span><i class="pi pi-calendar mr-1"></i>{{ new Date(project.created_at).toLocaleDateString() }}</span>
          <span><i class="pi pi-git-branch mr-1"></i>{{ project.pr_strategy }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
