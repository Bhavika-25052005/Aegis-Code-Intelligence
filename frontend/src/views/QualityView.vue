<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api/client'

const route = useRoute()
const router = useRouter()
const projectId = route.params.id as string
const storyId = route.params.storyId as string

// ── State ─────────────────────────────────────────────────────────────────
interface AcLegend { id: string; text: string; color: string }
interface TestEntry {
  test_id?: string
  test_name?: string
  file?: string
  type?: string
  test_type?: string
  scope?: string
  source_type?: string
  criteria?: string[]
  status?: string
  description?: string
  mapping_source?: string
}

const loading = ref(true)
const error = ref('')
const qualityData = ref<any>(null)

// Filters
const search = ref('')
const filterCriterion = ref('')
const filterType = ref('')
const filterStatus = ref('')
const currentPage = ref(1)
const pageSize = 50

// Expanded row
const expandedRow = ref<string | null>(null)

// README
const readmeLoading = ref(false)
const readmeMsg = ref('')

// Push
const pushLoading = ref(false)
const pushResult = ref<any>(null)
const pushError = ref('')
const showRepoModal = ref(false)
const pushRepoUrl = ref('')
const pushPat = ref('')

// Verify traceability
const verifyLoading = ref(false)
const verifyMsg = ref('')

// ── Load data ─────────────────────────────────────────────────────────────
async function fetchQuality() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, string | number> = {
      page: currentPage.value,
      page_size: pageSize,
    }
    if (search.value) params.search = search.value
    if (filterCriterion.value) params.criterion = filterCriterion.value
    if (filterType.value) params.type = filterType.value
    if (filterStatus.value) params.status = filterStatus.value

    const { data } = await api.get(
      `/projects/${projectId}/quality/${storyId}`,
      { params }
    )
    qualityData.value = data
    // Prefill repo URL from project config if present
    if (data.repo_configured && !pushRepoUrl.value) {
      // We don't display the PAT but we can show that it's configured
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to load quality data'
  } finally {
    loading.value = false
  }
}

// Debounced search
let searchTimer: ReturnType<typeof setTimeout> | null = null
watch([search, filterCriterion, filterType, filterStatus], () => {
  currentPage.value = 1
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(fetchQuality, 300)
})

watch(currentPage, fetchQuality)

onMounted(fetchQuality)

// ── Computed ──────────────────────────────────────────────────────────────
const acLegend = computed<AcLegend[]>(() => qualityData.value?.ac_legend ?? [])
const tests = computed<TestEntry[]>(() => qualityData.value?.tests ?? [])
const summary = computed(() => qualityData.value?.test_summary ?? {})
const totalFiltered = computed(() => qualityData.value?.total_filtered ?? 0)
const totalPages = computed(() => qualityData.value?.total_pages ?? 1)
const qualityGate = computed(() => qualityData.value?.quality_gate ?? 'unknown')
const readmeStatus = computed(() => qualityData.value?.readme_status ?? 'unknown')
const repoConfigured = computed(() => qualityData.value?.repo_configured ?? false)
const pushBlocked = computed(() => qualityData.value?.push_blocked_reason ?? null)

function acById(id: string): AcLegend | undefined {
  return acLegend.value.find(a => a.id === id)
}

function testName(t: TestEntry): string {
  return t.test_name || t.test_id || '—'
}
function testType(t: TestEntry): string {
  return (t.scope || t.test_type || t.type || 'unit')
}
function testStatus(t: TestEntry): string {
  return (t.status || 'generated').toLowerCase()
}
function testKey(t: TestEntry): string {
  return t.test_id || t.test_name || JSON.stringify(t).slice(0, 40)
}

function toggleRow(key: string) {
  expandedRow.value = expandedRow.value === key ? null : key
}

// ── Verify Traceability ──────────────────────────────────────────────────
async function verifyTraceability() {
  verifyLoading.value = true
  verifyMsg.value = ''
  try {
    const { data } = await api.post(
      `/projects/${projectId}/quality/${storyId}/verify-traceability`
    )
    verifyMsg.value = `Mapped ${data.total} tests`
    await fetchQuality()
  } catch (e: any) {
    verifyMsg.value = e?.response?.data?.detail || 'Verification failed'
  } finally {
    verifyLoading.value = false
  }
}

