<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api/client'

const route = useRoute()
const router = useRouter()
const projectId = route.params.id as string
const storyId = route.params.storyId as string

// ── Interfaces ────────────────────────────────────────────────────────────
interface AcLegend { id: string; text: string; color: string }
interface TestEntry {
  test_id?: string; test_name?: string; file?: string; type?: string
  test_type?: string; scope?: string; source_type?: string
  criteria?: string[]; status?: string; description?: string; mapping_source?: string
}
interface RunByType {
  type: string; total: number; passed: number; failed: number
  fix_attempts: number; error_summary: string
}
interface RunHistoryEntry {
  execution_run_id: string; status: string; started_at: string | null
  completed_at: string | null; total_tasks: number; completed_tasks: number
  failed_tasks: number; total_tests: number; passed_tests: number
  failed_tests: number; by_type: RunByType[]
}
interface CoverageFile { path: string; coverage: number }
interface CoverageData {
  status: string; tool: string | null; overall: number | null
  lines: number | null; statements: number | null; functions: number | null
  branches: number | null; files: CoverageFile[]; reason?: string
}
interface Finding {
  severity: string; category: string; file: string
  line_or_area: string; finding: string; recommendation: string
}
interface ReviewScores {
  maintainability: number; readability: number; error_handling: number
  architecture_fit: number; security: number; overall: number
}
interface ReviewDetails { personal_info: string[]; sensitive_info: string[]; bad_practices: string[] }
interface ReviewData {
  status: string; findings: Finding[]; scores: ReviewScores; summary: string; details?: ReviewDetails
}
interface ReadinessCheck { key: string; label: string; passed: boolean; blocking: boolean; message: string }
interface ReadinessData {
  status: string; passed_checks: number; total_checks: number
  blockers: { key: string; message: string }[]
  warnings: { key: string; message: string }[]
  checks: ReadinessCheck[]; is_stale: boolean
}
interface CodeQualityData {
  coverage: CoverageData; review: ReviewData
  release_readiness: ReadinessData; generated_at: string; workspace_fingerprint: string
}

// ── State ─────────────────────────────────────────────────────────────────
const loading = ref(true)
const error = ref('')
const qualityData = ref<any>(null)

// Traceability filters
const search = ref('')
const filterCriterion = ref('')
const filterType = ref('')
const filterStatus = ref('')
const currentPage = ref(1)
const pageSize = 10
const expandedRow = ref<string | null>(null)

// Run History
const runHistory = ref<RunHistoryEntry[]>([])
const runHistoryLoading = ref(false)
const expandedRun = ref<string | null>(null)

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

// Day 5 - Quality Analysis
const analyzeLoading = ref(false)
const analyzeMsg = ref('')
const analyzeError = ref('')
const showAllChecks = ref(false)

// Day 5 - Findings Explorer filters
const findingSearch = ref('')
const findingSeverity = ref('')
const findingCategory = ref('')
const findingFile = ref('')
const findingPage = ref(1)
const findingPageSize = 5

// Tab navigation
const activeTab = ref<'test_coverage' | 'code_coverage' | 'deployment'>('test_coverage')
const reviewTab = ref<'findings' | 'details'>('findings')

// ── Load data ─────────────────────────────────────────────────────────────
async function fetchQuality() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, string | number> = {
      page: currentPage.value, page_size: pageSize,
    }
    if (search.value) params.search = search.value
    if (filterCriterion.value) params.criterion = filterCriterion.value
    if (filterType.value) params.type = filterType.value
    if (filterStatus.value) params.status = filterStatus.value

    const { data } = await api.get(`/projects/${projectId}/quality/${storyId}`, { params })
    qualityData.value = data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to load quality data'
  } finally {
    loading.value = false
  }
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch([search, filterCriterion, filterType, filterStatus], () => {
  currentPage.value = 1
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(fetchQuality, 300)
})
watch(currentPage, fetchQuality)

async function fetchRunHistory() {
  runHistoryLoading.value = true
  try {
    const { data } = await api.get(`/projects/${projectId}/quality/${storyId}/run-history`)
    runHistory.value = data.runs ?? []
  } catch { /* non-critical */ } finally {
    runHistoryLoading.value = false
  }
}

onMounted(() => { fetchQuality(); fetchRunHistory() })

// ── Day 5: Refresh Quality Analysis ──────────────────────────────────────
async function refreshQualityAnalysis() {
  if (analyzeLoading.value) return
  analyzeLoading.value = true
  analyzeMsg.value = ''
  analyzeError.value = ''
  try {
    await api.post(`/projects/${projectId}/quality/${storyId}/analyze`)
    analyzeMsg.value = 'Analysis complete'
    await fetchQuality()
  } catch (e: any) {
    analyzeError.value = e?.response?.data?.detail || 'Analysis failed'
  } finally {
    analyzeLoading.value = false
  }
}

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
const qualityStale = computed<boolean>(() => qualityData.value?.quality_stale ?? false)

