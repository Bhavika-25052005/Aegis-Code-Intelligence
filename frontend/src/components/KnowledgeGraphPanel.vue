<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import api from '../api/client'

const props = defineProps<{ projectId: string; storyId: string; mode: 'implementation' | 'quality' }>()

// ── State ──────────────────────────────────────────────────────────────────
const loading     = ref(false)
const generating  = ref(false)
const graphStatus = ref<'not_generated' | 'current' | 'stale'>('not_generated')
const graphVersion = ref(0)
const generatedAt  = ref<string | null>(null)
const errorMsg     = ref('')
const successMsg   = ref('')

const searchQuery = ref('')
const depthOption = ref(2)

const allNodes = ref<any[]>([])
const allEdges = ref<any[]>([])
const stats    = ref({ nodes: 0, edges: 0 })

const selectedNode  = ref<any | null>(null)
const impactData    = ref<any | null>(null)
const impactLoading = ref(false)
const showImpact    = ref(false)

const activeTypes = ref<Set<string>>(new Set([
  'file', 'service', 'model', 'api', 'controller', 'frontend', 'task', 'class', 'acceptance_criterion',
]))

const containerRef = ref<HTMLElement | null>(null)
let network: any = null

// ── Node / Edge visual config ──────────────────────────────────────────────
const NODE_COLOR: Record<string, string> = {
  file: '#475569', service: '#2563eb', model: '#7c3aed',
  api: '#059669', controller: '#0891b2', frontend: '#d97706',
  task: '#4f46e5', class: '#be185d', acceptance_criterion: '#0e7490', test: '#65a30d',
}
const EDGE_COLOR: Record<string, string> = {
  IMPORTS: '#94a3b8', DEPENDS_ON: '#ef4444', DEPENDS_ON_TASK: '#ef4444',
  MODIFIES: '#f59e0b', IMPLEMENTS: '#3b82f6', VALIDATED_BY: '#22c55e',
  TESTS: '#84cc16', USES: '#a78bfa', CALLS: '#a78bfa', CONTAINS: '#cbd5e1',
}
const EDGE_WIDTH: Record<string, number> = {
  DEPENDS_ON: 3, DEPENDS_ON_TASK: 3, CALLS: 2.5, USES: 2.5, IMPLEMENTS: 2.5,
}

const NODE_TYPE_OPTIONS = [
  { key: 'api',        label: 'APIs',        color: NODE_COLOR.api        },
  { key: 'service',    label: 'Services',    color: NODE_COLOR.service    },
  { key: 'model',      label: 'Models',      color: NODE_COLOR.model      },
  { key: 'controller', label: 'Controllers', color: NODE_COLOR.controller },
  { key: 'frontend',   label: 'Frontend',    color: NODE_COLOR.frontend   },
  { key: 'file',       label: 'Files',       color: NODE_COLOR.file       },
  { key: 'class',      label: 'Classes',     color: NODE_COLOR.class      },
  { key: 'task',                 label: 'Tasks',    color: NODE_COLOR.task                 },
  { key: 'acceptance_criterion', label: 'Criteria', color: NODE_COLOR.acceptance_criterion },
]

function nodeColor(type: string) { return NODE_COLOR[type] ?? '#475569' }
function nodeTypeLabel(type: string) { return NODE_TYPE_OPTIONS.find(o => o.key === type)?.label ?? type }

const RISK_CLASS: Record<string, string> = {
  LOW:    'text-green-700 bg-green-50 border-green-200',
  MEDIUM: 'text-amber-700 bg-amber-50 border-amber-200',
  HIGH:   'text-red-700 bg-red-50 border-red-200',
}

// ── API ────────────────────────────────────────────────────────────────────
async function loadGraph() {
  loading.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.get(
      `/projects/${props.projectId}/requirements/${props.storyId}/knowledge-graph`,
      { params: { depth: depthOption.value } }
    )
    graphStatus.value = data.status ?? 'not_generated'
    graphVersion.value = data.version ?? 0
    generatedAt.value = data.generated_at ?? null
    allNodes.value = data.nodes ?? []
    allEdges.value = data.edges ?? []
    stats.value = data.stats ?? { nodes: 0, edges: 0 }
    if (data.status !== 'not_generated') await renderGraph()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || 'Failed to load graph'
  } finally {
    loading.value = false
  }
}

