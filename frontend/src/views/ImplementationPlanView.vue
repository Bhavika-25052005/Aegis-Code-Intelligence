<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import api from '../api/client'
import KnowledgeGraphPanel from '../components/KnowledgeGraphPanel.vue'
import DataModelTable from '../components/implementation/DataModelTable.vue'
import DataModelDiagram from '../components/implementation/DataModelDiagram.vue'

const route = useRoute()
const router = useRouter()

const projectId = route.params.id as string
const storyId = route.params.storyId as string

const data = ref<any>(null)
const loading = ref(true)
const planning = ref(false)
const approving = ref(false)
const error = ref('')
const activeTab = ref<'plan' | 'datamodel' | 'graph'>('plan')

// ── Data Model ─────────────────────────────────────────────────────────────
const dataModel = computed(() => data.value?.data_model ?? null)
const dataModelStatus = computed(() => data.value?.data_model_status ?? 'not_generated')
const dataModelView = ref<'table' | 'diagram'>('table')
const generatingModel = ref(false)
const approvingModel = ref(false)
const showDownloadMenu = ref(false)

async function generateDataModel() {
  generatingModel.value = true
  error.value = ''
  try {
    const res = await api.post(`/projects/${projectId}/requirements/${storyId}/data-model`)
    data.value = { ...data.value, data_model: res.data.data_model, data_model_status: res.data.data_model_status }
  } catch (err: unknown) {
    if (axios.isAxiosError(err)) error.value = err.response?.data?.detail || err.message
  } finally {
    generatingModel.value = false
  }
}

async function approveDataModel() {
  approvingModel.value = true
  try {
    await api.post(`/projects/${projectId}/requirements/${storyId}/data-model/approve`)
    data.value = { ...data.value, data_model_status: 'approved' }
  } catch (err: unknown) {
    if (axios.isAxiosError(err)) error.value = err.response?.data?.detail || err.message
  } finally {
    approvingModel.value = false
  }
}

async function reopenDataModel() {
  await api.post(`/projects/${projectId}/requirements/${storyId}/data-model/reopen`)
  data.value = { ...data.value, data_model_status: 'draft' }
}

function downloadDataModel(fmt: string) {
  showDownloadMenu.value = false
  window.open(`/api/projects/${projectId}/requirements/${storyId}/data-model/download?format=${fmt}`, '_blank')
}

async function saveDataModel(updatedModel: any) {
  try {
    const res = await api.patch(`/projects/${projectId}/requirements/${storyId}/data-model`, updatedModel)
    data.value = { ...data.value, data_model: res.data.data_model, data_model_status: res.data.data_model_status }
  } catch (err: unknown) {
    if (axios.isAxiosError(err)) error.value = err.response?.data?.detail || err.message
  }
}

async function uploadDataModelFile(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return
  const file = input.files[0]
  const formData = new FormData()
  formData.append('file', file)
  input.value = ''
  try {
    const res = await api.post(
      `/projects/${projectId}/requirements/${storyId}/data-model/upload`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    data.value = { ...data.value, data_model: res.data.data_model, data_model_status: res.data.data_model_status }
  } catch (err: unknown) {
    if (axios.isAxiosError(err)) error.value = err.response?.data?.detail || err.message
  }
}

// Edit state
const editingSection = ref<string | null>(null)
const editDraft = ref<any>(null)
const saving = ref(false)

const plan = computed(() => data.value?.implementation_plan ?? null)

const orderedTasks = computed(() =>
  [...(plan.value?.task_plan ?? [])].sort(
    (a: any, b: any) => a.execution_order - b.execution_order,
  ),
)

// ── Load / Generate / Approve ────────────────────────────────────────────────

async function loadPlan() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get(
      `/projects/${projectId}/requirements/${storyId}/implementation-plan`,
    )
    data.value = res.data
  } catch (err: unknown) {
    if (axios.isAxiosError(err)) error.value = err.response?.data?.detail || err.message
  } finally {
    loading.value = false
  }
}