const codeQuality = computed<CodeQualityData | null>(() => {
  const cq = qualityData.value?.code_quality
  return cq && Object.keys(cq).length > 0 ? cq : null
})
const coverage = computed<CoverageData | null>(() => codeQuality.value?.coverage ?? null)
const review = computed<ReviewData | null>(() => codeQuality.value?.review ?? null)
const releaseReadiness = computed<ReadinessData | null>(() => {
  return qualityData.value?.release_readiness && Object.keys(qualityData.value.release_readiness).length > 0
    ? qualityData.value.release_readiness
    : null
})

// Filtered findings
const filteredFindings = computed<Finding[]>(() => {
  let findings = review.value?.findings ?? []
  if (findingSearch.value) {
    const s = findingSearch.value.toLowerCase()
    findings = findings.filter(f =>
      f.finding.toLowerCase().includes(s) ||
      f.file.toLowerCase().includes(s) ||
      f.recommendation.toLowerCase().includes(s)
    )
  }
  if (findingSeverity.value) findings = findings.filter(f => f.severity === findingSeverity.value)
  if (findingCategory.value) findings = findings.filter(f => f.category === findingCategory.value)
  if (findingFile.value) findings = findings.filter(f => f.file.toLowerCase().includes(findingFile.value.toLowerCase()))
  return findings
})

const findingCounts = computed(() => {
  const all = review.value?.findings ?? []
  return {
    critical: all.filter(f => f.severity === 'critical').length,
    high: all.filter(f => f.severity === 'high').length,
    medium: all.filter(f => f.severity === 'medium').length,
    low: all.filter(f => f.severity === 'low').length,
  }
})

const uniqueFiles = computed(() => {
  const files = [...new Set((review.value?.findings ?? []).map(f => f.file).filter(Boolean))]
  return files.sort()
})

const findingTotalPages = computed(() => Math.max(1, Math.ceil(filteredFindings.value.length / findingPageSize)))
const paginatedFindings = computed<Finding[]>(() => {
  const start = (findingPage.value - 1) * findingPageSize
  return filteredFindings.value.slice(start, start + findingPageSize)
})

watch(filteredFindings, () => { findingPage.value = 1 })

const reviewDetails = computed<ReviewDetails>(() => {
  return (review.value as any)?.details ?? { personal_info: [], sensitive_info: [], bad_practices: [] }
})

// ── Helpers ───────────────────────────────────────────────────────────────
function acById(id: string) { return acLegend.value.find(a => a.id === id) }
function testName(t: TestEntry) { return t.test_name || t.test_id || '-' }
function testType(t: TestEntry) { return (t.scope || t.test_type || t.type || 'unit') }
function testStatus(t: TestEntry) { return (t.status || 'generated').toLowerCase() }
function testKey(t: TestEntry) { return t.test_id || t.test_name || JSON.stringify(t).slice(0, 40) }
function toggleRow(key: string) { expandedRow.value = expandedRow.value === key ? null : key }
function toggleRun(id: string) { expandedRun.value = expandedRun.value === id ? null : id }

function formatDate(iso: string | null) {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
    + '  ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}
function typeLabel(t: string) {
  return ({ unit: 'Unit', integration: 'Integration', quality: 'Quality Gate', system: 'System', regression: 'Regression', custom: 'Custom' })[t] ?? t
}

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
  search.value = ''; filterCriterion.value = ''; filterType.value = ''; filterStatus.value = ''; currentPage.value = 1
}

function scoreColor(score: number) {
  if (score >= 80) return 'text-green-600'
  if (score >= 60) return 'text-yellow-600'
  return 'text-red-600'
}
function normalizeCheckLabel(label: string) {
  if (label === 'Critical Security Flaws') return 'No Critical Security Flaws'
  return label
}
function severityClass(sev: string) {
  if (sev === 'critical') return 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
  if (sev === 'high') return 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300'
  if (sev === 'medium') return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300'
  return 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
}
function coverageBar(pct: number | null) {
  if (pct === null) return 'bg-gray-300'
  if (pct >= 80) return 'bg-green-500'
  if (pct >= 60) return 'bg-yellow-500'
  return 'bg-red-500'
}
function coveragePct(pct: number | null) {
  if (pct === null) return '-'
  return pct.toFixed(1) + '%'
}
function categoryLabel(cat: string) {
  return ({ maintainability: 'Maintainability', readability: 'Readability', error_handling: 'Error Handling', architecture_fit: 'Architecture Fit', security: 'Security' })[cat] ?? cat
}

// ── Actions ───────────────────────────────────────────────────────────────
async function verifyTraceability() {
  verifyLoading.value = true; verifyMsg.value = ''
  try {
    const { data } = await api.post(`/projects/${projectId}/quality/${storyId}/verify-traceability`)
    verifyMsg.value = `Mapped ${data.total} tests`
    await fetchQuality()
  } catch (e: any) {
    verifyMsg.value = e?.response?.data?.detail || 'Verification failed'
  } finally { verifyLoading.value = false }
}

async function updateReadme() {
  readmeLoading.value = true; readmeMsg.value = ''
  try {
    const { data } = await api.post(`/projects/${projectId}/quality/${storyId}/update-readme`)
    readmeMsg.value = data.readme_present ? 'README.md updated' : 'README update completed'
    await fetchQuality()
  } catch (e: any) {
    readmeMsg.value = e?.response?.data?.detail || 'README update failed'
  } finally { readmeLoading.value = false }
}

