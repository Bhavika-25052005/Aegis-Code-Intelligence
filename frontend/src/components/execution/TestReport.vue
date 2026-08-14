<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../../api/client'

const props = defineProps<{ projectId: string }>()

interface TestRunEntry {
  id: string
  task_id: string
  test_type: string
  status: string
  total_tests: number
  passed_tests: number
  failed_tests: number
  coverage_percentage: number
  duration_seconds: number
  error_summary: string
  fix_attempt: number
}

const testRuns = ref<TestRunEntry[]>([])
const loading = ref(false)

// Manual test trigger state
const testScope = ref<'regression' | 'pr'>('regression')
const branchName = ref('')
const selectedTestTypes = ref<string[]>(['unit', 'integration'])
const isRunning = ref(false)
const triggerError = ref('')

async function fetchTestRuns() {
  loading.value = true
  try {
    const { data } = await api.get(`/projects/${props.projectId}/tests/runs`, {
      params: { latest_only: true },
    })
    testRuns.value = data
  } finally {
    loading.value = false
  }
}

async function checkActiveTest() {
  try {
    const { data } = await api.get(`/projects/${props.projectId}/tests/active`)
    isRunning.value = data.active
  } catch {
    // ignore
  }
}

async function triggerTests() {
  triggerError.value = ''
  isRunning.value = true
  try {
    await api.post(`/projects/${props.projectId}/tests/trigger`, {
      scope: testScope.value,
      branch: testScope.value === 'pr' ? branchName.value || null : null,
      test_types: selectedTestTypes.value,
    })
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    triggerError.value = err.response?.data?.detail || 'Failed to trigger tests'
    isRunning.value = false
  }
}

function toggleTestType(type: string) {
  const idx = selectedTestTypes.value.indexOf(type)
  if (idx >= 0) {
    selectedTestTypes.value.splice(idx, 1)
  } else {
    selectedTestTypes.value.push(type)
  }
}

onMounted(() => {
  fetchTestRuns()
  checkActiveTest()
})

function getStatusColor(status: string) {
  return status === 'passed' ? 'text-green-600 bg-green-50' : 'text-red-600 bg-red-50'
}

function getTypeIcon(type: string) {
  switch (type) {
    case 'unit': return 'pi pi-check-square'
    case 'quality': return 'pi pi-shield'
    case 'integration': return 'pi pi-link'
    case 'regression': return 'pi pi-replay'
    case 'pr': return 'pi pi-code'
    case 'performance': return 'pi pi-bolt'
    default: return 'pi pi-list'
  }
}

defineExpose({ fetchTestRuns, checkActiveTest })
</script>

