<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBacklogStore } from '../stores/backlog'
import { useProjectStore } from '../stores/project'
import BacklogUploader from '../components/backlog/BacklogUploader.vue'
import BacklogTree from '../components/backlog/BacklogTree.vue'

const route = useRoute()
const router = useRouter()
const backlogStore = useBacklogStore()
const projectStore = useProjectStore()
const projectId = route.params.id as string

const showUploader = ref(true)
const showSettings = ref(false)
const settingsSaved = ref(false)

const editForm = ref({
  github_repo_url: '',
  github_pat: '',
  pr_strategy: 'per_story',
  workspace_path: '',
  claude_max_budget_usd: 5.0,
})

onMounted(async () => {
  await projectStore.fetchProject(projectId)
  await backlogStore.fetchBacklog(projectId)
  if (backlogStore.backlog && backlogStore.backlog.features.length > 0) {
    showUploader.value = false
  }
  if (projectStore.currentProject) {
    editForm.value.github_repo_url = projectStore.currentProject.github_repo_url
    editForm.value.pr_strategy = projectStore.currentProject.pr_strategy
    editForm.value.workspace_path = projectStore.currentProject.workspace_path
    editForm.value.claude_max_budget_usd = projectStore.currentProject.claude_max_budget_usd
  }
})

function onUploaded() {
  showUploader.value = false
}

function startExecution() {
  router.push(`/projects/${projectId}/execute`)
}

async function saveSettings() {
  const payload: Record<string, unknown> = {}
  if (editForm.value.github_repo_url) payload.github_repo_url = editForm.value.github_repo_url
  if (editForm.value.github_pat) payload.github_pat = editForm.value.github_pat
  if (editForm.value.pr_strategy) payload.pr_strategy = editForm.value.pr_strategy
  if (editForm.value.workspace_path) payload.workspace_path = editForm.value.workspace_path
  payload.claude_max_budget_usd = editForm.value.claude_max_budget_usd

  await projectStore.updateProject(projectId, payload)
  settingsSaved.value = true
  setTimeout(() => { settingsSaved.value = false }, 3000)
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-800 dark:text-white">Backlog</h2>
        <p class="text-sm text-gray-500 dark:text-gray-400">{{ projectStore.currentProject?.name }}</p>
      </div>
      <div class="flex items-center gap-3">
        <button
          @click="showSettings = !showSettings"
          class="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300"
        >
          <i class="pi pi-cog mr-1"></i> Settings
        </button>
        <button
          @click="showUploader = !showUploader"
          class="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300"
        >
          <i class="pi pi-upload mr-1"></i> Import
        </button>
        <button
          v-if="backlogStore.backlog && backlogStore.backlog.total_tasks > 0"
          @click="startExecution"
          class="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2"
        >
          <i class="pi pi-play"></i> Start Code Generation
        </button>
      </div>
    </div>

    <!-- Project Settings Panel -->
    <div v-if="showSettings" class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 space-y-4">
      <h3 class="font-semibold text-gray-800 dark:text-white flex items-center gap-2">
        <i class="pi pi-cog text-blue-500"></i> Project Settings
      </h3>

      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">GitHub Repository URL</label>
          <input
            v-model="editForm.github_repo_url"
            type="text"
            placeholder="https://github.com/owner/repo"
            class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">GitHub Personal Access Token</label>
          <input
            v-model="editForm.github_pat"
            type="password"
            placeholder="ghp_xxxx (leave empty to keep existing)"
            class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
      </div>

      <div class="grid grid-cols-3 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">PR Strategy</label>
          <select
            v-model="editForm.pr_strategy"
            class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="per_task">Per Task</option>
            <option value="per_story">Per User Story</option>
            <option value="per_feature">Per Feature</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Workspace Path (optional)</label>
          <input
            v-model="editForm.workspace_path"
            type="text"
            placeholder="Auto-managed"
            class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Budget/Task (USD)</label>
          <input
            v-model.number="editForm.claude_max_budget_usd"
            type="number"
            min="0.5"
            max="50"
            step="0.5"
            class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
      </div>

      <div class="flex items-center gap-3">
        <button
          @click="saveSettings"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
        >
          Save Settings
        </button>
        <span v-if="settingsSaved" class="text-sm text-green-500 flex items-center gap-1">
          <i class="pi pi-check"></i> Saved
        </span>
        <span v-if="projectStore.currentProject?.is_repo_cloned" class="text-sm text-green-500 flex items-center gap-1 ml-auto">
          <i class="pi pi-check-circle"></i> Repo cloned
        </span>
        <span v-else-if="projectStore.currentProject?.github_repo_url" class="text-sm text-orange-500 flex items-center gap-1 ml-auto">
          <i class="pi pi-info-circle"></i> Repo will be cloned on execution start
        </span>
      </div>
    </div>

    <!-- Stats -->
    <div v-if="backlogStore.backlog" class="grid grid-cols-3 gap-4">
      <div class="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 text-center">
        <div class="text-2xl font-bold text-blue-600">{{ backlogStore.backlog.total_tasks }}</div>
        <div class="text-sm text-gray-500">Total Tasks</div>
      </div>
      <div class="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 text-center">
        <div class="text-2xl font-bold text-green-600">{{ backlogStore.backlog.completed_tasks }}</div>
        <div class="text-sm text-gray-500">Completed</div>
      </div>
      <div class="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 text-center">
        <div class="text-2xl font-bold text-orange-600">{{ backlogStore.backlog.pending_tasks }}</div>
        <div class="text-sm text-gray-500">Pending</div>
      </div>
    </div>

    <!-- Uploader -->
    <BacklogUploader v-if="showUploader" :project-id="projectId" @uploaded="onUploaded" />

    <!-- Backlog Tree -->
    <BacklogTree v-if="backlogStore.backlog && backlogStore.backlog.features.length > 0" :backlog="backlogStore.backlog" />
  </div>
</template>