async function handlePush() {
  if (pushBlocked.value) return
  if (!repoConfigured.value) { showRepoModal.value = true; return }
  await doPush()
}

async function saveAndPush() {
  if (!pushRepoUrl.value.trim()) return
  showRepoModal.value = false
  await doPush(pushRepoUrl.value.trim(), pushPat.value)
  pushPat.value = ''
}

async function doPush(repoUrl?: string, pat?: string) {
  pushLoading.value = true; pushError.value = ''; pushResult.value = null
  try {
    const body: Record<string, string> = {}
    if (repoUrl) body.repo_url = repoUrl
    if (pat) body.pat = pat
    const { data } = await api.post(`/projects/${projectId}/quality/${storyId}/push`, body)
    pushResult.value = data
    await fetchQuality()
  } catch (e: any) {
    pushError.value = e?.response?.data?.detail || 'Push failed'
  } finally { pushLoading.value = false }
}

function downloadPdf() {
  const params = new URLSearchParams()
  if (search.value) params.set('search', search.value)
  if (filterCriterion.value) params.set('criterion', filterCriterion.value)
  if (filterType.value) params.set('type', filterType.value)
  if (filterStatus.value) params.set('status', filterStatus.value)
  const query = params.toString() ? `?${params.toString()}` : ''
  window.open(`/api/projects/${projectId}/quality/${storyId}/report.pdf${query}`, '_blank')
}
</script>

