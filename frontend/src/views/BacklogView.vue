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

onMounted(async () => {
  await projectStore.fetchProject(projectId)
  await backlogStore.fetchBacklog(projectId)
  if (backlogStore.backlog && backlogStore.backlog.features.length > 0) {
    showUploader.value = false
  }
})

function onUploaded() {
  showUploader.value = false
}

function startExecution() {
  router.push(`/projects/${projectId}/execute`)
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
