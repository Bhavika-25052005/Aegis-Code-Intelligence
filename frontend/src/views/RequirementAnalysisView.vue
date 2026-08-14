<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import api from '../api/client'

interface RequirementAnalysis {
  summary: string
  acceptance_criteria: string[]
  functional_rules: string[]
  edge_cases: string[]
  assumptions: string[]
  dependencies: string[]
  ambiguities: string[]
  risks: string[]
  questions: string[]
  risk_level: 'low' | 'medium' | 'high' | 'critical'
}

interface AnalysisResponse {
  project_id: string
  feature_id: string
  feature_title: string
  user_story_id: string
  user_story_title: string
  user_story_description: string
  original_acceptance_criteria: string
  analysis: RequirementAnalysis | null
  status: 'not_analyzed' | 'draft' | 'approved'
  approved_at: string | null
}

type SectionKey = keyof Omit<RequirementAnalysis, 'summary' | 'risk_level'>

const route = useRoute()
const router = useRouter()

const projectId = route.params.id as string
const storyId = route.params.storyId as string

const data = ref<AnalysisResponse | null>(null)
const loading = ref(true)
const analyzing = ref(false)
const approving = ref(false)
const error = ref('')

// Edit state - which card is being edited and its draft content
const editingSection = ref<SectionKey | 'summary' | null>(null)
const editDraft = ref<string[]>([])
const editSummaryDraft = ref('')
const saving = ref(false)

const SECTIONS: [string, SectionKey][] = [
  ['Acceptance Criteria', 'acceptance_criteria'],
  ['Functional Rules', 'functional_rules'],
  ['Edge Cases', 'edge_cases'],
  ['Assumptions', 'assumptions'],
  ['Dependencies', 'dependencies'],
  ['Ambiguities', 'ambiguities'],
  ['Risks', 'risks'],
  ['Questions Before Coding', 'questions'],
]

const riskClass = computed(() => {
  const risk = data.value?.analysis?.risk_level
  switch (risk) {
    case 'critical': return 'bg-red-100 text-red-700'
    case 'high': return 'bg-orange-100 text-orange-700'
    case 'medium': return 'bg-yellow-100 text-yellow-700'
    case 'low': return 'bg-green-100 text-green-700'
    default: return 'bg-gray-100 text-gray-700'
  }
})

async function loadAnalysis() {
  loading.value = true
  error.value = ''
  try {
    const response = await api.get(`/projects/${projectId}/requirements/${storyId}`)
    data.value = response.data
  } catch (err: unknown) {
    error.value = axios.isAxiosError(err)
      ? (err.response?.data?.detail || err.message)
      : 'Unable to load requirement.'
  } finally {
    loading.value = false
  }
}

async function analyze() {
  analyzing.value = true
  error.value = ''
  try {
    const response = await api.post(`/projects/${projectId}/requirements/${storyId}/analyze`)
    data.value = response.data
    editingSection.value = null
  } catch (err: unknown) {
    error.value = axios.isAxiosError(err)
      ? (err.response?.data?.detail || err.message)
      : 'Requirement analysis failed.'
  } finally {
    analyzing.value = false
  }
}

async function approve() {
  approving.value = true
  error.value = ''
  try {
    const response = await api.post(`/projects/${projectId}/requirements/${storyId}/approve`)
    data.value = response.data
  } catch (err: unknown) {
    if (axios.isAxiosError(err)) error.value = err.response?.data?.detail || err.message
  } finally {
    approving.value = false
  }
}

async function reopen() {
  error.value = ''
  try {
    const response = await api.post(`/projects/${projectId}/requirements/${storyId}/reopen`)
    data.value = response.data
  } catch (err: unknown) {
    if (axios.isAxiosError(err)) error.value = err.response?.data?.detail || err.message
  }
}

// ── Edit helpers ──────────────────────────────────────────────────────────────

function startEditSection(key: SectionKey) {
  editingSection.value = key
  editDraft.value = [...(data.value!.analysis![key] as string[])]
}