<template>
  <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
    <div class="flex items-center justify-between mb-4">
      <h3 class="font-semibold text-gray-800 dark:text-white flex items-center gap-2">
        <i class="pi pi-verified text-blue-500"></i> Test Results
      </h3>
      <button @click="fetchTestRuns" class="text-xs text-gray-400 hover:text-blue-500">
        <i class="pi pi-refresh"></i> Refresh
      </button>
    </div>

    <!-- Manual Test Trigger -->
    <div class="mb-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
      <h4 class="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3 flex items-center gap-2">
        <i class="pi pi-play-circle"></i> Run Tests Manually
      </h4>

      <!-- Scope selector -->
      <div class="flex items-center gap-4 mb-3">
        <label class="flex items-center gap-2 cursor-pointer">
          <input
            type="radio"
            value="regression"
            v-model="testScope"
            class="text-blue-600"
          />
          <span class="text-sm text-gray-700 dark:text-gray-200">Regression (Full Codebase)</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input
            type="radio"
            value="pr"
            v-model="testScope"
            class="text-blue-600"
          />
          <span class="text-sm text-gray-700 dark:text-gray-200">PR Branch</span>
        </label>
      </div>

      <!-- Branch input for PR scope -->
      <div v-if="testScope === 'pr'" class="mb-3">
        <input
          v-model="branchName"
          type="text"
          placeholder="Branch name (leave empty for current branch)"
          class="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200"
        />
      </div>

      <!-- Test types -->
      <div class="flex items-center gap-4 mb-3">
        <span class="text-xs text-gray-500">Test types:</span>
        <label class="flex items-center gap-1 cursor-pointer">
          <input
            type="checkbox"
            :checked="selectedTestTypes.includes('unit')"
            @change="toggleTestType('unit')"
            class="text-blue-600"
          />
          <span class="text-xs text-gray-600 dark:text-gray-300">Unit</span>
        </label>
        <label class="flex items-center gap-1 cursor-pointer">
          <input
            type="checkbox"
            :checked="selectedTestTypes.includes('integration')"
            @change="toggleTestType('integration')"
            class="text-blue-600"
          />
          <span class="text-xs text-gray-600 dark:text-gray-300">Integration</span>
        </label>
      </div>

      <!-- Trigger button -->
      <div class="flex items-center gap-3">
        <button
          @click="triggerTests"
          :disabled="isRunning || selectedTestTypes.length === 0"
          class="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <i :class="isRunning ? 'pi pi-spin pi-spinner' : 'pi pi-play'"></i>
          {{ isRunning ? 'Running...' : 'Run Tests' }}
        </button>
        <span v-if="isRunning" class="text-xs text-blue-500">
          Tests are running. Check logs below for progress.
        </span>
      </div>

      <!-- Error -->
      <div v-if="triggerError" class="mt-2 text-xs text-red-500">
        {{ triggerError }}
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="text-center py-4">
      <i class="pi pi-spin pi-spinner text-blue-500"></i>
    </div>

    <!-- Empty state -->
    <div v-else-if="testRuns.length === 0" class="text-center py-4 text-sm text-gray-400">
      No test runs yet. Use the panel above to trigger tests manually, or they will appear during execution.
    </div>

    <!-- Test runs list -->
    <div v-else class="space-y-2 max-h-64 overflow-y-auto">
      <div
        v-for="run in testRuns"
        :key="run.id"
        class="flex items-center gap-3 py-2 px-3 rounded-lg bg-gray-50 dark:bg-gray-700/50"
      >
        <i :class="getTypeIcon(run.test_type)" class="text-gray-400"></i>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-xs font-medium px-1.5 py-0.5 rounded" :class="getStatusColor(run.status)">
              {{ run.status }}
            </span>
            <span class="text-xs text-gray-500 uppercase">{{ run.test_type }}</span>
            <span v-if="run.fix_attempt > 0" class="text-xs text-orange-500">
              (fix #{{ run.fix_attempt }})
            </span>
            <span v-if="run.task_id.startsWith('manual')" class="text-xs text-purple-500 font-medium">
              MANUAL
            </span>
          </div>
          <div class="text-xs text-gray-400 mt-0.5">
            {{ run.passed_tests }}/{{ run.total_tests }} passed
            <span v-if="run.coverage_percentage > 0"> | {{ run.coverage_percentage.toFixed(0) }}% coverage</span>
            <span> | {{ run.duration_seconds.toFixed(1) }}s</span>
          </div>
        </div>
        <div v-if="run.error_summary" class="text-xs text-red-400 max-w-48 truncate">
          {{ run.error_summary }}
        </div>
      </div>
    </div>

    <!-- Summary -->
    <div v-if="testRuns.length > 0" class="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700 flex items-center gap-4 text-xs text-gray-500">
      <span>
        <i class="pi pi-check-circle text-green-500 mr-1"></i>
        {{ testRuns.filter(r => r.status === 'passed').length }} passed
      </span>
      <span>
        <i class="pi pi-times-circle text-red-500 mr-1"></i>
        {{ testRuns.filter(r => r.status === 'failed').length }} failed
      </span>
      <span v-if="testRuns.some(r => r.coverage_percentage > 0)">
        <i class="pi pi-chart-bar text-blue-500 mr-1"></i>
        Avg {{ (testRuns.filter(r => r.coverage_percentage > 0).reduce((a, r) => a + r.coverage_percentage, 0) / testRuns.filter(r => r.coverage_percentage > 0).length).toFixed(0) }}% coverage
      </span>
    </div>
  </div>
</template>