async function generatePlan() {
  planning.value = true
  error.value = ''
  try {
    const res = await api.post(
      `/projects/${projectId}/requirements/${storyId}/implementation-plan`,
    )
    data.value = res.data
    editingSection.value = null
  } catch (err: unknown) {
    if (axios.isAxiosError(err)) {
      const d = err.response?.data?.detail
      error.value = typeof d === 'string' ? d : JSON.stringify(d)
    }
  } finally {
    planning.value = false
  }
}

async function approvePlan() {
  approving.value = true
  error.value = ''
  try {
    await api.post(
      `/projects/${projectId}/requirements/${storyId}/implementation-plan/approve`,
    )
    await loadPlan()
  } finally {
    approving.value = false
  }
}

async function reopenPlan() {
  await api.post(
    `/projects/${projectId}/requirements/${storyId}/implementation-plan/reopen`,
  )
  await loadPlan()
}

// ── Edit helpers ─────────────────────────────────────────────────────────────

function startEdit(section: string, value: any) {
  editingSection.value = section
  // Deep clone so we don't mutate displayed data until saved
  editDraft.value = JSON.parse(JSON.stringify(value))
}

function cancelEdit() {
  editingSection.value = null
  editDraft.value = null
}

async function saveEdit(section: string) {
  saving.value = true
  error.value = ''
  try {
    const payload: any = {}

    if (section === 'work_summary') {
      payload.work_summary = editDraft.value
    } else if (section === 'planned_changes') {
      payload.planned_changes = editDraft.value
    } else if (section === 'task_approaches') {
      payload.task_plan = editDraft.value
    } else {
      payload[section] = editDraft.value
    }

    const res = await api.patch(
      `/projects/${projectId}/requirements/${storyId}/implementation-plan`,
      payload,
    )
    // Merge updated plan back into data
    data.value = {
      ...data.value,
      implementation_plan: res.data.implementation_plan,
      implementation_plan_status: res.data.implementation_plan_status,
      approved_at: res.data.approved_at,
    }
    editingSection.value = null
    editDraft.value = null
  } catch (err: unknown) {
    if (axios.isAxiosError(err)) error.value = err.response?.data?.detail || err.message
  } finally {
    saving.value = false
  }
}

function addListItem(arr: string[]) {
  arr.push('')
}

function removeListItem(arr: string[], i: number) {
  arr.splice(i, 1)
}

// ── Navigation ───────────────────────────────────────────────────────────────

function goBack() {
  router.push(`/projects/${projectId}/requirements/${storyId}`)
}

function goToExecution(skipTests: boolean) {
  router.push({
    path: `/projects/${projectId}/execute`,
    query: {
      story_id: storyId,
      skip_tests: skipTests ? '1' : '0',
    },
  })
}

onMounted(loadPlan)
</script>