function startEditSummary() {
  editingSection.value = 'summary'
  editSummaryDraft.value = data.value!.analysis!.summary
}

function cancelEdit() {
  editingSection.value = null
}

function addItem() {
  editDraft.value.push('')
}

function removeItem(index: number) {
  editDraft.value.splice(index, 1)
}

async function saveSection(key: SectionKey | 'summary') {
  saving.value = true
  error.value = ''
  try {
    const payload = key === 'summary'
      ? { summary: editSummaryDraft.value }
      : { [key]: editDraft.value.filter(s => s.trim()) }
    const response = await api.patch(
      `/projects/${projectId}/requirements/${storyId}`,
      payload,
    )
    data.value = response.data
    editingSection.value = null
  } catch (err: unknown) {
    error.value = axios.isAxiosError(err)
      ? (err.response?.data?.detail || err.message)
      : 'Save failed.'
  } finally {
    saving.value = false
  }
}

function goBack() {
  router.push(`/projects/${projectId}/backlog`)
}

onMounted(loadAnalysis)
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-start justify-between gap-4">
      <div>
        <button class="text-sm text-blue-600 mb-3" @click="goBack">
          &larr; Back to Backlog
        </button>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          Requirement Intelligence
        </h1>
        <p class="text-sm text-gray-500 mt-1">
          Understand the requirement before implementation.
        </p>
      </div>
      <div class="flex gap-3 flex-wrap justify-end">
        <button
          v-if="data?.status === 'approved'"
          class="px-5 py-2.5 rounded-lg bg-purple-600 hover:bg-purple-700 text-white"
          @click="router.push(`/projects/${projectId}/implementation/${storyId}`)"
        >
          Continue to Implementation Plan &rarr;
        </button>
        <button
          class="px-5 py-2.5 rounded-lg bg-blue-600 text-white disabled:opacity-50"
          :disabled="analyzing"
          @click="analyze"
        >
          {{ analyzing ? 'Analyzing...' : data?.analysis ? 'Regenerate Analysis' : 'Analyze Requirement' }}
        </button>
      </div>
    </div>

    <!-- Error banner -->
    <div v-if="error" class="p-4 rounded-lg bg-red-50 text-red-700 border border-red-200">
      {{ error }}
    </div>

    <div v-if="loading" class="py-16 text-center text-gray-500">
      Loading requirement...
    </div>

    <template v-else-if="data">
      <!-- Story context card -->
      <section class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <p class="text-xs uppercase text-gray-400">Feature</p>
        <p class="font-medium text-purple-600">{{ data.feature_title }}</p>
        <p class="text-xs uppercase text-gray-400 mt-4">User Story</p>
        <h2 class="text-lg font-semibold text-gray-900 dark:text-white">{{ data.user_story_title }}</h2>
        <p class="mt-2 text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap">{{ data.user_story_description }}</p>
        <div v-if="data.original_acceptance_criteria" class="mt-4">
          <p class="text-xs uppercase text-gray-400">Imported Acceptance Criteria</p>
          <p class="mt-1 text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap">{{ data.original_acceptance_criteria }}</p>
        </div>
      </section>

      <!-- No analysis placeholder -->
      <section
        v-if="!data.analysis"
        class="bg-white dark:bg-gray-800 rounded-xl border border-dashed border-gray-300 dark:border-gray-600 p-10 text-center"
      >
        <h3 class="font-semibold text-gray-800 dark:text-white">No AI analysis yet</h3>
        <p class="text-sm text-gray-500 mt-2">
          Click Analyze Requirement to generate acceptance criteria, edge cases, assumptions, risks and questions.
        </p>
      </section>

      <template v-else>
        <!-- Status / approval bar -->
        <section class="flex items-center justify-between bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div>
            <div class="flex items-center gap-3">
              <span class="font-semibold text-gray-900 dark:text-white">Analysis</span>
              <span
                class="text-xs px-3 py-1 rounded-full"
                :class="data.status === 'approved' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'"
              >{{ data.status }}</span>
              <span class="text-xs px-3 py-1 rounded-full" :class="riskClass">
                {{ data.analysis.risk_level }} risk
              </span>
            </div>
            <p class="text-sm text-gray-500 mt-2">Editing or regenerating requires approval again.</p>
          </div>
          <button
            v-if="data.status !== 'approved'"
            class="px-5 py-2.5 rounded-lg bg-green-600 text-white disabled:opacity-50"
            :disabled="approving"
            @click="approve"
          >{{ approving ? 'Approving...' : 'Approve Requirement' }}</button>
          <div v-else class="flex items-center gap-3">
            <span class="text-green-600 font-medium">&#10003; Approved for Implementation</span>
            <button class="text-sm text-gray-500 underline" @click="reopen">Reopen</button>
          </div>
        </section>

        <!-- Summary card -->
        <section class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-semibold text-gray-900 dark:text-white">Summary</h3>
            <button
              v-if="editingSection !== 'summary'"
              class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-gray-500 hover:border-blue-300 hover:text-blue-600"
              @click="startEditSummary"
            >Edit</button>
            <div v-else class="flex gap-2">
              <button
                class="text-xs px-3 py-1 rounded-lg bg-blue-600 text-white disabled:opacity-50"
                :disabled="saving"
                @click="saveSection('summary')"
              >{{ saving ? 'Saving…' : 'Save' }}</button>
              <button class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-gray-500" @click="cancelEdit">Cancel</button>
            </div>
          </div>
          <textarea
            v-if="editingSection === 'summary'"
            v-model="editSummaryDraft"
            rows="4"
            class="w-full text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 p-3 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y"
          />
          <p v-else class="text-sm text-gray-600 dark:text-gray-300 leading-6">{{ data.analysis.summary }}</p>
        </section>

        <!-- List section cards -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <section
            v-for="[label, key] in SECTIONS"
            :key="key"
            class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5"
          >
            <!-- Card header -->
            <div class="flex items-center justify-between mb-4">
              <h3 class="font-semibold text-gray-900 dark:text-white">{{ label }}</h3>
              <button
                v-if="editingSection !== key"
                class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-gray-500 hover:border-blue-300 hover:text-blue-600"
                @click="startEditSection(key)"
              >Edit</button>
              <div v-else class="flex gap-2">
                <button
                  class="text-xs px-3 py-1 rounded-lg bg-blue-600 text-white disabled:opacity-50"
                  :disabled="saving"
                  @click="saveSection(key)"
                >{{ saving ? 'Saving…' : 'Save' }}</button>
                <button class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-gray-500" @click="cancelEdit">Cancel</button>
              </div>
            </div>

            <!-- View mode -->
            <template v-if="editingSection !== key">
              <ul v-if="(data.analysis![key] as string[]).length" class="space-y-3">
                <li
                  v-for="(item, i) in data.analysis![key] as string[]"
                  :key="i"
                  class="text-sm text-gray-600 dark:text-gray-300 flex gap-2"
                >
                  <span>&bull;</span><span>{{ item }}</span>
                </li>
              </ul>
              <p v-else class="text-sm italic text-gray-400">None identified.</p>
            </template>

            <!-- Edit mode -->
            <template v-else>
              <div class="space-y-2">
                <div
                  v-for="(_, i) in editDraft"
                  :key="i"
                  class="flex gap-2 items-start"
                >
                  <textarea
                    v-model="editDraft[i]"
                    rows="2"
                    class="flex-1 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 p-2 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y"
                  />
                  <button
                    class="mt-1 text-xs px-2 py-1 rounded border border-red-200 text-red-500 hover:bg-red-50"
                    @click="removeItem(i)"
                  >&#x2715;</button>
                </div>
                <button
                  class="mt-2 text-xs px-3 py-1.5 rounded-lg border border-dashed border-blue-300 text-blue-600 hover:bg-blue-50 w-full"
                  @click="addItem"
                >+ Add item</button>
              </div>
            </template>
          </section>
        </div>
      </template>
    </template>
  </div>
</template>