// ── Update README ────────────────────────────────────────────────────────
async function updateReadme() {
  readmeLoading.value = true
  readmeMsg.value = ''
  try {
    const { data } = await api.post(
      `/projects/${projectId}/quality/${storyId}/update-readme`
    )
    readmeMsg.value = data.readme_present ? 'README.md updated' : 'README update completed'
    await fetchQuality()
  } catch (e: any) {
    readmeMsg.value = e?.response?.data?.detail || 'README update failed'
  } finally {
    readmeLoading.value = false
  }
}

// ── Push to Repo ─────────────────────────────────────────────────────────
async function handlePush() {
  if (pushBlocked.value) return
  if (!repoConfigured.value) {
    showRepoModal.value = true
    return
  }
  await doPush()
}

async function saveAndPush() {
  if (!pushRepoUrl.value.trim()) return
  showRepoModal.value = false
  await doPush(pushRepoUrl.value.trim(), pushPat.value)
  pushPat.value = '' // never retain PAT in memory
}

async function doPush(repoUrl?: string, pat?: string) {
  pushLoading.value = true
  pushError.value = ''
  pushResult.value = null
  try {
    const body: Record<string, string> = {}
    if (repoUrl) body.repo_url = repoUrl
    if (pat) body.pat = pat
    const { data } = await api.post(
      `/projects/${projectId}/quality/${storyId}/push`,
      body
    )
    pushResult.value = data
    await fetchQuality()
  } catch (e: any) {
    pushError.value = e?.response?.data?.detail || 'Push failed'
  } finally {
    pushLoading.value = false
  }
}