<template>
  <div class="space-y-4">

    <!-- ── Tab Navigation ── -->
    <div class="flex gap-1 border-b border-gray-200 dark:border-gray-700">
      <button @click="activeTab = 'plan'"
        :class="activeTab === 'plan' ? 'border-b-2 border-purple-500 text-purple-600 dark:text-purple-400 font-medium' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
        class="px-4 py-2.5 text-sm transition-colors">
        Implementation Plan
      </button>
      <button @click="activeTab = 'datamodel'"
        :class="activeTab === 'datamodel' ? 'border-b-2 border-purple-500 text-purple-600 dark:text-purple-400 font-medium' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
        class="px-4 py-2.5 text-sm transition-colors flex items-center gap-1.5">
        <i class="pi pi-database text-xs"></i>
        Data Model
        <span v-if="dataModelStatus === 'approved'" class="text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300 px-1.5 py-0.5 rounded-full">Approved</span>
        <span v-else-if="dataModelStatus === 'draft'" class="text-xs bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 px-1.5 py-0.5 rounded-full">Draft</span>
      </button>
      <button @click="activeTab = 'graph'"
        :class="activeTab === 'graph' ? 'border-b-2 border-purple-500 text-purple-600 dark:text-purple-400 font-medium' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
        class="px-4 py-2.5 text-sm transition-colors flex items-center gap-1.5">
        <i class="pi pi-sitemap text-xs"></i>
        Knowledge Graph
      </button>
    </div>

    <!-- ── Knowledge Graph tab ── -->
    <template v-if="activeTab === 'graph'">
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <KnowledgeGraphPanel :project-id="projectId" :story-id="storyId" mode="implementation" />
      </div>
    </template>

    <!-- ── Data Model tab ── -->
    <template v-else-if="activeTab === 'datamodel'">
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 space-y-4">

        <!-- Header -->
        <div class="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h3 class="font-semibold text-gray-800 dark:text-white">Data Model</h3>
            <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Entity-relationship model generated from your implementation plan.</p>
          </div>
          <div class="flex items-center gap-2 flex-wrap">
            <template v-if="dataModel">
              <!-- Approve / Reopen -->
              <button v-if="dataModelStatus !== 'approved'" @click="approveDataModel" :disabled="approvingModel"
                class="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50">
                <i :class="approvingModel ? 'pi pi-spin pi-spinner' : 'pi pi-check'" class="text-xs"></i>
                {{ approvingModel ? 'Approving...' : 'Approve Model' }}
              </button>
              <div v-else class="flex items-center gap-2">
                <span class="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400 font-medium">
                  <i class="pi pi-check-circle"></i> Approved v{{ dataModel.version }}
                </span>
                <button @click="reopenDataModel" class="text-xs px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
                  Reopen
                </button>
              </div>
              <!-- Export dropdown -->
              <div class="relative">
                <button @click="showDownloadMenu = !showDownloadMenu"
                  class="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
                  <i class="pi pi-download text-xs"></i> Export <i class="pi pi-chevron-down text-xs"></i>
                </button>
                <div v-if="showDownloadMenu" class="absolute right-0 mt-1 w-28 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg z-20 overflow-hidden">
                  <button @click="downloadDataModel('json')" class="w-full text-left px-3 py-2 text-xs hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300">JSON</button>
                  <button @click="downloadDataModel('sql')" class="w-full text-left px-3 py-2 text-xs hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300">SQL</button>
                  <button @click="downloadDataModel('dbml')" class="w-full text-left px-3 py-2 text-xs hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300">DBML</button>
                </div>
                <div v-if="showDownloadMenu" class="fixed inset-0 z-10" @click="showDownloadMenu = false"></div>
              </div>
            </template>
            <!-- Import JSON -->
            <label class="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer">
              <i class="pi pi-upload text-xs"></i> Import JSON
              <input type="file" accept=".json" class="hidden" @change="uploadDataModelFile" />
            </label>
            <!-- Generate / Regenerate -->
            <button @click="generateDataModel" :disabled="generatingModel"
              class="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50">
              <i :class="generatingModel ? 'pi pi-spin pi-spinner' : 'pi pi-sparkles'" class="text-xs"></i>
              {{ generatingModel ? 'Generating...' : dataModel ? 'Regenerate' : 'Generate Data Model' }}
            </button>
          </div>
        </div>

        <!-- Empty state -->
        <div v-if="!dataModel && !generatingModel"
          class="flex flex-col items-center justify-center py-16 text-center bg-gray-50 dark:bg-gray-900/30 rounded-xl border-2 border-dashed border-gray-200 dark:border-gray-700">
          <div class="w-14 h-14 rounded-2xl bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center mb-4">
            <i class="pi pi-database text-2xl text-purple-500"></i>
          </div>
          <h4 class="font-semibold text-gray-700 dark:text-gray-300 mb-1">No Data Model Yet</h4>
          <p class="text-sm text-gray-500 dark:text-gray-400 max-w-xs mb-5">
            Claude will analyse your implementation plan and design the full entity-relationship model — automatically generated when the plan is created.
          </p>
          <button @click="generateDataModel" class="px-5 py-2.5 rounded-xl bg-purple-600 text-white hover:bg-purple-700 text-sm font-medium flex items-center gap-2">
            <i class="pi pi-sparkles"></i> Generate Data Model
          </button>
        </div>

        <!-- Loading -->
        <div v-else-if="generatingModel" class="flex flex-col items-center justify-center py-16">
          <i class="pi pi-spin pi-spinner text-3xl text-purple-500 mb-3"></i>
          <p class="text-sm text-gray-500 dark:text-gray-400">Claude is designing your data model...</p>
          <p class="text-xs text-gray-400 mt-1">This takes 15-30 seconds</p>
        </div>

        <!-- Data model content -->
        <template v-else-if="dataModel">
          <!-- Stats row -->
          <div class="flex items-center gap-5 text-xs text-gray-500 dark:text-gray-400 flex-wrap">
            <span><span class="font-semibold text-gray-700 dark:text-gray-200">{{ dataModel.entities?.length ?? 0 }}</span> entities</span>
            <span><span class="font-semibold text-gray-700 dark:text-gray-200">{{ dataModel.enums?.length ?? 0 }}</span> enums</span>
            <span><span class="font-semibold text-gray-700 dark:text-gray-200">{{ dataModel.entities?.reduce((s:number, e:any) => s + (e.fields?.length ?? 0), 0) ?? 0 }}</span> total fields</span>
            <span class="ml-auto text-gray-400">v{{ dataModel.version }} &middot; {{ dataModel.project_mode === 'new_project' ? 'New project' : 'Enhancement' }}</span>
          </div>

          <!-- View toggle -->
          <div class="flex items-center gap-1 p-1 bg-gray-100 dark:bg-gray-700/50 rounded-lg w-fit">
            <button @click="dataModelView = 'table'"
              :class="dataModelView === 'table' ? 'bg-white dark:bg-gray-800 shadow-sm text-gray-800 dark:text-white font-medium' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
              class="px-3 py-1.5 rounded-md text-xs transition-colors flex items-center gap-1.5">
              <i class="pi pi-table text-xs"></i> Table
            </button>
            <button @click="dataModelView = 'diagram'"
              :class="dataModelView === 'diagram' ? 'bg-white dark:bg-gray-800 shadow-sm text-gray-800 dark:text-white font-medium' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
              class="px-3 py-1.5 rounded-md text-xs transition-colors flex items-center gap-1.5">
              <i class="pi pi-share-alt text-xs"></i> Diagram
            </button>
          </div>

          <DataModelTable v-if="dataModelView === 'table'" :model="dataModel" :readonly="dataModelStatus === 'approved'" @update="saveDataModel" />
          <DataModelDiagram v-else :model="dataModel" />
        </template>

      </div>
    </template>

    <!-- ── Plan tab ── -->
    <template v-else>

    <!-- Header -->
    <div class="flex items-start justify-between gap-4">
      <div>
        <button class="text-sm text-blue-600 mb-3" @click="goBack">
          &larr; Back to Requirement Intelligence
        </button>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          Implementation Intelligence
        </h1>
        <p class="text-sm text-gray-500 mt-1">
          Understand the codebase, approve task order, then generate code.
        </p>
      </div>
      <button
        class="px-5 py-2.5 rounded-lg bg-purple-600 text-white disabled:opacity-50"
        :disabled="planning"
        @click="generatePlan"
      >
        {{ planning ? 'Analyzing Repository...' : plan ? 'Regenerate Plan' : 'Generate Implementation Plan' }}
      </button>
    </div>

    <div v-if="error" class="p-4 rounded-lg bg-red-50 text-red-700 border border-red-200">
      {{ error }}
    </div>
    <div v-if="loading" class="py-16 text-center text-gray-500">Loading implementation intelligence...</div>

    <template v-else-if="data">
      <!-- Context -->
      <section class="bg-white dark:bg-gray-800 rounded-xl border p-5">
        <p class="text-xs uppercase text-gray-400">Feature</p>
        <p class="font-medium text-purple-600">{{ data.feature_title }}</p>
        <p class="text-xs uppercase text-gray-400 mt-4">User Story</p>
        <h2 class="text-lg font-semibold">{{ data.user_story_title }}</h2>
      </section>

      <!-- Empty state -->
      <section
        v-if="!plan"
        class="bg-white dark:bg-gray-800 rounded-xl border border-dashed p-10 text-center"
      >
        <h3 class="font-semibold">No implementation plan yet</h3>
        <p class="text-sm text-gray-500 mt-2">
          Aegis will scan repository metadata, find relevant code, and order the imported tasks.
        </p>
      </section>

      <template v-else>
        <!-- Status bar -->
        <section class="bg-white dark:bg-gray-800 rounded-xl border p-5 flex justify-between gap-4 flex-wrap">
          <div>
            <div class="flex items-center gap-3 flex-wrap">
              <span class="font-semibold">Implementation Plan</span>
              <span class="text-xs px-3 py-1 rounded-full bg-purple-100 text-purple-700">
                {{ plan.project_mode === 'new_project' ? 'New Project' : 'Existing Project' }}
              </span>
              <span
                class="text-xs px-3 py-1 rounded-full"
                :class="data.implementation_plan_status === 'approved' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'"
              >
                {{ data.implementation_plan_status }}
              </span>
            </div>
            <p class="text-sm text-gray-500 mt-1">Editing or regenerating requires approval again.</p>
          </div>
          <button
            v-if="data.implementation_plan_status !== 'approved'"
            class="px-5 py-2.5 rounded-lg bg-green-600 text-white disabled:opacity-50"
            :disabled="approving"
            @click="approvePlan"
          >
            {{ approving ? 'Approving...' : 'Approve Implementation Plan' }}
          </button>
          <div v-else class="flex items-center gap-4">
            <span class="text-green-600 font-medium">&#10003; Approved for Code Generation</span>
            <button class="text-sm text-gray-500 underline" @click="reopenPlan">Reopen</button>
          </div>
        </section>

        <!-- Work Summary -->
        <section class="bg-white dark:bg-gray-800 rounded-xl border p-5">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-semibold">Implementation Summary</h3>
            <div v-if="editingSection !== 'work_summary'" >
              <button
                class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-gray-500 hover:border-blue-300 hover:text-blue-600"
                @click="startEdit('work_summary', plan.work_summary)"
              >Edit</button>
            </div>
            <div v-else class="flex gap-2">
              <button
                class="text-xs px-3 py-1 rounded-lg bg-blue-600 text-white disabled:opacity-50"
                :disabled="saving"
                @click="saveEdit('work_summary')"
              >{{ saving ? 'Saving…' : 'Save' }}</button>
              <button class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-gray-500" @click="cancelEdit">Cancel</button>
            </div>
          </div>
          <textarea
            v-if="editingSection === 'work_summary'"
            v-model="editDraft"
            rows="3"
            class="w-full text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 p-3 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y"
          />
          <p v-else class="text-sm">{{ plan.work_summary }}</p>
        </section>

        <!-- Architecture + Relevant Files -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <section class="bg-white dark:bg-gray-800 rounded-xl border p-5">
            <div class="flex items-center justify-between mb-3">
              <h3 class="font-semibold">Architecture Observations</h3>
              <div v-if="editingSection !== 'architecture_notes'">
                <button
                  class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-gray-500 hover:border-blue-300 hover:text-blue-600"
                  @click="startEdit('architecture_notes', plan.architecture_notes ?? [])"
                >Edit</button>
              </div>
              <div v-else class="flex gap-2">
                <button class="text-xs px-3 py-1 rounded-lg bg-blue-600 text-white disabled:opacity-50" :disabled="saving" @click="saveEdit('architecture_notes')">{{ saving ? 'Saving…' : 'Save' }}</button>
                <button class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-gray-500" @click="cancelEdit">Cancel</button>
              </div>
            </div>
            <template v-if="editingSection === 'architecture_notes'">
              <div v-for="(_, i) in editDraft" :key="i" class="flex gap-2 mb-2">
                <textarea v-model="editDraft[i]" rows="2" class="flex-1 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 p-2 resize-y" />
                <button class="text-xs px-2 py-1 rounded border border-red-200 text-red-500" @click="removeListItem(editDraft, i)">&#x2715;</button>
              </div>
              <button class="text-xs px-3 py-1.5 rounded-lg border border-dashed border-blue-300 text-blue-600 w-full mt-1" @click="addListItem(editDraft)">+ Add</button>
            </template>
            <template v-else>
              <p v-for="item in plan.architecture_notes" :key="item" class="text-sm mb-2">- {{ item }}</p>
              <p v-if="!plan.architecture_notes?.length" class="text-sm italic text-gray-400">None.</p>
            </template>
          </section>

          <section class="bg-white dark:bg-gray-800 rounded-xl border p-5">
            <h3 class="font-semibold mb-3">Relevant Repository Files</h3>
            <div v-for="file in plan.relevant_files" :key="file.path + file.action" class="mb-3 pb-3 border-b last:border-0">
              <div class="flex items-center gap-2">
                <code class="text-sm text-blue-600">{{ file.path }}</code>
                <span class="text-xs uppercase px-2 py-0.5 rounded bg-gray-100 text-gray-600">{{ file.action }}</span>
              </div>
              <p class="text-sm text-gray-500 mt-1">{{ file.reason }}</p>
            </div>
            <p v-if="!plan.relevant_files?.length" class="text-sm italic text-gray-400">None identified.</p>
          </section>
        </div>

        <!-- Planned Changes -->
        <section class="bg-white dark:bg-gray-800 rounded-xl border p-5">
          <div class="flex items-center justify-between mb-4">
            <h3 class="font-semibold">Planned Repository Changes</h3>
            <div v-if="editingSection !== 'planned_changes'">
              <button
                class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-gray-500 hover:border-blue-300 hover:text-blue-600"
                @click="startEdit('planned_changes', plan.planned_changes ?? [])"
              >Edit</button>
            </div>
            <div v-else class="flex gap-2">
              <button class="text-xs px-3 py-1 rounded-lg bg-blue-600 text-white disabled:opacity-50" :disabled="saving" @click="saveEdit('planned_changes')">{{ saving ? 'Saving…' : 'Save' }}</button>
              <button class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-gray-500" @click="cancelEdit">Cancel</button>
            </div>
          </div>

          <!-- Edit mode -->
          <template v-if="editingSection === 'planned_changes'">
            <div v-for="(change, i) in editDraft" :key="i" class="border rounded-lg p-3 mb-3">
              <div class="grid grid-cols-2 gap-2 mb-2">
                <div>
                  <label class="text-xs text-gray-400 uppercase">Path</label>
                  <input v-model="change.path" class="w-full text-sm border border-gray-300 dark:border-gray-600 rounded p-1.5 bg-white dark:bg-gray-700" />
                </div>
                <div>
                  <label class="text-xs text-gray-400 uppercase">Action</label>
                  <select v-model="change.action" class="w-full text-sm border border-gray-300 dark:border-gray-600 rounded p-1.5 bg-white dark:bg-gray-700">
                    <option>create</option>
                    <option>modify</option>
                    <option>reuse</option>
                  </select>
                </div>
              </div>
              <div class="mb-2">
                <label class="text-xs text-gray-400 uppercase">Purpose</label>
                <input v-model="change.purpose" class="w-full text-sm border border-gray-300 dark:border-gray-600 rounded p-1.5 bg-white dark:bg-gray-700" />
              </div>
              <div class="mb-2">
                <label class="text-xs text-gray-400 uppercase">Reason</label>
                <input v-model="change.reason" placeholder="Why this file is needed" class="w-full text-sm border border-gray-300 dark:border-gray-600 rounded p-1.5 bg-white dark:bg-gray-700" />
              </div>
              <button class="text-xs text-red-500 border border-red-200 rounded px-2 py-1" @click="removeListItem(editDraft, i)">Remove</button>
            </div>
            <button
              class="text-xs px-3 py-1.5 rounded-lg border border-dashed border-blue-300 text-blue-600 w-full"
              @click="editDraft.push({ path: '', action: 'create', purpose: '', reason: '' })"
            >+ Add File</button>
          </template>

          <!-- View mode -->
          <template v-else>
            <div
              v-for="change in plan.planned_changes"
              :key="change.path + change.action"
              class="border-b py-3 last:border-0"
            >
              <div class="flex items-center gap-2">
                <span class="text-xs uppercase font-semibold px-2 py-0.5 rounded"
                  :class="change.action === 'create' ? 'bg-green-100 text-green-700' : change.action === 'modify' ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-600'"
                >{{ change.action }}</span>
                <code class="text-sm text-blue-600">{{ change.path }}</code>
              </div>
              <p class="text-sm mt-1">{{ change.purpose }}</p>
              <p v-if="change.reason" class="text-xs text-gray-500 mt-0.5 italic">{{ change.reason }}</p>
            </div>
            <p v-if="!plan.planned_changes?.length" class="text-sm italic text-gray-400">None.</p>
          </template>
        </section>

        <!-- Ordered Task Execution -->
        <section class="bg-white dark:bg-gray-800 rounded-xl border p-5">
          <div class="flex items-center justify-between mb-4">
            <h3 class="font-semibold">Ordered Task Execution</h3>
            <div v-if="editingSection !== 'task_approaches'">
              <button
                class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-gray-500 hover:border-blue-300 hover:text-blue-600"
                @click="startEdit('task_approaches', orderedTasks.map((t: any) => ({ task_id: t.task_id, task_title: t.task_title, execution_order: t.execution_order, depends_on: t.depends_on, approach: t.approach, related_files: t.related_files ?? [] })))"
              >Edit Approaches</button>
            </div>
            <div v-else class="flex gap-2">
              <button class="text-xs px-3 py-1 rounded-lg bg-blue-600 text-white disabled:opacity-50" :disabled="saving" @click="saveEdit('task_approaches')">{{ saving ? 'Saving…' : 'Save' }}</button>
              <button class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-gray-500" @click="cancelEdit">Cancel</button>
            </div>
          </div>

          <!-- Edit mode for task approaches -->
          <template v-if="editingSection === 'task_approaches'">
            <div v-for="(task, i) in editDraft" :key="task.task_id" class="border rounded-lg p-4 mb-3">
              <div class="flex items-center gap-3 mb-2">
                <span class="w-7 h-7 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center text-sm font-bold">{{ task.execution_order }}</span>
                <h4 class="font-medium">{{ task.task_title }}</h4>
              </div>
              <label class="text-xs text-gray-400 uppercase">Approach</label>
              <textarea v-model="editDraft[i].approach" rows="3" class="w-full text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 p-2 resize-y mb-2" />
              <p class="text-xs text-gray-500">Depends on: {{ task.depends_on?.length ? task.depends_on.join(', ') : 'None' }}</p>
            </div>
          </template>

          <!-- View mode -->
          <template v-else>
            <div
              v-for="task in orderedTasks"
              :key="task.task_id"
              class="border rounded-lg p-4 mb-3"
            >
              <div class="flex items-center gap-3">
                <span class="w-7 h-7 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center text-sm font-bold">{{ task.execution_order }}</span>
                <h4 class="font-medium">{{ task.task_title }}</h4>
              </div>
              <p class="text-sm mt-2">{{ task.approach }}</p>
              <p class="text-xs text-gray-500 mt-2">
                Depends on: {{ task.depends_on?.length ? task.depends_on.join(', ') : 'None' }}
              </p>
            </div>
          </template>
        </section>

        <!-- Test Strategy -->
        <section class="bg-white dark:bg-gray-800 rounded-xl border p-5">
          <h3 class="font-semibold mb-4">Test Strategy</h3>
          <div v-for="(strategy, index) in plan.test_strategy" :key="index" class="mb-4">
            <strong class="text-sm uppercase">{{ strategy.type }}</strong>
            <p class="text-sm">{{ strategy.target }}</p>
            <p v-for="item in strategy.cases" :key="item" class="text-sm text-gray-500">- {{ item }}</p>
          </div>
          <p v-if="!plan.test_strategy?.length" class="text-sm italic text-gray-400">None specified.</p>
        </section>

        <!-- Risks / Deps / Out of scope -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <section class="border rounded-xl p-5">
            <div class="flex items-center justify-between mb-2">
              <h3 class="font-semibold">Risks</h3>
              <button v-if="editingSection !== 'risks'" class="text-xs px-2 py-0.5 rounded border border-gray-200 text-gray-500" @click="startEdit('risks', plan.risks ?? [])">Edit</button>
              <div v-else class="flex gap-1">
                <button class="text-xs px-2 py-0.5 rounded bg-blue-600 text-white" :disabled="saving" @click="saveEdit('risks')">Save</button>
                <button class="text-xs px-2 py-0.5 rounded border border-gray-200 text-gray-500" @click="cancelEdit">✕</button>
              </div>
            </div>
            <template v-if="editingSection === 'risks'">
              <div v-for="(_, i) in editDraft" :key="i" class="flex gap-2 mb-1">
                <input v-model="editDraft[i]" class="flex-1 text-sm border border-gray-300 rounded p-1 bg-white dark:bg-gray-700" />
                <button class="text-xs text-red-500" @click="removeListItem(editDraft, i)">✕</button>
              </div>
              <button class="text-xs text-blue-600 mt-1" @click="addListItem(editDraft)">+ Add</button>
            </template>
            <template v-else>
              <p v-for="item in plan.risks" :key="item" class="text-sm mt-2">- {{ item }}</p>
              <p v-if="!plan.risks?.length" class="text-sm italic text-gray-400">None.</p>
            </template>
          </section>

          <section class="border rounded-xl p-5">
            <h3 class="font-semibold mb-2">Dependencies</h3>
            <p v-for="item in plan.dependencies" :key="item" class="text-sm mt-2">- {{ item }}</p>
            <p v-if="!plan.dependencies?.length" class="text-sm italic text-gray-400">None.</p>
          </section>

          <section class="border rounded-xl p-5">
            <h3 class="font-semibold mb-2">Out of Scope</h3>
            <p v-for="item in plan.out_of_scope" :key="item" class="text-sm mt-2">- {{ item }}</p>
            <p v-if="!plan.out_of_scope?.length" class="text-sm italic text-gray-400">None.</p>
          </section>
        </div>

        <!-- Generate Code CTA -->
        <section
          v-if="data.implementation_plan_status === 'approved'"
          class="bg-green-50 border border-green-200 rounded-xl p-6"
        >
          <div class="flex justify-between items-start flex-wrap gap-4">
            <div>
              <h3 class="font-semibold text-green-800">Ready for Code Generation</h3>
              <p class="text-sm text-green-700 mt-1">
                Requirement and implementation plan are both approved.
                Choose whether to run tests after each task.
              </p>
            </div>
            <div class="flex gap-3 flex-wrap">
              <button
                class="px-5 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700"
                @click="goToExecution(false)"
              >
                Generate Code + Tests &rarr;
              </button>
              <button
                class="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                @click="goToExecution(true)"
              >
                Generate Code Only (skip tests) &rarr;
              </button>
            </div>
          </div>
        </section>
      </template>
    </template>
    </template>

  </div>
</template>
