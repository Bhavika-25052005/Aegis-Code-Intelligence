<script setup lang="ts">
import { ref } from 'vue'
import { useBacklogStore } from '../../stores/backlog'

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ imported: [] }>()

const backlogStore = useBacklogStore()
const loading = ref(false)
const error = ref('')

const form = ref({
  org_url: '',
  project: '',
  pat: '',
  query: '',
})

async function handleImport() {
  error.value = ''
  loading.value = true
  try {
    await backlogStore.importFromAzureDevOps(props.projectId, form.value)
    emit('imported')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Import failed'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 space-y-4">
    <h3 class="font-semibold text-gray-800 dark:text-white flex items-center gap-2">
      <i class="pi pi-microsoft text-blue-500"></i>
      Import from Azure DevOps
    </h3>

    <div class="grid grid-cols-2 gap-4">
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Organization URL</label>
        <input
          v-model="form.org_url"
          type="text"
          placeholder="https://dev.azure.com/your-org"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Project</label>
        <input
          v-model="form.project"
          type="text"
          placeholder="Project name"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>
    </div>

    <div>
      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Personal Access Token</label>
      <input
        v-model="form.pat"
        type="password"
        placeholder="Azure DevOps PAT"
        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
      />
    </div>

    <div>
      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Custom WIQL Query (Optional)</label>
      <textarea
        v-model="form.query"
        rows="3"
        placeholder="Leave empty for default query (all Features, User Stories, and Tasks)"
        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
      ></textarea>
    </div>

    <div class="flex items-center gap-3">
      <button
        @click="handleImport"
        :disabled="!form.org_url || !form.project || !form.pat || loading"
        class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center gap-2"
      >
        <i v-if="loading" class="pi pi-spin pi-spinner"></i>
        <i v-else class="pi pi-download"></i>
        {{ loading ? 'Importing...' : 'Import Backlog' }}
      </button>
      <span v-if="error" class="text-sm text-red-500">{{ error }}</span>
    </div>
  </div>
</template>