// ── PDF download ─────────────────────────────────────────────────────────
function downloadPdf() {
  const params = new URLSearchParams()
  if (search.value) params.set('search', search.value)
  if (filterCriterion.value) params.set('criterion', filterCriterion.value)
  if (filterType.value) params.set('type', filterType.value)
  if (filterStatus.value) params.set('status', filterStatus.value)
  const query = params.toString() ? `?${params.toString()}` : ''
  window.open(
    `/api/projects/${projectId}/quality/${storyId}/report.pdf${query}`,
    '_blank'
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────
function gateClass(gate: string) {
  if (gate === 'passed') return 'text-green-600 bg-green-50 dark:bg-green-900/30'
  if (gate === 'needs_human_review' || gate === 'failed') return 'text-red-600 bg-red-50 dark:bg-red-900/30'
  if (gate === 'running' || gate === 'repairing') return 'text-blue-600 bg-blue-50'
  return 'text-gray-600 bg-gray-100 dark:bg-gray-700'
}
function statusClass(s: string) {
  if (s === 'passed') return 'text-green-600 font-semibold'
  if (s === 'failed' || s === 'needs_human_review') return 'text-red-600 font-semibold'
  return 'text-gray-400'
}
function clearFilters() {
  search.value = ''
  filterCriterion.value = ''
  filterType.value = ''
  filterStatus.value = ''
  currentPage.value = 1
}
</script>

<template>
  <div class="space-y-6 pb-12">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-800 dark:text-white">Quality &amp; Delivery</h2>
        <p v-if="qualityData" class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
          {{ qualityData.story?.title }}
        </p>
      </div>
      <button @click="router.back()" class="text-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 flex items-center gap-1">
        <i class="pi pi-arrow-left text-xs"></i> Back
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-16">
      <i class="pi pi-spin pi-spinner text-3xl text-blue-500"></i>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-xl p-5 text-red-700 dark:text-red-300">
      {{ error }}
    </div>

    <template v-else-if="qualityData">

      <!-- ── Quality Gate Banner ── -->
      <div class="flex items-center gap-3 px-5 py-4 rounded-xl border" :class="gateClass(qualityGate)">
        <i :class="qualityGate === 'passed' ? 'pi pi-check-circle' : 'pi pi-exclamation-circle'" class="text-lg"></i>
        <span class="font-semibold">Quality Gate: {{ qualityGate.replace(/_/g, ' ').toUpperCase() }}</span>
      </div>

      <!-- ── Test Summary ── -->
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 class="font-semibold text-gray-800 dark:text-white mb-4">Test Summary</h3>
        <div class="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <div v-for="(label, key) in { unit: 'Unit', integration: 'Integration', system: 'System', regression: 'Regression', custom: 'Custom', passed: 'Passed', failed: 'Failed' }"
            :key="key"
            class="text-center p-3 rounded-lg border"
            :class="{
              'border-green-200 bg-green-50 dark:bg-green-900/20': key === 'passed',
              'border-red-200 bg-red-50 dark:bg-red-900/20': key === 'failed',
              'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50': !['passed','failed'].includes(key),
            }"
          >
            <div class="text-2xl font-bold" :class="{
              'text-green-600': key === 'passed',
              'text-red-600': key === 'failed' && summary[key] > 0,
              'text-gray-800 dark:text-white': !['passed','failed'].includes(key),
            }">
              {{ summary[key] ?? 0 }}
            </div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ label }}</div>
          </div>
          <div class="text-center p-3 rounded-lg border border-blue-200 bg-blue-50 dark:bg-blue-900/20">
            <div class="text-2xl font-bold text-blue-600">{{ summary.total ?? 0 }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">Total</div>
          </div>
        </div>
      </div>

      <!-- ── Test Traceability Explorer ── -->
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <div class="flex items-center justify-between mb-4">
          <h3 class="font-semibold text-gray-800 dark:text-white">Test Traceability</h3>
          <div class="flex items-center gap-2">
            <button @click="verifyTraceability" :disabled="verifyLoading"
              class="text-xs px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 flex items-center gap-1">
              <i :class="verifyLoading ? 'pi pi-spin pi-spinner' : 'pi pi-link'" class="text-xs"></i>
              {{ verifyLoading ? 'Verifying...' : 'Verify Mappings' }}
            </button>
            <span v-if="verifyMsg" class="text-xs text-green-600 dark:text-green-400">{{ verifyMsg }}</span>
          </div>
        </div>

        <!-- AC Legend -->
        <div v-if="acLegend.length > 0" class="mb-4 flex flex-wrap gap-2">
          <span v-for="ac in acLegend" :key="ac.id"
            class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium text-white"
            :style="{ backgroundColor: ac.color }"
            :title="ac.text"
          >
            {{ ac.id }}
            <span class="hidden sm:inline text-white/80 font-normal max-w-[120px] truncate">{{ ac.text }}</span>
          </span>
        </div>

        <!-- Filters -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <input v-model="search" type="text" placeholder="Search test name or file..."
            class="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500" />

          <select v-model="filterCriterion"
            class="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="">Acceptance Criterion: All</option>
            <option v-for="ac in acLegend" :key="ac.id" :value="ac.id">{{ ac.id }}: {{ ac.text.slice(0, 40) }}</option>
          </select>

          <select v-model="filterType"
            class="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="">Type: All</option>
            <option value="unit">Unit</option>
            <option value="integration">Integration</option>
            <option value="system">System</option>
            <option value="regression">Regression</option>
            <option value="custom">Custom</option>
          </select>

          <select v-model="filterStatus"
            class="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="">Status: All</option>
            <option value="passed">Passed</option>
            <option value="failed">Failed</option>
            <option value="needs_review">Needs Review</option>
          </select>
        </div>

        <!-- Active filters summary + clear -->
        <div v-if="search || filterCriterion || filterType || filterStatus"
          class="flex items-center gap-2 mb-3 text-xs text-gray-500 dark:text-gray-400">
          <span>Active filters:</span>
          <span v-if="filterCriterion" class="px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">{{ filterCriterion }}</span>
          <span v-if="filterType" class="px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300">{{ filterType }}</span>
          <span v-if="filterStatus" class="px-1.5 py-0.5 rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">{{ filterStatus }}</span>
          <span v-if="search" class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700">"{{ search }}"</span>
          <button @click="clearFilters" class="ml-1 text-red-500 hover:text-red-700">
            <i class="pi pi-times-circle text-xs"></i> Clear
          </button>
        </div>

        <!-- Test Table -->
        <div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <table class="w-full text-sm">
            <thead class="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <th class="text-left px-4 py-2.5 font-medium text-gray-600 dark:text-gray-300 w-1/2">Test Name</th>
                <th class="text-left px-4 py-2.5 font-medium text-gray-600 dark:text-gray-300 w-24">Type</th>
                <th class="text-left px-4 py-2.5 font-medium text-gray-600 dark:text-gray-300">Criteria</th>
                <th class="text-left px-4 py-2.5 font-medium text-gray-600 dark:text-gray-300 w-24">Result</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="t in tests" :key="testKey(t)">
                <tr
                  class="border-t border-gray-100 dark:border-gray-700 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                  @click="toggleRow(testKey(t))"
                >
                  <td class="px-4 py-2.5 text-gray-800 dark:text-gray-200 font-mono text-xs max-w-0">
                    <div class="truncate" :title="testName(t)">
                      <i class="pi pi-chevron-right text-xs text-gray-400 mr-1 transition-transform"
                        :class="{ 'rotate-90': expandedRow === testKey(t) }"></i>
                      {{ testName(t) }}
                    </div>
                  </td>
                  <td class="px-4 py-2.5 text-gray-500 dark:text-gray-400 capitalize text-xs">{{ testType(t) }}</td>
                  <td class="px-4 py-2.5">
                    <span v-if="t.criteria && t.criteria.length" class="flex flex-wrap gap-1">
                      <span
                        v-for="cid in t.criteria" :key="cid"
                        class="inline-block px-1.5 py-0.5 rounded text-xs font-bold text-white"
                        :style="{ backgroundColor: acById(cid)?.color || '#6b7280' }"
                        :title="acById(cid)?.text"
                      >{{ cid }}</span>
                    </span>
                    <span v-else class="text-gray-300 dark:text-gray-600 text-xs">—</span>
                  </td>
                  <td class="px-4 py-2.5 text-xs" :class="statusClass(testStatus(t))">
                    {{ testStatus(t).toUpperCase() }}
                  </td>
                </tr>
                <!-- Expanded row -->
                <tr v-if="expandedRow === testKey(t)" class="bg-gray-50 dark:bg-gray-900/30 border-t border-gray-100 dark:border-gray-700">
                  <td colspan="4" class="px-6 py-3 text-xs text-gray-600 dark:text-gray-400 space-y-1">
                    <div v-if="t.file"><span class="font-medium">File:</span> <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded">{{ t.file }}</code></div>
                    <div v-if="t.source_type"><span class="font-medium">Source:</span> {{ t.source_type }}</div>
                    <div v-if="t.description"><span class="font-medium">Description:</span> {{ t.description }}</div>
                    <div v-if="t.mapping_source"><span class="font-medium">Mapping:</span> {{ t.mapping_source }}</div>
                    <div v-if="t.criteria && t.criteria.length">
                      <span class="font-medium">Mapped criteria:</span>
                      <span v-for="cid in t.criteria" :key="cid" class="ml-1">
                        <span class="font-mono" :style="{ color: acById(cid)?.color || '#6b7280' }">{{ cid }}</span>
                        <span v-if="acById(cid)" class="text-gray-500"> — {{ acById(cid)?.text }}</span>
                      </span>
                    </div>
                  </td>
                </tr>
              </template>
              <tr v-if="tests.length === 0">
                <td colspan="4" class="px-4 py-8 text-center text-gray-400 text-sm">
                  {{ totalFiltered === 0 && !search && !filterCriterion && !filterType && !filterStatus
                    ? 'No tests recorded yet. Complete execution to generate tests.'
                    : 'No tests match the current filters.' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div class="mt-3 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
          <span>Showing {{ tests.length }} of {{ totalFiltered }} tests</span>
          <div v-if="totalPages > 1" class="flex items-center gap-2">
            <button @click="currentPage--" :disabled="currentPage === 1"
              class="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-700">
              <i class="pi pi-chevron-left"></i>
            </button>
            <span>Page {{ currentPage }} / {{ totalPages }}</span>
            <button @click="currentPage++" :disabled="currentPage >= totalPages"
              class="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-700">
              <i class="pi pi-chevron-right"></i>
            </button>
          </div>
        </div>

        <!-- Download PDF -->
        <div class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <button @click="downloadPdf"
            class="flex items-center gap-2 px-4 py-2 bg-gray-800 dark:bg-gray-600 text-white rounded-lg hover:bg-gray-700 text-sm">
            <i class="pi pi-download"></i>
            Download Filtered PDF
            <span v-if="search || filterCriterion || filterType || filterStatus" class="text-xs opacity-70">(filtered)</span>
          </button>
        </div>
      </div>

      <!-- ── Documentation ── -->
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 class="font-semibold text-gray-800 dark:text-white mb-3">Documentation</h3>
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2 text-sm">
            <i :class="readmeStatus === 'present' ? 'pi pi-file text-green-500' : 'pi pi-file text-gray-400'"></i>
            <span class="text-gray-600 dark:text-gray-300">README.md</span>
            <span class="text-xs px-2 py-0.5 rounded-full"
              :class="readmeStatus === 'present' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-gray-100 text-gray-500'">
              {{ readmeStatus === 'present' ? 'Present' : 'Missing' }}
            </span>
          </div>
          <button @click="updateReadme" :disabled="readmeLoading"
            class="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50">
            <i :class="readmeLoading ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'" class="text-xs"></i>
            {{ readmeStatus === 'present' ? 'Update README' : 'Generate README' }}
          </button>
          <span v-if="readmeMsg" class="text-xs" :class="readmeMsg.includes('failed') ? 'text-red-500' : 'text-green-600'">
            {{ readmeMsg }}
          </span>
        </div>
      </div>

      <!-- ── Delivery ── -->
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 class="font-semibold text-gray-800 dark:text-white mb-3">Delivery</h3>

        <!-- Push blocked reason -->
        <div v-if="pushBlocked" class="mb-3 flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2">
          <i class="pi pi-lock"></i>
          {{ pushBlocked }}
        </div>

        <!-- Push result -->
        <div v-if="pushResult" class="mb-3 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg text-sm">
          <p class="text-green-700 dark:text-green-300 font-medium">Pushed successfully</p>
          <p class="text-green-600 dark:text-green-400 mt-1">Branch: <code class="bg-green-100 dark:bg-green-900/40 px-1 rounded">{{ pushResult.branch }}</code></p>
          <p v-if="pushResult.pr_url" class="text-green-600 dark:text-green-400 mt-0.5">
            PR: <a :href="pushResult.pr_url" target="_blank" class="underline hover:no-underline">{{ pushResult.pr_url }}</a>
          </p>
        </div>

        <!-- Push error -->
        <div v-if="pushError" class="mb-3 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
          {{ pushError }}
        </div>

        <div class="flex items-center gap-3">
          <button
            @click="handlePush"
            :disabled="!!pushBlocked || pushLoading"
            class="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
          >
            <i :class="pushLoading ? 'pi pi-spin pi-spinner' : 'pi pi-cloud-upload'"></i>
            {{ pushLoading ? 'Pushing...' : 'Push to Repo' }}
          </button>
          <span v-if="repoConfigured" class="text-xs text-gray-500 dark:text-gray-400">
            <i class="pi pi-check-circle text-green-500 mr-1"></i> Repository configured
          </span>
          <span v-else class="text-xs text-gray-400">Repository not configured — will ask on push</span>
        </div>
      </div>

    </template>

    <!-- ── Repository Config Modal ── -->
    <Teleport to="body">
      <div v-if="showRepoModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" @click.self="showRepoModal = false">
        <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-6 w-full max-w-md mx-4">
          <h3 class="font-semibold text-gray-800 dark:text-white mb-4">Repository Configuration</h3>

          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Repository URL</label>
              <input v-model="pushRepoUrl" type="url" placeholder="https://github.com/owner/repository"
                class="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Personal Access Token</label>
              <input v-model="pushPat" type="password" placeholder="ghp_••••••••••••••••••••••••••••••"
                class="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500" />
              <p class="text-xs text-gray-400 mt-1">The token is stored encrypted and never displayed again.</p>
            </div>
          </div>

          <div class="flex gap-3 justify-end mt-5">
            <button @click="showRepoModal = false"
              class="px-4 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
              Cancel
            </button>
            <button @click="saveAndPush" :disabled="!pushRepoUrl.trim() || !pushPat.trim()"
              class="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
              Save &amp; Push
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
