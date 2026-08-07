<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useExecutionStore } from '../stores/execution'
import { useBacklogStore } from '../stores/backlog'
import { useWebSocket } from '../composables/useWebSocket'
import TestReport from '../components/execution/TestReport.vue'
import api from '../api/client'

const route = useRoute()
const executionStore = useExecutionStore()
const backlogStore = useBacklogStore()
const projectId = route.params.id as string

// Optional query params set by ImplementationPlanView
const storyIdFilter = route.query.story_id as string | null || null
const skipTests = route.query.skip_tests === '1'

const { connected, messages, connect } = useWebSocket(projectId)
const taskStatuses = ref<Record<string, { status: string; title: string }>>({})
const testReportRef = ref<InstanceType<typeof TestReport> | null>(null)

onMounted(async () => {
  await backlogStore.fetchBacklog(projectId)
  await executionStore.fetchStatus(projectId)
  connect()
  executionStore.addLog(`[INFO] Page loaded. Status: ${executionStore.status?.status || 'none'}. Click Start to begin.`)
})

watch(messages, (msgs) => {
  const latest = msgs[msgs.length - 1]
  if (!latest) return

  if (latest.type === 'task_status_change') {
    const payload = latest.payload as { task_id: string; status: string; title?: string; completed_tasks?: number; failed_tasks?: number; total_tasks?: number }
    taskStatuses.value[payload.task_id] = {
      status: payload.status,
      title: payload.title || '',
    }
    if (executionStore.status) {
      if (payload.completed_tasks !== undefined) executionStore.status.completed_tasks = payload.completed_tasks
      if (payload.failed_tasks !== undefined) executionStore.status.failed_tasks = payload.failed_tasks
      if (payload.total_tasks !== undefined) executionStore.status.total_tasks = payload.total_tasks
    }
    executionStore.addLog(`[${payload.status.toUpperCase()}] ${payload.title || payload.task_id}`)
  } else if (latest.type === 'claude_output') {
    const payload = latest.payload as { message: string }
    executionStore.addLog(`[CLAUDE] ${payload.message}`)
  } else if (latest.type === 'test_started') {
    const payload = latest.payload as { task_id: string; test_type: string }
    executionStore.addLog(`[TEST] Running ${payload.test_type} tests...`)
  } else if (latest.type === 'test_completed') {
    const payload = latest.payload as { task_id: string; test_type: string; passed: boolean; total: number; failed: number; coverage: number; fix_attempt?: number }
    const icon = payload.passed ? 'PASS' : 'FAIL'
    const fixNote = payload.fix_attempt ? ` (fix #${payload.fix_attempt})` : ''
    executionStore.addLog(`[${icon}] ${payload.test_type}: ${payload.total - payload.failed}/${payload.total} passed, ${payload.coverage.toFixed(0)}% coverage${fixNote}`)
    testReportRef.value?.fetchTestRuns()
    testReportRef.value?.checkActiveTest()
  } else if (latest.type === 'fix_attempt') {
    const payload = latest.payload as { task_id: string; attempt: number; reason: string }
    executionStore.addLog(`[FIX] Attempt ${payload.attempt}: ${payload.reason}`)
  } else if (latest.type === 'pr_created') {
    const payload = latest.payload as { pr_url: string; title: string }
    executionStore.addLog(`[PR] Created: ${payload.title} - ${payload.pr_url}`)
  } else if (latest.type === 'execution_complete') {
    executionStore.addLog('[DONE] Execution completed')
    if (executionStore.status) executionStore.status.status = 'completed'
    testReportRef.value?.fetchTestRuns()
  } else if (latest.type === 'error') {
    const payload = latest.payload as { message: string }
    executionStore.addLog(`[ERROR] ${payload.message}`)
  }
}, { deep: true })

async function handleStart() {
  executionStore.clearLogs()
  await executionStore.startExecution(projectId, {
    skip_tests: skipTests,
    story_id: storyIdFilter,
  })
}

async function handlePause() {
  await executionStore.pauseExecution(projectId)
}

async function handleResume() {
  await executionStore.resumeExecution(projectId)
}

async function handleReset() {
  try {
    await api.post(`/projects/${projectId}/execute/reset`)
    executionStore.status = null
    executionStore.clearLogs()
    taskStatuses.value = {}
    executionStore.addLog('[INFO] All tasks reset to pending. Ready to re-run.')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    executionStore.addLog(`[ERROR] Reset failed: ${err.response?.data?.detail || 'Unknown error'}`)
  }
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
    <!-- Mode banner when launched from Implementation Plan -->
    <div
      v-if="storyIdFilter || skipTests"
      class="flex items-center gap-3 flex-wrap px-4 py-3 rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-800"
    >
      <i class="pi pi-info-circle"></i>
      <span v-if="storyIdFilter">Running <strong>single user story</strong> only (3 tasks, not all project tasks).</span>
      <span v-if="skipTests">Test runner is <strong>disabled</strong> — code will be generated without running tests.</span>
    </div>

    <div class="flex items-center justify-between">
      <h2 class="text-2xl font-bold text-gray-800 dark:text-white">Execution</h2>
      <div class="flex items-center gap-3">
        <span class="flex items-center gap-1 text-sm" :class="connected ? 'text-green-500' : 'text-red-500'">
          <i class="pi pi-circle-fill text-xs"></i>
          {{ connected ? 'Connected' : 'Disconnected' }}
        </span>
        <button
          v-if="executionStore.status && (executionStore.status.status === 'completed' || executionStore.status.status === 'failed')"
          @click="handleReset"
          class="px-4 py-2 border border-orange-500 text-orange-500 rounded-lg hover:bg-orange-50 dark:hover:bg-orange-900/20 flex items-center gap-2"
        >
          <i class="pi pi-refresh"></i> Reset
        </button>
        <button
          v-if="!executionStore.status || executionStore.status.status === 'completed' || executionStore.status.status === 'failed' || executionStore.status.status === 'cancelled'"
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

    <!-- Test Results -->
    <TestReport ref="testReportRef" :project-id="projectId" />

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