async function generateGraph() {
  generating.value = true
  errorMsg.value = ''
  successMsg.value = ''
  try {
    const { data } = await api.post(
      `/projects/${props.projectId}/requirements/${props.storyId}/knowledge-graph/generate`
    )
    successMsg.value = `Graph generated: ${data.node_count} nodes, ${data.edge_count} edges`
    setTimeout(() => { successMsg.value = '' }, 4000)
    await loadGraph()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || 'Generation failed'
  } finally {
    generating.value = false
  }
}

// ── Render with vis-network ────────────────────────────────────────────────
async function renderGraph() {
  await nextTick()
  if (!containerRef.value) return

  // Destroy previous instance
  if (network) { network.destroy(); network = null }

  // Lazy-load vis-network
  let visNet: any
  try {
    const m = await import('vis-network/standalone')
    visNet = m
  } catch {
    errorMsg.value = 'Graph library missing — run: npm install'
    return
  }

  const sq = searchQuery.value.toLowerCase()

  // Filter nodes
  const visibleNodes = allNodes.value.filter(n => {
    if (!activeTypes.value.has(n.type)) return false
    if (sq && !n.label.toLowerCase().includes(sq) && !(n.file || '').toLowerCase().includes(sq)) return false
    return true
  })
  const visibleIds = new Set(visibleNodes.map((n: any) => n.id))

  // Build vis DataSets
  const nodeDataset = new visNet.DataSet(
    visibleNodes.map((n: any) => {
      // Always show short ID-based label for tasks and ACs regardless of what Claude stored
      let displayLabel = n.label
      if (n.type === 'task' || n.type === 'acceptance_criterion') {
        // Extract "T1" from "task:T1" or "AC1" from "ac:AC1"
        const part = n.id.split(':').pop() ?? n.label
        displayLabel = part.toUpperCase()
      }
      return {
      id: n.id,
      label: displayLabel,
      title: n.metadata?.description || n.label,   // tooltip
      color: {
        background: nodeColor(n.type),
        border: nodeColor(n.type),
        highlight: { background: nodeColor(n.type), border: '#f59e0b' },
        hover: { background: nodeColor(n.type), border: '#f59e0b' },
      },
      font: { color: '#ffffff', size: 13, face: 'Inter, ui-sans-serif, sans-serif', bold: true },
      shape: n.type === 'task' ? 'hexagon' : n.type === 'acceptance_criterion' ? 'diamond' : 'box',
      margin: 12,
      borderWidth: 0,
      borderWidthSelected: 3,
      shadow: false,
      // store extra data
      nodeType: n.type,
      file: n.file,
      metadata: n.metadata,
    }
  })
)

  const edgeDataset = new visNet.DataSet(
    allEdges.value
      .filter((e: any) => visibleIds.has(e.source) && visibleIds.has(e.target))
      .map((e: any) => ({
        from: e.source,
        to: e.target,
        label: e.type,
        font: { size: 9, color: '#6b7280', align: 'middle', strokeWidth: 0, background: 'rgba(255,255,255,0.8)' },
        arrows: { to: { enabled: true, scaleFactor: 0.8, type: 'arrow' } },
        color: { color: EDGE_COLOR[e.type] ?? '#374151', highlight: '#f59e0b', hover: '#f59e0b', opacity: 1 },
        width: EDGE_WIDTH[e.type] ?? 1.5,
        smooth: { type: 'dynamic', roundness: 0.3 },
        relationType: e.type,
      }))
  )

  const options = {
    physics: {
      enabled: true,
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {
        gravitationalConstant: -80,
        centralGravity: 0.005,
        springLength: 220,
        springConstant: 0.06,
        damping: 0.5,
        avoidOverlap: 1,
      },
      stabilization: {
        enabled: true,
        iterations: 500,
        updateInterval: 50,
        fit: true,
      },
      minVelocity: 0.75,
    },
    interaction: {
      hover: true,
      tooltipDelay: 200,
      hideEdgesOnDrag: false,
      keyboard: { enabled: false },
    },
    nodes: {
      chosen: true,
    },
    edges: {
      chosen: true,
    },
  }

  network = new visNet.Network(containerRef.value, { nodes: nodeDataset, edges: edgeDataset }, options)

  // Fit once physics stabilises
  network.once('stabilizationIterationsDone', () => {
    network.setOptions({ physics: { enabled: false } })
    network.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } })
  })

  // Node click → detail panel
  network.on('click', (params: any) => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0]
      const found = allNodes.value.find((n: any) => n.id === nodeId)
      if (found) {
        const outgoing = allEdges.value.filter((e: any) => e.source === nodeId)
        const incoming = allEdges.value.filter((e: any) => e.target === nodeId)
        selectedNode.value = { ...found, outgoing, incoming }
        impactData.value = null
        showImpact.value = false
      }
    } else {
      selectedNode.value = null
      impactData.value = null
      showImpact.value = false
    }
  })
}

