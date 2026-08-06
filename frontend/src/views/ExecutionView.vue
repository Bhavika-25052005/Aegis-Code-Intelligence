<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useExecutionStore } from '../stores/execution'
import { useBacklogStore } from '../stores/backlog'
import { useWebSocket } from '../composables/useWebSocket'

const route = useRoute()
const executionStore = useExecutionStore()
const backlogStore = useBacklogStore()
const projectId = route.params.id as string

const { connected, messages, connect } = useWebSocket(projectId)
const taskStatuses = ref<Record<string, { status: string; title: string }>>({})

onMounted(async () => {
  await backlogStore.fetchBacklog(projectId)
  await executionStore.fetchStatus(projectId)
  connect()
})

watch(messages, (msgs) => {
  const latest = msgs[msgs.length - 1]
  if (!latest) return

  if (latest.type === 'task_status_change') {
    const payload = latest.payload as { task_id: string; status: string; title?: string }
    taskStatuses.value[payload.task_id] = {
      status: payload.status,
      title: payload.title || '',
    }
    executionStore.addLog(`[${payload.status.toUpperCase()}] ${payload.title || payload.task_id}`)
  } else if (latest.type === 'pr_created') {
    const payload = latest.payload as { pr_url: string; title: string }
    executionStore.addLog(`[PR] Created: ${payload.title} - ${payload.pr_url}`)
  } else if (latest.type === 'execution_complete') {
    executionStore.addLog('[DONE] Execution completed')
  }
}, { deep: true })

async function handleStart() {
  executionStore.clearLogs()
  await executionStore.startExecution(projectId)
}

async function handlePause() {
  await executionStore.pauseExecution(projectId)
}

async function handleResume() {
  await executionStore.resumeExecution(projectId)
}

function getStatusIcon(status: string) {
  switch (status) {
    case 'completed': return 'pi pi-check-circle text-green-500'
    case 'in_progress': return 'pi pi-spin pi-spinner text-blue-500'
    case 'failed': return 'pi pi-times-circle text-red-500'
    case 'retry': return 'pi pi-refresh text-orange-500'
    default: return 'pi pi-circle text-gray-300'
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h2 class="text-2xl font-bold text-gray-800 dark:text-white">Execution</h2>
      <div class="flex items-center gap-3">
        <span class="flex items-center gap-1 text-sm" :class="connected ? 'text-green-500' : 'text-red-500'">
          <i class="pi pi-circle-fill text-xs"></i>
          {{ connected ? 'Connected' : 'Disconnected' }}
        </span>
        <button
          v-if="!executionStore.status || executionStore.status.status === 'completed'"
          @click="handleStart"
          :disabled="executionStore.loading"
          class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 flex items-center gap-2"
        >
          <i class="pi pi-play"></i> Start
        </button>
        <button
          v-else-if="executionStore.status?.status === 'running'"
          @click="handlePause"
          class="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 flex items-center gap-2"
        >
          <i class="pi pi-pause"></i> Pause
        </button>
        <button
          v-else-if="executionStore.status?.status === 'paused'"
          @click="handleResume"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
        >
          <i class="pi pi-play"></i> Resume
        </button>
      </div>
    </div>

    <!-- Progress Bar -->
    <div v-if="executionStore.status" class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
      <div class="flex justify-between text-sm mb-2">
        <span class="text-gray-600 dark:text-gray-300">
          Progress: {{ executionStore.status.completed_tasks }} / {{ executionStore.status.total_tasks }} tasks
        </span>
        <span class="font-medium" :class="{
          'text-green-600': executionStore.status.status === 'completed',
          'text-blue-600': executionStore.status.status === 'running',
          'text-yellow-600': executionStore.status.status === 'paused',
          'text-red-600': executionStore.status.status === 'failed',
        }">
          {{ executionStore.status.status.toUpperCase() }}
        </span>
      </div>
      <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
        <div
          class="bg-blue-600 h-3 rounded-full transition-all duration-500"
          :style="{ width: `${executionStore.status.total_tasks > 0 ? (executionStore.status.completed_tasks / executionStore.status.total_tasks) * 100 : 0}%` }"
        ></div>
      </div>
      <div v-if="executionStore.status.failed_tasks > 0" class="mt-2 text-sm text-red-500">
        {{ executionStore.status.failed_tasks }} task(s) failed
      </div>
    </div>

    <!-- Task Status List -->
    <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
      <h3 class="font-semibold text-gray-800 dark:text-white mb-3">Task Progress</h3>
      <div class="space-y-2 max-h-64 overflow-y-auto">
        <div
          v-for="(info, taskId) in taskStatuses"
          :key="taskId"
          class="flex items-center gap-3 py-2 px-3 rounded-lg bg-gray-50 dark:bg-gray-700/50"
        >
          <i :class="getStatusIcon(info.status)"></i>
          <span class="text-sm text-gray-700 dark:text-gray-200 flex-1">{{ info.title || taskId }}</span>
          <span class="text-xs px-2 py-0.5 rounded-full" :class="{
            'bg-green-100 text-green-700': info.status === 'completed',
            'bg-blue-100 text-blue-700': info.status === 'in_progress',
            'bg-red-100 text-red-700': info.status === 'failed',
            'bg-orange-100 text-orange-700': info.status === 'retry',
          }">
            {{ info.status }}
          </span>
        </div>
        <p v-if="Object.keys(taskStatuses).length === 0" class="text-sm text-gray-400 text-center py-4">
          No tasks processed yet. Click Start to begin.
        </p>
      </div>
    </div>

    <!-- Log Viewer -->
    <div class="bg-gray-900 rounded-xl p-5">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-semibold text-gray-200">Logs</h3>
        <button @click="executionStore.clearLogs" class="text-xs text-gray-400 hover:text-white">Clear</button>
      </div>
      <div class="font-mono text-xs text-green-400 max-h-48 overflow-y-auto space-y-1">
        <div v-for="(log, idx) in executionStore.logs" :key="idx">{{ log }}</div>
        <div v-if="executionStore.logs.length === 0" class="text-gray-500">Waiting for events...</div>
      </div>
    </div>
  </div>
</template>
