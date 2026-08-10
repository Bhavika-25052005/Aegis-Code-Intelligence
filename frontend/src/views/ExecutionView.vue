<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useExecutionStore } from '../stores/execution'
import { useBacklogStore } from '../stores/backlog'
import { useWebSocket } from '../composables/useWebSocket'
import TestReport from '../components/execution/TestReport.vue'
import api from '../api/client'

const route = useRoute()
const router = useRouter()
const executionStore = useExecutionStore()
const backlogStore = useBacklogStore()
const projectId = route.params.id as string

// Optional query params set by ImplementationPlanView
const storyIdFilter = route.query.story_id as string | null || null
const skipTests = route.query.skip_tests === '1'

const { connected, messages, connect } = useWebSocket(projectId)
const taskStatuses = ref<Record<string, { status: string; title: string }>>({})
const testReportRef = ref<InstanceType<typeof TestReport> | null>(null)

// Day 3 — Custom Test
const customObjective = ref('')
const runningCustomTest = ref(false)
interface CustomTestResult {
  test_id: string
  detected_type: string
  file: string
  status: string
  repair_attempts: number
  output: string
}
const customResult = ref<CustomTestResult | null>(null)

onMounted(async () => {
  await backlogStore.fetchBacklog(projectId)
  await executionStore.fetchStatus(projectId)
  connect()

  // If execution is already running/paused, seed task statuses from backlog
  // so the Task Progress panel is not empty when the page loads mid-run
  const runStatus = executionStore.status?.status
  if (runStatus === 'running' || runStatus === 'paused') {
    const features = backlogStore.backlog?.features ?? []
    for (const feature of features) {
      for (const story of feature.user_stories) {
        // Only show tasks for the selected story if a filter is active
        if (storyIdFilter && story.id !== storyIdFilter) continue
        for (const task of story.tasks) {
          taskStatuses.value[task.id] = { status: task.status, title: task.title }
        }
      }
    }
    executionStore.addLog(`[INFO] Reconnected to running execution. Status: ${runStatus}.`)
  } else {
    executionStore.addLog(`[INFO] Page loaded. Status: ${runStatus || 'none'}. Click Start to begin.`)
  }
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
  } else if (latest.type === 'test_generation_started') {
    const payload = latest.payload as { task_id?: string; story_id?: string; test_type: string }
    executionStore.addLog(`[TEST GEN] Generating ${payload.test_type} tests...`)
  } else if (latest.type === 'test_run_started') {
    const payload = latest.payload as { task_id: string; files: string[] }
    executionStore.addLog(`[TEST RUN] Running: ${payload.files?.join(', ') || 'tests'}`)
  } else if (latest.type === 'test_result') {
    const payload = latest.payload as { task_id: string; test_type: string; passed: boolean; total: number; failed: number }
    executionStore.addLog(`[TEST RESULT] ${payload.test_type}: ${payload.passed ? 'PASS' : 'FAIL'} (${payload.total - payload.failed}/${payload.total})`)
  } else if (latest.type === 'test_completed') {
    const payload = latest.payload as { task_id: string; test_type: string; passed: boolean; total: number; failed: number; coverage: number; fix_attempt?: number }
    const icon = payload.passed ? '✓ PASS' : '✗ FAIL'
    const fixNote = payload.fix_attempt ? ` (after fix #${payload.fix_attempt})` : ''
    const passed = (payload.total ?? 0) - (payload.failed ?? 0)
    const covNote = payload.coverage > 0 ? `, ${payload.coverage.toFixed(0)}% coverage` : ''
    const typeLabel = payload.test_type === 'quality' ? 'Quality Tests' : `${payload.test_type} tests`
    executionStore.addLog(`[${icon}] ${typeLabel}: ${passed}/${payload.total ?? 0} passed${covNote}${fixNote}`)
    testReportRef.value?.fetchTestRuns()
    testReportRef.value?.checkActiveTest()
  } else if (latest.type === 'fix_attempt' || latest.type === 'repair_started') {
    const payload = latest.payload as { task_id?: string; story_id?: string; attempt: number; reason?: string }
    executionStore.addLog(`[REPAIR] Attempt ${payload.attempt}/3${payload.reason ? ': ' + payload.reason : ''}`)
  } else if (latest.type === 'repair_result') {
    const payload = latest.payload as { attempt: number; passed: boolean }
    executionStore.addLog(`[REPAIR ${payload.passed ? 'PASS' : 'FAIL'}] Attempt ${payload.attempt} complete`)
  } else if (latest.type === 'story_quality_gate') {
    const payload = latest.payload as { story_id: string; status: string; total?: number; failed?: number }
    executionStore.addLog(`[QUALITY GATE] ${payload.status.toUpperCase()}${payload.total !== undefined ? ` — ${(payload.total ?? 0) - (payload.failed ?? 0)}/${payload.total} passed` : ''}`)
  } else if (latest.type === 'needs_human_review') {
    const payload = latest.payload as { story_id?: string; task_id?: string; reason: string }
    executionStore.addLog(`[NEEDS REVIEW] ${payload.reason}`)
  } else if (latest.type === 'pr_created') {
    const payload = latest.payload as { pr_url: string; title: string }
    executionStore.addLog(`[PR] Created: ${payload.title} - ${payload.pr_url}`)
  } else if (latest.type === 'execution_status_change') {
    const payload = latest.payload as { status: string }
    if (executionStore.status) executionStore.status.status = payload.status
    executionStore.addLog(`[INFO] Execution ${payload.status.toUpperCase()}`)
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

async function runCustomTest() {
  if (!storyIdFilter || !customObjective.value.trim()) return
  runningCustomTest.value = true
  customResult.value = null
  try {
    const resp = await api.post(
      `/projects/${projectId}/tests/${storyIdFilter}/custom-test`,
      { objective: customObjective.value.trim() }
    )
    customResult.value = resp.data
    executionStore.addLog(`[CUSTOM TEST] ${resp.data.status.toUpperCase()} — ${resp.data.file}`)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    executionStore.addLog(`[CUSTOM TEST ERROR] ${err.response?.data?.detail || 'Unknown error'}`)
  } finally {
    runningCustomTest.value = false
  }
}

// All tasks in the selected story, sourced directly from the backlog store.
// This means the list is always complete — even tasks that completed before
// the WebSocket connected are shown.
const allStoryTasks = computed(() => {
  const features = backlogStore.backlog?.features ?? []
  const tasks: { id: string; title: string }[] = []
  for (const feature of features) {
    for (const story of feature.user_stories) {
      if (storyIdFilter && story.id !== storyIdFilter) continue
      for (const task of story.tasks) {
        tasks.push({ id: task.id, title: task.title })
      }
    }
  }
  return tasks
})

// Returns the live status for a task: WS updates take precedence over backlog.
function liveStatus(taskId: string): string {
  if (taskStatuses.value[taskId]) return taskStatuses.value[taskId].status
  // Fall back to backlog status
  const features = backlogStore.backlog?.features ?? []
  for (const feature of features) {
    for (const story of feature.user_stories) {
      for (const task of story.tasks) {
        if (task.id === taskId) return task.status
      }
    }
  }
  return 'pending'
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
      <span v-if="storyIdFilter">Running <strong>all tasks in selected user story</strong>.</span>
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
        <!-- Day 4: Continue to Quality when story execution is complete and a story is selected -->
        <button
          v-if="storyIdFilter && executionStore.status?.status === 'completed'"
          @click="router.push(`/projects/${projectId}/quality/${storyIdFilter}`)"
          class="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center gap-2"
        >
          <i class="pi pi-chart-bar"></i> Quality &amp; Delivery
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

    <!-- Task Status List — shows ALL story tasks, seeded from backlog on load -->
    <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
      <h3 class="font-semibold text-gray-800 dark:text-white mb-3">Task Progress</h3>

      <!-- seed from backlog so we always show every task even before WS events -->
      <template v-if="allStoryTasks.length > 0">
        <div class="space-y-2 max-h-72 overflow-y-auto">
          <div
            v-for="task in allStoryTasks"
            :key="task.id"
            class="flex items-center gap-3 py-2 px-3 rounded-lg"
            :class="{
              'bg-green-50 dark:bg-green-900/20': liveStatus(task.id) === 'completed',
              'bg-blue-50 dark:bg-blue-900/20': liveStatus(task.id) === 'in_progress',
              'bg-red-50 dark:bg-red-900/20': liveStatus(task.id) === 'failed' || liveStatus(task.id) === 'blocked',
              'bg-orange-50 dark:bg-orange-900/20': liveStatus(task.id) === 'retry',
              'bg-gray-50 dark:bg-gray-700/50': !['completed','in_progress','failed','blocked','retry'].includes(liveStatus(task.id)),
            }"
          >
            <i :class="getStatusIcon(liveStatus(task.id))"></i>
            <span class="text-sm text-gray-700 dark:text-gray-200 flex-1">{{ task.title }}</span>
            <span class="text-xs px-2 py-0.5 rounded-full font-medium" :class="{
              'bg-green-100 text-green-700 dark:bg-green-800 dark:text-green-200': liveStatus(task.id) === 'completed',
              'bg-blue-100 text-blue-700 dark:bg-blue-800 dark:text-blue-200': liveStatus(task.id) === 'in_progress',
              'bg-red-100 text-red-700 dark:bg-red-800 dark:text-red-200': liveStatus(task.id) === 'failed' || liveStatus(task.id) === 'blocked',
              'bg-orange-100 text-orange-700': liveStatus(task.id) === 'retry',
              'bg-gray-100 text-gray-500 dark:bg-gray-600 dark:text-gray-300': !['completed','in_progress','failed','blocked','retry'].includes(liveStatus(task.id)),
            }">
              {{ liveStatus(task.id) }}
            </span>
          </div>
        </div>
        <!-- counts row -->
        <div class="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700 flex gap-4 text-xs text-gray-500">
          <span><i class="pi pi-check-circle text-green-500 mr-1"></i>{{ allStoryTasks.filter(t => liveStatus(t.id) === 'completed').length }} done</span>
          <span><i class="pi pi-spin pi-spinner text-blue-500 mr-1"></i>{{ allStoryTasks.filter(t => liveStatus(t.id) === 'in_progress').length }} running</span>
          <span><i class="pi pi-circle text-gray-300 mr-1"></i>{{ allStoryTasks.filter(t => liveStatus(t.id) === 'pending').length }} waiting</span>
          <span v-if="allStoryTasks.filter(t => liveStatus(t.id) === 'failed').length > 0"><i class="pi pi-times-circle text-red-500 mr-1"></i>{{ allStoryTasks.filter(t => liveStatus(t.id) === 'failed').length }} failed</span>
        </div>
      </template>

      <p v-else class="text-sm text-gray-400 text-center py-4">
        No tasks found. Select a user story and click Start.
      </p>
    </div>

    <!-- Test Results -->
    <TestReport ref="testReportRef" :project-id="projectId" />

    <!-- Day 3 Custom Test Panel — shown only when a story is selected -->
    <section v-if="storyIdFilter" class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
      <h3 class="font-semibold text-gray-800 dark:text-white">Custom Test</h3>
      <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
        Describe what you want Aegis to verify in natural language.
      </p>
      <textarea
        v-model="customObjective"
        rows="4"
        class="w-full mt-3 rounded-lg border border-gray-300 dark:border-gray-600 p-3 text-sm bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder="Example: Test that a prescription cannot be saved when dosage is missing."
      />
      <button
        class="mt-3 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700 disabled:opacity-50"
        :disabled="runningCustomTest || !customObjective.trim()"
        @click="runCustomTest"
      >
        {{ runningCustomTest ? 'Generating &amp; Testing...' : 'Generate &amp; Run Test' }}
      </button>
      <div v-if="customResult" class="mt-4 text-sm space-y-1">
        <p><span class="font-medium">Type:</span> {{ customResult.detected_type }}</p>
        <p><span class="font-medium">File:</span> <code class="text-xs bg-gray-100 dark:bg-gray-700 px-1 rounded">{{ customResult.file }}</code></p>
        <p>
          <span class="font-medium">Status:</span>
          <span :class="{
            'text-green-600': customResult.status === 'passed',
            'text-red-600': customResult.status === 'failed',
            'text-orange-500': customResult.status === 'needs_human_review',
          }">{{ customResult.status }}</span>
        </p>
        <p><span class="font-medium">Repair attempts:</span> {{ customResult.repair_attempts }}</p>
        <details v-if="customResult.output" class="mt-2">
          <summary class="cursor-pointer text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">Output</summary>
          <pre class="mt-2 text-xs bg-gray-50 dark:bg-gray-900 p-3 rounded overflow-x-auto max-h-48">{{ customResult.output }}</pre>
        </details>
      </div>
    </section>

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