// ── Impact ─────────────────────────────────────────────────────────────────
async function runImpact() {
  if (!selectedNode.value) return
  impactLoading.value = true
  try {
    const { data } = await api.post(
      `/projects/${props.projectId}/requirements/${props.storyId}/knowledge-graph/impact`,
      null,
      { params: { node_key: selectedNode.value.id, depth: depthOption.value } }
    )
    impactData.value = data
    showImpact.value = true
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || 'Impact analysis failed'
  } finally {
    impactLoading.value = false
  }
}

function clearImpact() { impactData.value = null; showImpact.value = false }

// ── Controls ───────────────────────────────────────────────────────────────
function fitAll()  { network?.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } }) }
function zoomIn()  { network?.moveTo({ scale: (network.getScale() * 1.3) }) }
function zoomOut() { network?.moveTo({ scale: (network.getScale() * 0.75) }) }

function toggleType(key: string) {
  if (activeTypes.value.has(key)) activeTypes.value.delete(key)
  else activeTypes.value.add(key)
  activeTypes.value = new Set(activeTypes.value)
  if (graphStatus.value !== 'not_generated') renderGraph()
}
function toggleAll() {
  activeTypes.value = activeTypes.value.size === NODE_TYPE_OPTIONS.length
    ? new Set() : new Set(NODE_TYPE_OPTIONS.map(t => t.key))
  if (graphStatus.value !== 'not_generated') renderGraph()
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { if (graphStatus.value !== 'not_generated') renderGraph() }, 350)
})

onMounted(loadGraph)
onUnmounted(() => { network?.destroy() })
</script>

