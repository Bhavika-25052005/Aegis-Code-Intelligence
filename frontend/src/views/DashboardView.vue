<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '../stores/project'

const router = useRouter()
const projectStore = useProjectStore()

const confirmId = ref<string | null>(null)   // project id pending delete confirmation
const deleting = ref(false)

onMounted(() => {
  projectStore.fetchProjects()
})

function getStatusColor(status: string) {
  switch (status) {
    case 'completed': return 'text-green-600 bg-green-50 dark:bg-green-900/30 dark:text-green-400'
    case 'running':   return 'text-blue-600 bg-blue-50 dark:bg-blue-900/30 dark:text-blue-400'
    case 'failed':    return 'text-red-600 bg-red-50 dark:bg-red-900/30 dark:text-red-400'
    default:          return 'text-gray-600 bg-gray-100 dark:bg-gray-700 dark:text-gray-300'
  }
}

function askDelete(event: MouseEvent, id: string) {
  event.stopPropagation()   // don't navigate to the project
  confirmId.value = id
}

function cancelDelete() {
  confirmId.value = null
}

async function confirmDelete() {
  if (!confirmId.value) return
  deleting.value = true
  try {
    await projectStore.deleteProject(confirmId.value)
  } finally {
    deleting.value = false
    confirmId.value = null
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
        class="relative bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 hover:shadow-md transition-shadow cursor-pointer group"
        @click="router.push(`/projects/${project.id}/backlog`)"
      >
        <!-- Delete button - visible on hover -->
        <button
          @click="askDelete($event, project.id)"
          class="absolute top-3 right-3 p-1.5 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 opacity-0 group-hover:opacity-100 transition-opacity"
          title="Delete project"
        >
          <i class="pi pi-trash text-sm"></i>
        </button>

        <div class="flex items-start justify-between mb-3 pr-6">
          <h3 class="font-semibold text-gray-800 dark:text-white">{{ project.name }}</h3>
          <span
            class="text-xs px-2 py-1 rounded-full font-medium"
            :class="getStatusColor(project.is_repo_cloned ? 'completed' : 'pending')"
          >
            {{ project.is_repo_cloned ? 'Ready' : 'Setup' }}
          </span>
        </div>
        <p class="text-sm text-gray-500 dark:text-gray-400 truncate">
          {{ project.github_repo_url || 'No repo configured' }}
        </p>
        <div class="flex items-center gap-4 mt-3 text-xs text-gray-400">
          <span><i class="pi pi-calendar mr-1"></i>{{ new Date(project.created_at).toLocaleDateString() }}</span>
          <span><i class="pi pi-git-branch mr-1"></i>{{ project.pr_strategy }}</span>
        </div>
      </div>
    </div>

    <!-- Delete confirmation modal -->
    <Teleport to="body">
      <div
        v-if="confirmId"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        @click.self="cancelDelete"
      >
        <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-6 w-full max-w-sm mx-4">
          <div class="flex items-center gap-3 mb-4">
            <div class="w-10 h-10 rounded-full bg-red-100 dark:bg-red-900/40 flex items-center justify-center flex-shrink-0">
              <i class="pi pi-trash text-red-600 dark:text-red-400"></i>
            </div>
            <div>
              <h3 class="font-semibold text-gray-800 dark:text-white">Delete project?</h3>
              <p class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                "{{ projectStore.projects.find(p => p.id === confirmId)?.name }}"
              </p>
            </div>
          </div>
          <p class="text-sm text-gray-500 dark:text-gray-400 mb-5">
            This will permanently delete the project, its backlog, all analyses and execution history.
            This cannot be undone.
          </p>
          <div class="flex gap-3 justify-end">
            <button
              @click="cancelDelete"
              class="px-4 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              Cancel
            </button>
            <button
              @click="confirmDelete"
              :disabled="deleting"
              class="px-4 py-2 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 flex items-center gap-2"
            >
              <i v-if="deleting" class="pi pi-spin pi-spinner text-xs"></i>
              {{ deleting ? 'Deleting...' : 'Delete' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
