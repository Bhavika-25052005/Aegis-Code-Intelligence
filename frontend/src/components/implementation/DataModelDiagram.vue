<script setup lang="ts">
import { computed } from 'vue'
import { VueFlow, Position } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import type { DataModel } from '../../types'
import type { Node, Edge } from '@vue-flow/core'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

const props = defineProps<{
  model: DataModel
}>()

const CARD_BASE_HEIGHT = 60
const FIELD_HEIGHT = 22
const COLS = 3
const X_GAP = 340
const Y_GAP = 80

function getRelEdgeColor(type: string): string {
  switch (type) {
    case 'one_to_many': return '#3b82f6'
    case 'many_to_one': return '#10b981'
    case 'many_to_many': return '#8b5cf6'
    case 'one_to_one': return '#f59e0b'
    default: return '#6b7280'
  }
}

function formatRelLabel(rel: { type: string; foreign_key: string }): string {
  const typeLabel = rel.type.replace(/_/g, ' ')
  return `${typeLabel} (${rel.foreign_key})`
}

const nodes = computed<Node[]>(() => {
  return props.model.entities.map((entity, index) => {
    const col = index % COLS
    const prevEntitiesInCol = props.model.entities
      .slice(0, index)
      .filter((_, i) => i % COLS === col)
    const yOffset = prevEntitiesInCol.reduce(
      (sum, e) => sum + CARD_BASE_HEIGHT + e.fields.length * FIELD_HEIGHT + Y_GAP,
      0,
    )

    return {
      id: entity.name,
      position: { x: col * X_GAP + 50, y: yOffset + 50 },
      data: {
        label: entity.name,
        entity,
      },
      type: 'entity',
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    }
  })
})

const edges = computed<Edge[]>(() => {
  const result: Edge[] = []
  for (const entity of props.model.entities) {
    for (const rel of entity.relationships) {
      const targetExists = props.model.entities.some(e => e.name === rel.target_entity)
      if (!targetExists) continue

      result.push({
        id: `${entity.name}-${rel.target_entity}-${rel.foreign_key}`,
        source: entity.name,
        target: rel.target_entity,
        label: formatRelLabel(rel),
        animated: rel.type === 'many_to_many',
        style: { stroke: getRelEdgeColor(rel.type), strokeWidth: 2 },
        labelStyle: { fontSize: '10px', fontWeight: 500 },
        labelBgStyle: { fill: '#f8fafc', fillOpacity: 0.9 },
      })
    }
  }
  return result
})

const flowHeight = computed(() => {
  const rows = Math.ceil(props.model.entities.length / COLS)
  const avgFields = props.model.entities.reduce((s, e) => s + e.fields.length, 0) / (props.model.entities.length || 1)
  return Math.max(400, rows * (CARD_BASE_HEIGHT + avgFields * FIELD_HEIGHT + Y_GAP) + 100)
})
</script>

<template>
  <div class="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden" :style="{ height: flowHeight + 'px' }">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :default-viewport="{ x: 0, y: 0, zoom: 0.85 }"
      :min-zoom="0.3"
      :max-zoom="2"
      fit-view-on-init
      class="w-full h-full"
    >
      <Background :gap="20" :size="1" />
      <Controls position="top-right" />

      <template #node-entity="{ data }">
        <div class="bg-white dark:bg-gray-800 border-2 border-gray-300 dark:border-gray-600 rounded-lg shadow-md min-w-[240px] overflow-hidden">
          <!-- Entity header -->
          <div class="px-3 py-2 bg-gradient-to-r from-blue-500 to-blue-600 dark:from-blue-700 dark:to-blue-800">
            <div class="flex items-center justify-between">
              <span class="font-semibold text-white text-sm">{{ data.entity.name }}</span>
              <span class="text-xs bg-white/20 text-white px-1.5 py-0.5 rounded">
                {{ data.entity.type }}
              </span>
            </div>
          </div>

          <!-- Fields list -->
          <div class="px-2 py-1.5 max-h-[200px] overflow-y-auto">
            <div
              v-for="field in data.entity.fields"
              :key="field.name"
              class="flex items-center gap-1.5 py-0.5 text-xs"
            >
              <span v-if="field.primary_key" class="text-amber-500 w-3 text-center" title="Primary Key">🔑</span>
              <span v-else-if="field.indexed" class="text-purple-400 w-3 text-center" title="Indexed">⚡</span>
              <span v-else class="w-3" />
              <span class="font-mono text-gray-800 dark:text-gray-200 flex-1">{{ field.name }}</span>
              <span class="font-mono text-blue-500 dark:text-blue-400 text-[10px]">{{ field.type }}</span>
              <span v-if="!field.nullable" class="text-red-400 text-[10px]" title="NOT NULL">!</span>
            </div>
          </div>

          <!-- Relationship badges -->
          <div v-if="data.entity.relationships.length" class="px-2 py-1.5 border-t border-gray-100 dark:border-gray-700">
            <div class="flex flex-wrap gap-1">
              <span
                v-for="rel in data.entity.relationships"
                :key="rel.target_entity"
                class="text-[10px] px-1.5 py-0.5 rounded"
                :style="{ backgroundColor: getRelEdgeColor(rel.type) + '20', color: getRelEdgeColor(rel.type) }"
              >
                → {{ rel.target_entity }}
              </span>
            </div>
          </div>
        </div>
      </template>
    </VueFlow>
  </div>

  <!-- Legend -->
  <div class="mt-3 flex flex-wrap items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
    <span class="font-medium">Relationships:</span>
    <span class="flex items-center gap-1">
      <span class="w-3 h-0.5 bg-blue-500 inline-block rounded" /> one to many
    </span>
    <span class="flex items-center gap-1">
      <span class="w-3 h-0.5 bg-green-500 inline-block rounded" /> many to one
    </span>
    <span class="flex items-center gap-1">
      <span class="w-3 h-0.5 bg-purple-500 inline-block rounded" /> many to many
    </span>
    <span class="flex items-center gap-1">
      <span class="w-3 h-0.5 bg-amber-500 inline-block rounded" /> one to one
    </span>
  </div>
</template>