<template>
  <div class="flex flex-col" style="min-height:680px">

    <!-- Top bar -->
    <div class="flex items-center justify-between mb-3 flex-shrink-0">
      <div class="flex items-center gap-2.5">
        <span class="font-semibold text-gray-800 dark:text-white text-sm">Knowledge Graph</span>
        <span class="text-xs px-2 py-0.5 rounded-full border font-medium"
          :class="graphStatus==='current' ? 'bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-300 dark:border-green-800'
                : graphStatus==='stale'   ? 'bg-amber-50 text-amber-700 border-amber-200'
                                          : 'bg-gray-100 text-gray-500 border-gray-200 dark:bg-gray-700 dark:text-gray-400'">
          {{ graphStatus === 'current' ? 'Current' : graphStatus === 'stale' ? 'Stale' : 'Not Generated' }}
        </span>
        <span v-if="generatedAt" class="text-xs text-gray-400">
          v{{ graphVersion }} &middot; {{ new Date(generatedAt).toLocaleTimeString() }}
        </span>
      </div>
      <div class="flex gap-2">
        <button v-if="graphStatus !== 'not_generated'" @click="loadGraph" :disabled="loading"
          class="text-xs px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-1 disabled:opacity-50">
          <i :class="loading ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'" class="text-xs"></i> Refresh
        </button>
        <button @click="generateGraph" :disabled="generating || loading"
          class="text-xs px-4 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-1.5 font-medium">
          <i :class="generating ? 'pi pi-spin pi-spinner' : 'pi pi-sparkles'" class="text-xs"></i>
          {{ generating ? 'Claude is analyzing...' : graphStatus === 'not_generated' ? 'Generate with Claude' : 'Regenerate' }}
        </button>
      </div>
    </div>

    <!-- Alerts -->
    <div v-if="errorMsg" class="mb-2 flex items-center gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex-shrink-0">
      <i class="pi pi-exclamation-circle"></i> {{ errorMsg }}
    </div>
    <div v-if="successMsg" class="mb-2 flex items-center gap-2 px-3 py-2 bg-green-50 border border-green-200 rounded-lg text-xs text-green-700 flex-shrink-0">
      <i class="pi pi-check-circle"></i> {{ successMsg }}
    </div>
    <div v-if="graphStatus === 'stale'" class="mb-2 flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-300 rounded-lg text-xs text-amber-700 flex-shrink-0">
      <i class="pi pi-exclamation-triangle"></i>
      Repository changed since this graph was generated.
      <button @click="generateGraph" class="ml-auto font-semibold underline">Regenerate</button>
    </div>

    <!-- Not generated -->
    <div v-if="graphStatus === 'not_generated' && !loading"
      class="flex-1 flex flex-col items-center justify-center text-center bg-gray-50 dark:bg-gray-900/30 rounded-xl border-2 border-dashed border-gray-200 dark:border-gray-700 py-16">
      <div class="w-16 h-16 rounded-2xl bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center mb-4">
        <i class="pi pi-sitemap text-3xl text-indigo-500"></i>
      </div>
      <h4 class="font-semibold text-gray-800 dark:text-white mb-1">Knowledge Graph</h4>
      <p class="text-sm text-gray-500 dark:text-gray-400 max-w-xs mb-6">
        Claude reads your codebase and generates a full architecture graph — nodes, relationships and descriptions.
      </p>
      <button @click="generateGraph" :disabled="generating"
        class="px-6 py-2.5 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 font-medium flex items-center gap-2 disabled:opacity-50 shadow-sm">
        <i :class="generating ? 'pi pi-spin pi-spinner' : 'pi pi-sparkles'"></i>
        {{ generating ? 'Claude is analyzing your code...' : 'Generate with Claude' }}
      </button>
      <p v-if="generating" class="text-xs text-gray-400 mt-3">This takes 15-30 seconds</p>
    </div>

    <!-- Loading -->
    <div v-else-if="loading" class="flex-1 flex items-center justify-center">
      <i class="pi pi-spin pi-spinner text-3xl text-indigo-500"></i>
    </div>

    <!-- Main workspace -->
    <div v-else-if="graphStatus !== 'not_generated'" class="flex gap-3" style="height:600px">

      <!-- LEFT sidebar -->
      <div class="w-48 flex-shrink-0 flex flex-col gap-2.5 overflow-y-auto" style="height:600px">

        <!-- Search -->
        <div class="relative">
          <i class="pi pi-search absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" style="font-size:10px"></i>
          <input v-model="searchQuery" type="text" placeholder="Search nodes..."
            class="w-full pl-7 pr-3 py-1.5 text-xs rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
        </div>

        <!-- Node types -->
        <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-3">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Types</span>
            <button @click="toggleAll" class="text-xs text-indigo-500 hover:underline">
              {{ activeTypes.size === NODE_TYPE_OPTIONS.length ? 'None' : 'All' }}
            </button>
          </div>
          <div class="space-y-0.5">
            <button v-for="opt in NODE_TYPE_OPTIONS" :key="opt.key" @click="toggleType(opt.key)"
              class="w-full flex items-center gap-2 px-1.5 py-1 rounded text-xs transition-opacity"
              :class="activeTypes.has(opt.key) ? '' : 'opacity-30'">
              <span class="w-2.5 h-2.5 rounded-sm flex-shrink-0" :style="{ background: opt.color }"></span>
              <span class="text-gray-700 dark:text-gray-300">{{ opt.label }}</span>
            </button>
          </div>
        </div>

        <!-- Impact depth -->
        <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-3">
          <span class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Impact Depth</span>
          <div class="mt-2 flex gap-1">
            <button v-for="d in [1,2,3]" :key="d" @click="depthOption = d"
              class="flex-1 py-1 text-xs rounded border transition-colors"
              :class="depthOption === d ? 'bg-indigo-600 text-white border-indigo-600' : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'">
              {{ d }}
            </button>
          </div>
          <p class="text-xs text-gray-400 mt-1">hops</p>
        </div>

        <!-- Stats -->
        <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-3 text-xs space-y-1">
          <div class="flex justify-between text-gray-500 dark:text-gray-400">
            <span>Nodes</span><span class="font-semibold text-gray-700 dark:text-gray-200">{{ stats.nodes }}</span>
          </div>
          <div class="flex justify-between text-gray-500 dark:text-gray-400">
            <span>Edges</span><span class="font-semibold text-gray-700 dark:text-gray-200">{{ stats.edges }}</span>
          </div>
        </div>

        <!-- Edge legend -->
        <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-3">
          <span class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Edges</span>
          <div class="mt-2 space-y-1">
            <div v-for="(color, type) in EDGE_COLOR" :key="type" class="flex items-center gap-1.5">
              <div class="flex-shrink-0 rounded" :style="{ width:'18px', height:'2px', background: color }"></div>
              <span class="text-xs text-gray-500 dark:text-gray-400">{{ String(type).replace(/_/g,' ') }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- CENTER canvas -->
      <div class="flex-1 relative rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden" style="height:600px">
        <div ref="containerRef" style="width:100%;height:100%"></div>

        <!-- Controls -->
        <div class="absolute top-3 right-3 flex flex-col gap-1 z-10">
          <button @click="zoomIn"  class="w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-200 flex items-center justify-center shadow-sm font-bold text-base">+</button>
          <button @click="zoomOut" class="w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-200 flex items-center justify-center shadow-sm font-bold text-base">-</button>
          <button @click="fitAll"  title="Fit all" class="w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-200 flex items-center justify-center shadow-sm">
            <i class="pi pi-expand" style="font-size:11px"></i>
          </button>
        </div>

        <div class="absolute bottom-2 left-3 text-xs text-gray-400 pointer-events-none select-none">
          Click node for details &middot; Scroll to zoom &middot; Drag to pan
        </div>
      </div>

      <!-- RIGHT detail panel -->
      <Transition
        enter-active-class="transition-all duration-200 ease-out"
        enter-from-class="opacity-0 translate-x-3"
        enter-to-class="opacity-100 translate-x-0"
        leave-active-class="transition-all duration-150 ease-in"
        leave-from-class="opacity-100 translate-x-0"
        leave-to-class="opacity-0 translate-x-3">
        <div v-if="selectedNode" class="w-68 flex-shrink-0 flex flex-col gap-2.5 overflow-y-auto" style="width:264px;height:600px">

          <!-- Node header -->
          <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
            <div class="flex items-start justify-between gap-2 mb-2">
              <span class="text-xs font-bold px-2 py-0.5 rounded text-white" :style="{ background: nodeColor(selectedNode.type) }">
                {{ nodeTypeLabel(selectedNode.type) }}
              </span>
              <button @click="selectedNode = null; clearImpact()" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 flex-shrink-0">
                <i class="pi pi-times" style="font-size:11px"></i>
              </button>
            </div>
            <h4 class="font-bold text-gray-900 dark:text-white text-base mt-2 leading-tight">{{ selectedNode.label }}</h4>
            <p v-if="selectedNode.file" class="text-xs text-blue-500 font-mono mt-1 break-all">{{ selectedNode.file }}</p>
            <p v-if="selectedNode.metadata?.description" class="text-sm text-gray-600 dark:text-gray-300 mt-3 leading-relaxed border-t border-gray-100 dark:border-gray-700 pt-3">
              {{ selectedNode.metadata.description }}
            </p>
          </div>

          <!-- Connections -->
          <div v-if="selectedNode.outgoing?.length || selectedNode.incoming?.length"
            class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
            <div v-if="selectedNode.outgoing?.length" class="mb-3">
              <p class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Depends On</p>
              <div class="space-y-1.5">
                <div v-for="e in selectedNode.outgoing.slice(0,6)" :key="e.target+e.type" class="flex items-center gap-2 text-xs">
                  <div class="w-2 h-2 rounded-sm flex-shrink-0" :style="{ background: nodeColor((allNodes.find((n:any)=>n.id===e.target))?.type??'file') }"></div>
                  <span class="text-gray-700 dark:text-gray-300 truncate flex-1">{{ (allNodes.find((n:any)=>n.id===e.target))?.label ?? e.target.split(':').pop() }}</span>
                  <span class="text-gray-400 flex-shrink-0 text-xs bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded">{{ e.type }}</span>
                </div>
              </div>
            </div>
            <div v-if="selectedNode.incoming?.length">
              <p class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Used By</p>
              <div class="space-y-1.5">
                <div v-for="e in selectedNode.incoming.slice(0,6)" :key="e.source+e.type" class="flex items-center gap-2 text-xs">
                  <div class="w-2 h-2 rounded-sm flex-shrink-0" :style="{ background: nodeColor((allNodes.find((n:any)=>n.id===e.source))?.type??'file') }"></div>
                  <span class="text-gray-700 dark:text-gray-300 truncate flex-1">{{ (allNodes.find((n:any)=>n.id===e.source))?.label ?? e.source.split(':').pop() }}</span>
                  <span class="text-gray-400 flex-shrink-0 text-xs bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded">{{ e.type }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Impact -->
          <div v-if="!showImpact" class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
            <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">Traverse the graph to find all files, tasks and ACs affected by changing this component.</p>
            <button @click="runImpact" :disabled="impactLoading"
              class="w-full flex items-center justify-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-xs font-semibold disabled:opacity-50">
              <i :class="impactLoading ? 'pi pi-spin pi-spinner' : 'pi pi-bolt'"></i>
              {{ impactLoading ? 'Analyzing...' : 'Analyze Impact' }}
            </button>
          </div>

          <!-- Impact result -->
          <div v-if="showImpact && impactData" class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
            <div class="flex items-center justify-between mb-3">
              <p class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Impact</p>
              <button @click="clearImpact" class="text-xs text-gray-400 hover:text-gray-600">Clear</button>
            </div>
            <div class="flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-bold mb-3"
              :class="RISK_CLASS[impactData.risk] ?? 'text-gray-600 bg-gray-50 border-gray-200'">
              <i :class="impactData.risk==='HIGH' ? 'pi pi-exclamation-circle' : impactData.risk==='MEDIUM' ? 'pi pi-exclamation-triangle' : 'pi pi-check-circle'"></i>
              {{ impactData.risk }} RISK
            </div>
            <div class="grid grid-cols-2 gap-1.5 mb-3">
              <div v-for="(count, label) in { Files: impactData.impact_counts?.files, Tasks: impactData.impact_counts?.tasks, ACs: impactData.impact_counts?.acs, Tests: impactData.impact_counts?.tests }"
                :key="label" class="text-center py-2 rounded-lg bg-gray-50 dark:bg-gray-700/50">
                <div class="text-base font-bold text-gray-800 dark:text-white">{{ count ?? 0 }}</div>
                <div class="text-xs text-gray-500">{{ label }}</div>
              </div>
            </div>
            <div v-if="impactData.affected_files?.length">
              <p class="text-xs font-medium text-gray-500 mb-1">Affected</p>
              <div class="space-y-0.5">
                <div v-for="f in impactData.affected_files.slice(0,5)" :key="f.key" class="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300">
                  <div class="w-2 h-2 rounded-sm flex-shrink-0" :style="{ background: nodeColor(f.type) }"></div>
                  <span class="truncate">{{ f.label }}</span>
                </div>
                <p v-if="impactData.affected_files.length > 5" class="text-xs text-gray-400">+{{ impactData.affected_files.length - 5 }} more</p>
              </div>
            </div>
          </div>

        </div>
      </Transition>

    </div>
  </div>
</template>