<template>
  <div class="space-y-6 pb-12">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-800 dark:text-white">Quality &amp; Delivery</h2>
        <p v-if="qualityData" class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{{ qualityData.story?.title }}</p>
      </div>
      <button @click="router.back()" class="text-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 flex items-center gap-1">
        <i class="pi pi-arrow-left text-xs"></i> Back
      </button>
    </div>

    <div v-if="loading" class="flex justify-center py-16">
      <i class="pi pi-spin pi-spinner text-3xl text-blue-500"></i>
    </div>
    <div v-else-if="error" class="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-xl p-5 text-red-700 dark:text-red-300">
      {{ error }}
    </div>

    <template v-else-if="qualityData">

      <!-- ── Stale Warning ── -->
      <div v-if="qualityStale" class="flex items-center gap-3 px-5 py-3 rounded-xl border border-amber-300 bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300">
        <i class="pi pi-exclamation-triangle"></i>
        <div>
          <span class="font-semibold">Quality analysis is outdated</span>
          <span class="ml-2 text-sm">- workspace has changed since last analysis. Push is disabled until you refresh.</span>
        </div>
        <button @click="refreshQualityAnalysis" :disabled="analyzeLoading"
          class="ml-auto text-sm px-3 py-1.5 rounded-lg bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50 flex items-center gap-1 whitespace-nowrap">
          <i :class="analyzeLoading ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'" class="text-xs"></i>
          Refresh Now
        </button>
      </div>

      <!-- ── Quality Gate Banner ── -->
      <div class="flex items-center gap-3 px-5 py-4 rounded-xl border" :class="gateClass(qualityGate)">
        <i :class="qualityGate === 'passed' ? 'pi pi-check-circle' : 'pi pi-exclamation-circle'" class="text-lg"></i>
        <span class="font-semibold">Quality Gate: {{ qualityGate.replace(/_/g, ' ').toUpperCase() }}</span>
      </div>

      <!-- ── Tab Navigation ── -->
      <div class="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        <button @click="activeTab = 'test_coverage'"
          :class="activeTab === 'test_coverage' ? 'border-b-2 border-blue-500 text-blue-600 dark:text-blue-400 font-medium' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
          class="px-4 py-2.5 text-sm transition-colors">
          Test Coverage
        </button>
        <button @click="activeTab = 'code_coverage'"
          :class="activeTab === 'code_coverage' ? 'border-b-2 border-blue-500 text-blue-600 dark:text-blue-400 font-medium' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
          class="px-4 py-2.5 text-sm transition-colors">
          Code Coverage
        </button>
        <button @click="activeTab = 'deployment'"
          :class="activeTab === 'deployment' ? 'border-b-2 border-blue-500 text-blue-600 dark:text-blue-400 font-medium' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
          class="px-4 py-2.5 text-sm transition-colors">
          Deployment
        </button>
      </div>

      <!-- ══ TAB 1: TEST COVERAGE ══ -->
      <template v-if="activeTab === 'test_coverage'">

      <!-- ── Test Summary ── -->
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 class="font-semibold text-gray-800 dark:text-white mb-4">Test Summary</h3>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <div v-for="(label, key) in { unit: 'Unit', integration_system: 'Integration / System', regression: 'Regression', custom: 'Custom' }"
            :key="key" class="text-center p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50">
            <div class="text-2xl font-bold text-gray-800 dark:text-white">{{ summary[key] ?? 0 }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 leading-tight">{{ label }}</div>
          </div>
          <div class="text-center p-3 rounded-lg border border-blue-200 bg-blue-50 dark:bg-blue-900/20">
            <div class="text-2xl font-bold text-blue-600">{{ summary.total ?? 0 }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">Total</div>
          </div>
          <div class="text-center p-3 rounded-lg border border-green-200 bg-green-50 dark:bg-green-900/20">
            <div class="text-2xl font-bold text-green-600">{{ summary.passed ?? 0 }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">Passed</div>
          </div>
        </div>
      </div>

      <!-- ── Run History ── -->
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <div class="flex items-center justify-between mb-4">
          <h3 class="font-semibold text-gray-800 dark:text-white">Run History</h3>
          <span class="text-xs text-gray-400">{{ runHistory.length }} run{{ runHistory.length !== 1 ? 's' : '' }}</span>
        </div>
        <div v-if="runHistoryLoading" class="flex justify-center py-4">
          <i class="pi pi-spin pi-spinner text-blue-500"></i>
        </div>
        <div v-else-if="runHistory.length === 0" class="text-sm text-gray-400 text-center py-4">No execution runs recorded yet.</div>
        <div v-else class="space-y-2">
          <div v-for="run in runHistory" :key="run.execution_run_id" class="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
            <button class="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors" @click="toggleRun(run.execution_run_id)">
              <span class="w-2 h-2 rounded-full flex-shrink-0" :class="{ 'bg-green-500': run.status === 'completed' && run.failed_tests === 0, 'bg-red-500': run.failed_tests > 0, 'bg-yellow-400': run.status === 'paused', 'bg-gray-400': run.status === 'cancelled', 'bg-blue-500': run.status === 'running' }"></span>
              <span class="text-sm font-medium text-gray-700 dark:text-gray-200 w-44 flex-shrink-0">{{ formatDate(run.started_at) }}</span>
              <span class="text-sm flex-1">
                <span class="text-green-600 font-semibold">{{ run.passed_tests }} passed</span>
                <span v-if="run.failed_tests > 0" class="text-red-500 font-semibold ml-2">{{ run.failed_tests }} failed</span>
                <span class="text-gray-400 ml-2 text-xs">/ {{ run.total_tests }} total</span>
              </span>
              <span class="text-xs text-gray-400 hidden sm:block">{{ run.completed_tasks }}/{{ run.total_tasks }} tasks</span>
              <i class="pi pi-chevron-right text-xs text-gray-400 transition-transform flex-shrink-0" :class="{ 'rotate-90': expandedRun === run.execution_run_id }"></i>
            </button>
            <div v-if="expandedRun === run.execution_run_id" class="border-t border-gray-100 dark:border-gray-700 px-4 py-3 bg-gray-50 dark:bg-gray-900/30">
              <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                <div v-for="bt in run.by_type" :key="bt.type" class="rounded-lg border p-3 text-center"
                  :class="bt.failed > 0 ? 'border-red-200 bg-red-50 dark:bg-red-900/20' : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800'">
                  <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">{{ typeLabel(bt.type) }}</div>
                  <div class="font-bold text-sm" :class="bt.failed > 0 ? 'text-red-600' : 'text-green-600'">{{ bt.passed }}/{{ bt.total }}</div>
                  <div v-if="bt.fix_attempts > 0" class="text-xs text-orange-500 mt-0.5">{{ bt.fix_attempts }} repair{{ bt.fix_attempts > 1 ? 's' : '' }}</div>
                </div>
              </div>
              <div v-if="run.completed_at" class="mt-2 text-xs text-gray-400">Completed {{ formatDate(run.completed_at) }}</div>
            </div>
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

        <div v-if="acLegend.length > 0" class="mb-4 flex flex-wrap gap-2">
          <span v-for="ac in acLegend" :key="ac.id" class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium text-white" :style="{ backgroundColor: ac.color }" :title="ac.text">
            {{ ac.id }}
            <span class="hidden sm:inline text-white/80 font-normal max-w-[120px] truncate">{{ ac.text }}</span>
          </span>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <input v-model="search" type="text" placeholder="Search test name or file..."
            class="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <select v-model="filterCriterion" class="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="">Acceptance Criterion: All</option>
            <option v-for="ac in acLegend" :key="ac.id" :value="ac.id">{{ ac.id }}: {{ ac.text.slice(0, 40) }}</option>
          </select>
          <select v-model="filterType" class="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="">Type: All</option>
            <option value="unit">Unit</option>
            <option value="integration">Integration</option>
            <option value="system">System</option>
            <option value="regression">Regression</option>
            <option value="custom">Custom</option>
          </select>
          <select v-model="filterStatus" class="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="">Status: All</option>
            <option value="passed">Passed</option>
            <option value="failed">Failed</option>
            <option value="needs_review">Needs Review</option>
          </select>
        </div>

        <div v-if="search || filterCriterion || filterType || filterStatus" class="flex items-center gap-2 mb-3 text-xs text-gray-500 dark:text-gray-400">
          <span>Active filters:</span>
          <span v-if="filterCriterion" class="px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">{{ filterCriterion }}</span>
          <span v-if="filterType" class="px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300">{{ filterType }}</span>
          <span v-if="filterStatus" class="px-1.5 py-0.5 rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">{{ filterStatus }}</span>
          <span v-if="search" class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700">"{{ search }}"</span>
          <button @click="clearFilters" class="ml-1 text-red-500 hover:text-red-700"><i class="pi pi-times-circle text-xs"></i> Clear</button>
        </div>

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
                <tr class="border-t border-gray-100 dark:border-gray-700 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors" @click="toggleRow(testKey(t))">
                  <td class="px-4 py-2.5 text-gray-800 dark:text-gray-200 font-mono text-xs max-w-0">
                    <div class="truncate" :title="testName(t)">
                      <i class="pi pi-chevron-right text-xs text-gray-400 mr-1 transition-transform" :class="{ 'rotate-90': expandedRow === testKey(t) }"></i>
                      {{ testName(t) }}
                    </div>
                  </td>
                  <td class="px-4 py-2.5 text-gray-500 dark:text-gray-400 capitalize text-xs">{{ testType(t) }}</td>
                  <td class="px-4 py-2.5">
                    <span v-if="t.criteria && t.criteria.length" class="flex flex-wrap gap-1">
                      <span v-for="cid in t.criteria" :key="cid" class="inline-block px-1.5 py-0.5 rounded text-xs font-bold text-white"
                        :style="{ backgroundColor: acById(cid)?.color || '#6b7280' }" :title="acById(cid)?.text">{{ cid }}</span>
                    </span>
                    <span v-else class="text-gray-300 dark:text-gray-600 text-xs">-</span>
                  </td>
                  <td class="px-4 py-2.5 text-xs" :class="statusClass(testStatus(t))">{{ testStatus(t).toUpperCase() }}</td>
                </tr>
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
                        <span v-if="acById(cid)" class="text-gray-500"> - {{ acById(cid)?.text }}</span>
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

        <div class="mt-3 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
          <span>Showing {{ tests.length }} of {{ totalFiltered }} tests</span>
          <div v-if="totalPages > 1" class="flex items-center gap-2">
            <button @click="currentPage--" :disabled="currentPage === 1" class="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-700">
              <i class="pi pi-chevron-left"></i>
            </button>
            <span>Page {{ currentPage }} / {{ totalPages }}</span>
            <button @click="currentPage++" :disabled="currentPage >= totalPages" class="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-700">
              <i class="pi pi-chevron-right"></i>
            </button>
          </div>
        </div>

        <div class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <button @click="downloadPdf" class="flex items-center gap-2 px-4 py-2 bg-gray-800 dark:bg-gray-600 text-white rounded-lg hover:bg-gray-700 text-sm">
            <i class="pi pi-download"></i>
            Download Filtered PDF
            <span v-if="search || filterCriterion || filterType || filterStatus" class="text-xs opacity-70">(filtered)</span>
          </button>
        </div>
      </div>

      </template>

      <!-- ══ TAB 2: CODE COVERAGE ══ -->
      <template v-else-if="activeTab === 'code_coverage'">

      <!-- ── Code Coverage ── -->
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <div class="flex items-center justify-between mb-4">
          <h3 class="font-semibold text-gray-800 dark:text-white">Code Coverage</h3>
          <span v-if="coverage" class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="coverage.status === 'available' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'">
            {{ coverage.tool ?? coverage.status }}
          </span>
        </div>

        <div v-if="!coverage" class="text-sm text-gray-400 text-center py-6">
          Run <strong>Refresh Quality Analysis</strong> in the Deployment tab to generate coverage data.
        </div>

        <div v-else-if="coverage.status !== 'available'" class="flex items-start gap-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-sm text-gray-600 dark:text-gray-300">
          <i class="pi pi-info-circle mt-0.5 text-gray-400"></i>
          <div>
            <span class="font-medium capitalize">{{ coverage.status }}</span>
            <span v-if="coverage.reason" class="ml-1">- {{ coverage.reason }}</span>
          </div>
        </div>

        <template v-else>
          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 mb-5">
            <div class="text-center p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50">
              <div class="text-2xl font-bold" :class="scoreColor(coverage.overall ?? 0)">{{ coveragePct(coverage.overall) }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">Overall</div>
            </div>
            <div v-if="coverage.statements !== null" class="text-center p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50">
              <div class="text-xl font-bold text-gray-700 dark:text-gray-200">{{ coveragePct(coverage.statements) }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">Statements</div>
            </div>
            <div v-if="coverage.functions !== null" class="text-center p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50">
              <div class="text-xl font-bold text-gray-700 dark:text-gray-200">{{ coveragePct(coverage.functions) }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">Functions</div>
            </div>
            <div v-if="coverage.branches !== null" class="text-center p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50">
              <div class="text-xl font-bold text-gray-700 dark:text-gray-200">{{ coveragePct(coverage.branches) }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">Branches</div>
            </div>
          </div>

          <div v-if="coverage.files && coverage.files.length > 0">
            <h4 class="text-sm font-medium text-gray-600 dark:text-gray-300 mb-2">File Coverage</h4>
            <div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
              <table class="w-full text-xs">
                <thead class="bg-gray-50 dark:bg-gray-900/50">
                  <tr>
                    <th class="text-left px-3 py-2 font-medium text-gray-600 dark:text-gray-300">File</th>
                    <th class="text-right px-3 py-2 font-medium text-gray-600 dark:text-gray-300 w-20">Coverage</th>
                    <th class="px-3 py-2 w-32"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="f in coverage.files.slice(0, 30)" :key="f.path" class="border-t border-gray-100 dark:border-gray-700">
                    <td class="px-3 py-1.5 font-mono text-gray-700 dark:text-gray-300 truncate max-w-xs" :title="f.path">{{ f.path }}</td>
                    <td class="px-3 py-1.5 text-right font-semibold" :class="scoreColor(f.coverage)">{{ f.coverage.toFixed(1) }}%</td>
                    <td class="px-3 py-1.5">
                      <div class="h-1.5 rounded-full bg-gray-200 dark:bg-gray-600">
                        <div class="h-1.5 rounded-full transition-all" :class="coverageBar(f.coverage)" :style="{ width: f.coverage + '%' }"></div>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="coverage.files.length > 30">
                    <td colspan="3" class="px-3 py-2 text-gray-400 text-center">…and {{ coverage.files.length - 30 }} more files</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </div>

      <!-- ── Code Review ── -->
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <div class="flex items-center justify-between mb-3">
          <h3 class="font-semibold text-gray-800 dark:text-white">Code Review</h3>
          <div v-if="review" class="flex items-center gap-3">
            <span class="text-sm font-bold" :class="scoreColor(review.scores?.overall ?? 100)">
              {{ review.scores?.overall ?? '-' }} / 100
            </span>
          </div>
        </div>

        <div v-if="!review" class="text-sm text-gray-400 text-center py-6">
          Run <strong>Refresh Quality Analysis</strong> in the Deployment tab to generate code review.
        </div>

        <template v-else>
          <p v-if="review.summary" class="text-sm text-gray-600 dark:text-gray-300 mb-4 italic">{{ review.summary }}</p>

          <!-- Review sub-tabs: Findings | Details -->
          <div class="flex gap-1 border-b border-gray-200 dark:border-gray-700 mb-4">
            <button @click="reviewTab = 'findings'"
              :class="reviewTab === 'findings' ? 'border-b-2 border-blue-500 text-blue-600 dark:text-blue-400 font-medium' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
              class="px-3 py-2 text-sm transition-colors">
              Findings
            </button>
            <button @click="reviewTab = 'details'"
              :class="reviewTab === 'details' ? 'border-b-2 border-blue-500 text-blue-600 dark:text-blue-400 font-medium' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
              class="px-3 py-2 text-sm transition-colors">
              Details
            </button>
          </div>

          <!-- Findings sub-tab -->
          <div v-if="reviewTab === 'findings'">
            <!-- Category scores -->
            <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
              <div v-for="(label, cat) in { maintainability: 'Maintainability', readability: 'Readability', error_handling: 'Error Handling', architecture_fit: 'Architecture', security: 'Security' }"
                :key="cat" class="text-center p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50">
                <div class="text-xl font-bold" :class="scoreColor((review.scores as any)[cat] ?? 100)">
                  {{ (review.scores as any)[cat] ?? 100 }}
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 leading-tight">{{ label }}</div>
              </div>
            </div>

            <!-- Finding counts -->
            <div class="flex items-center gap-4 mb-4 text-xs">
              <span class="px-2 py-1 rounded font-semibold" :class="findingCounts.critical > 0 ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'">
                Critical: {{ findingCounts.critical }}
              </span>
              <span class="px-2 py-1 rounded font-semibold" :class="findingCounts.high > 0 ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'">
                High: {{ findingCounts.high }}
              </span>
              <span class="px-2 py-1 rounded font-semibold" :class="findingCounts.medium > 0 ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'">
                Medium: {{ findingCounts.medium }}
              </span>
              <span class="px-2 py-1 rounded" :class="findingCounts.low > 0 ? 'bg-gray-100 text-gray-600' : 'bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500'">
                Low: {{ findingCounts.low }}
              </span>
            </div>

            <!-- Findings Explorer -->
            <div class="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
              <div class="bg-gray-50 dark:bg-gray-900/50 px-4 py-2.5 font-medium text-xs text-gray-600 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
                CODE REVIEW FINDINGS
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 p-3 border-b border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50">
                <input v-model="findingSearch" type="text" placeholder="Search findings..."
                  class="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500" />
                <select v-model="findingSeverity"
                  class="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500">
                  <option value="">Severity: All</option>
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
                <select v-model="findingCategory"
                  class="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500">
                  <option value="">Category: All</option>
                  <option value="maintainability">Maintainability</option>
                  <option value="readability">Readability</option>
                  <option value="error_handling">Error Handling</option>
                  <option value="architecture_fit">Architecture Fit</option>
                  <option value="security">Security</option>
                </select>
                <select v-model="findingFile"
                  class="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500">
                  <option value="">File: All</option>
                  <option v-for="f in uniqueFiles" :key="f" :value="f">{{ f }}</option>
                </select>
              </div>
              <div v-if="filteredFindings.length === 0" class="px-4 py-6 text-center text-sm text-gray-400">
                {{ review.findings.length === 0 ? 'No findings - code review passed all checks.' : 'No findings match the current filters.' }}
              </div>
              <div v-else class="divide-y divide-gray-100 dark:divide-gray-700">
                <div v-for="(f, idx) in paginatedFindings" :key="idx" class="px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                  <div class="flex items-start gap-2 mb-1">
                    <span class="text-xs px-2 py-0.5 rounded font-bold uppercase flex-shrink-0" :class="severityClass(f.severity)">{{ f.severity }}</span>
                    <span class="text-xs px-2 py-0.5 rounded bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 flex-shrink-0">{{ categoryLabel(f.category) }}</span>
                    <span class="text-xs text-gray-500 dark:text-gray-400 font-mono truncate">{{ f.file }}</span>
                  </div>
                  <div v-if="f.line_or_area" class="text-xs text-gray-500 dark:text-gray-400 mb-1">Area: {{ f.line_or_area }}</div>
                  <p class="text-sm text-gray-700 dark:text-gray-200">{{ f.finding }}</p>
                  <p v-if="f.recommendation" class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    <span class="font-medium">Recommendation:</span> {{ f.recommendation }}
                  </p>
                </div>
              </div>
              <!-- Findings pagination -->
              <div v-if="filteredFindings.length > 0" class="flex items-center justify-between px-4 py-2.5 border-t border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50">
                <span class="text-xs text-gray-500 dark:text-gray-400">
                  {{ (findingPage - 1) * findingPageSize + 1 }}-{{ Math.min(findingPage * findingPageSize, filteredFindings.length) }} of {{ filteredFindings.length }}
                </span>
                <div class="flex items-center gap-1">
                  <button @click="findingPage--" :disabled="findingPage === 1"
                    class="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-700 transition">
                    <i class="pi pi-chevron-left text-xs"></i>
                  </button>
                  <span class="text-xs text-gray-500 dark:text-gray-400 px-2">{{ findingPage }} / {{ findingTotalPages }}</span>
                  <button @click="findingPage++" :disabled="findingPage >= findingTotalPages"
                    class="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-700 transition">
                    <i class="pi pi-chevron-right text-xs"></i>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Details sub-tab -->
          <div v-else class="space-y-5">
            <!-- Personal Info -->
            <div>
              <h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                <i class="pi pi-user text-blue-500"></i> Personal Info Collected by Code
              </h4>
              <div v-if="reviewDetails.personal_info.length === 0" class="text-sm text-gray-400 italic px-3 py-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg">None detected.</div>
              <ul v-else class="space-y-1.5">
                <li v-for="(item, idx) in reviewDetails.personal_info" :key="idx"
                  class="flex items-start gap-2 text-sm px-3 py-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-blue-800 dark:text-blue-300">
                  <i class="pi pi-circle-fill text-xs mt-1 flex-shrink-0 text-blue-400"></i>
                  {{ item }}
                </li>
              </ul>
            </div>
            <!-- Sensitive Info -->
            <div>
              <h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                <i class="pi pi-lock text-amber-500"></i> Sensitive Info Generated by Application
              </h4>
              <div v-if="reviewDetails.sensitive_info.length === 0" class="text-sm text-gray-400 italic px-3 py-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg">None detected.</div>
              <ul v-else class="space-y-1.5">
                <li v-for="(item, idx) in reviewDetails.sensitive_info" :key="idx"
                  class="flex items-start gap-2 text-sm px-3 py-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg text-amber-800 dark:text-amber-300">
                  <i class="pi pi-circle-fill text-xs mt-1 flex-shrink-0 text-amber-400"></i>
                  {{ item }}
                </li>
              </ul>
            </div>
            <!-- Bad Practices -->
            <div>
              <h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                <i class="pi pi-exclamation-circle text-red-500"></i> Bad Code Practices
              </h4>
              <div v-if="reviewDetails.bad_practices.length === 0" class="text-sm text-gray-400 italic px-3 py-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg">None detected.</div>
              <ul v-else class="space-y-1.5">
                <li v-for="(item, idx) in reviewDetails.bad_practices" :key="idx"
                  class="flex items-start gap-2 text-sm px-3 py-2 bg-red-50 dark:bg-red-900/20 rounded-lg text-red-800 dark:text-red-300">
                  <i class="pi pi-circle-fill text-xs mt-1 flex-shrink-0 text-red-400"></i>
                  {{ item }}
                </li>
              </ul>
            </div>
          </div>
        </template>
      </div>

      </template>

      <!-- ══ TAB 3: DEPLOYMENT ══ -->
      <template v-else>

      <!-- ── Deployment Readiness Checklist ── -->
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <div class="flex items-center justify-between mb-4">
          <h3 class="font-semibold text-gray-800 dark:text-white">Deployment Readiness Checklist</h3>
          <div v-if="releaseReadiness" class="flex items-center gap-2">
            <span class="text-sm font-medium text-gray-500 dark:text-gray-400">
              {{ releaseReadiness.passed_checks }} / {{ releaseReadiness.total_checks }} checks
            </span>
          </div>
        </div>

        <div v-if="!releaseReadiness" class="text-sm text-gray-400 text-center py-6">
          Run <strong>Refresh Quality Analysis</strong> below to evaluate deployment readiness.
        </div>

        <template v-else>
          <div class="flex items-center gap-3 px-4 py-3 rounded-lg mb-4"
            :class="releaseReadiness.status === 'ready'
              ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300'
              : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300'">
            <i :class="releaseReadiness.status === 'ready' ? 'pi pi-check-circle text-xl' : 'pi pi-times-circle text-xl'"></i>
            <div class="flex-1">
              <div class="font-bold text-base">
                {{ releaseReadiness.status === 'ready' ? 'DEPLOYMENT READY' : 'NOT DEPLOYMENT READY' }}
              </div>
              <div class="text-sm opacity-80">{{ releaseReadiness.passed_checks }} / {{ releaseReadiness.total_checks }} checks passed</div>
            </div>
          </div>

          <!-- Checklist -->
          <div class="space-y-2 mb-4">
            <div v-for="c in releaseReadiness.checks" :key="c.key"
              class="flex items-center gap-3 px-4 py-3 rounded-lg border"
              :class="c.passed
                ? 'border-green-200 bg-green-50 dark:bg-green-900/10 dark:border-green-800/50'
                : c.blocking
                  ? 'border-red-200 bg-red-50 dark:bg-red-900/10 dark:border-red-800/50'
                  : 'border-amber-200 bg-amber-50 dark:bg-amber-900/10 dark:border-amber-800/50'">
              <i :class="c.passed ? 'pi pi-check-circle text-green-500 text-lg' : c.blocking ? 'pi pi-times-circle text-red-500 text-lg' : 'pi pi-exclamation-triangle text-amber-500 text-lg'"
                class="flex-shrink-0"></i>
              <div class="flex-1 min-w-0">
                <span class="text-sm font-medium" :class="c.passed ? 'text-green-700 dark:text-green-300' : c.blocking ? 'text-red-700 dark:text-red-300' : 'text-amber-700 dark:text-amber-300'">
                  {{ normalizeCheckLabel(c.label) }}
                </span>
                <span v-if="!c.passed && c.message" class="block text-xs mt-0.5 opacity-75">{{ c.message }}</span>
              </div>
            </div>
          </div>
        </template>

        <div class="mt-5 pt-4 border-t border-gray-200 dark:border-gray-700 flex items-center gap-4 flex-wrap">
          <button @click="refreshQualityAnalysis" :disabled="analyzeLoading"
            class="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm">
            <i :class="analyzeLoading ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'"></i>
            {{ analyzeLoading ? 'Running Analysis…' : 'Refresh Quality Analysis' }}
          </button>
          <div v-if="codeQuality" class="text-xs text-gray-400 dark:text-gray-500">
            Last run: {{ new Date(codeQuality.generated_at).toLocaleString() }}
          </div>
          <span v-if="analyzeMsg" class="text-xs text-green-600 dark:text-green-400">{{ analyzeMsg }}</span>
          <span v-if="analyzeError" class="text-xs text-red-600 dark:text-red-400">{{ analyzeError }}</span>
        </div>
      </div>

      <!-- ── Deployment Guide (README) ── -->
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 class="font-semibold text-gray-800 dark:text-white mb-3">Deployment Guide (README)</h3>
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
          <span v-if="readmeMsg" class="text-xs" :class="readmeMsg.includes('failed') ? 'text-red-500' : 'text-green-600'">{{ readmeMsg }}</span>
        </div>
      </div>

      <!-- ── GitHub Configuration ── -->
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 class="font-semibold text-gray-800 dark:text-white mb-3">GitHub Configuration</h3>

        <div v-if="pushBlocked" class="mb-3 flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2">
          <i class="pi pi-lock"></i>
          {{ pushBlocked }}
        </div>

        <div v-if="pushResult" class="mb-3 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg text-sm">
          <p class="text-green-700 dark:text-green-300 font-medium">Pushed successfully</p>
          <p class="text-green-600 dark:text-green-400 mt-1">Branch: <code class="bg-green-100 dark:bg-green-900/40 px-1 rounded">{{ pushResult.branch }}</code></p>
          <p v-if="pushResult.pr_url" class="text-green-600 dark:text-green-400 mt-0.5">
            PR: <a :href="pushResult.pr_url" target="_blank" class="underline hover:no-underline">{{ pushResult.pr_url }}</a>
          </p>
        </div>

        <div v-if="pushError" class="mb-3 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
          {{ pushError }}
        </div>

        <div class="flex items-center gap-3">
          <button @click="handlePush" :disabled="!!pushBlocked || pushLoading"
            class="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm">
            <i :class="pushLoading ? 'pi pi-spin pi-spinner' : 'pi pi-cloud-upload'"></i>
            {{ pushLoading ? 'Pushing...' : 'Push to GitHub' }}
          </button>
          <span v-if="repoConfigured" class="text-xs text-gray-500 dark:text-gray-400">
            <i class="pi pi-check-circle text-green-500 mr-1"></i> Repository configured
          </span>
          <span v-else class="text-xs text-gray-400">Repository not configured - will ask on push</span>
        </div>
      </div>

      </template>

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
            <button @click="showRepoModal = false" class="px-4 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">Cancel</button>
            <button @click="saveAndPush" :disabled="!pushRepoUrl.trim() || !pushPat.trim()" class="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
              Save &amp; Push
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
