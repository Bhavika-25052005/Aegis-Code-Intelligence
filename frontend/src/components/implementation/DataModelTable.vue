<script setup lang="ts">
import { ref } from 'vue'
import type { DataModel } from '../../types'

const props = defineProps<{
  model: DataModel
  readonly: boolean
}>()

defineEmits<{
  (e: 'update', model: DataModel): void
}>()

const expandedEntities = ref<Set<string>>(new Set())

function toggleEntity(name: string) {
  if (expandedEntities.value.has(name)) {
    expandedEntities.value.delete(name)
  } else {
    expandedEntities.value.add(name)
  }
}

function getRelTypeColor(type: string): string {
  switch (type) {
    case 'one_to_many': return 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300'
    case 'many_to_one': return 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
    case 'many_to_many': return 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300'
    case 'one_to_one': return 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300'
    default: return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
  }
}

function formatRelType(type: string): string {
  return type.replace(/_/g, ' ')
}

function getChangeAction(entityName: string): string | null {
  const entry = props.model.change_log?.find(c => c.entity === entityName)
  return entry?.action ?? null
}

function getChangeActionColor(action: string): string {
  switch (action) {
    case 'created': return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300'
    case 'modified': return 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300'
    case 'removed': return 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300'
    default: return 'bg-gray-100 text-gray-700'
  }
}
</script>

<template>
  <div class="space-y-3">
    <!-- Summary -->
    <p v-if="model.summary" class="text-sm text-gray-600 dark:text-gray-400 italic">
      {{ model.summary }}
    </p>

    <!-- Entities table -->
    <div class="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
            <th class="text-left px-4 py-2.5 font-semibold text-gray-700 dark:text-gray-200">Entity</th>
            <th class="text-left px-4 py-2.5 font-semibold text-gray-700 dark:text-gray-200">Type</th>
            <th class="text-center px-4 py-2.5 font-semibold text-gray-700 dark:text-gray-200">Fields</th>
            <th class="text-center px-4 py-2.5 font-semibold text-gray-700 dark:text-gray-200">Relations</th>
            <th class="text-left px-4 py-2.5 font-semibold text-gray-700 dark:text-gray-200">Description</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="entity in model.entities" :key="entity.name">
            <!-- Entity row -->
            <tr
              class="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer transition-colors"
              @click="toggleEntity(entity.name)"
            >
              <td class="px-4 py-2.5">
                <div class="flex items-center gap-2">
                  <i
                    class="pi text-xs text-gray-400 transition-transform duration-200"
                    :class="expandedEntities.has(entity.name) ? 'pi-chevron-down' : 'pi-chevron-right'"
                  />
                  <span class="font-medium text-gray-900 dark:text-gray-100">{{ entity.name }}</span>
                  <span
                    v-if="getChangeAction(entity.name)"
                    class="text-xs px-1.5 py-0.5 rounded font-medium uppercase"
                    :class="getChangeActionColor(getChangeAction(entity.name)!)"
                  >
                    {{ getChangeAction(entity.name) }}
                  </span>
                </div>
              </td>
              <td class="px-4 py-2.5">
                <span class="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                  {{ entity.type }}
                </span>
              </td>
              <td class="px-4 py-2.5 text-center text-gray-600 dark:text-gray-400">
                {{ entity.fields.length }}
              </td>
              <td class="px-4 py-2.5 text-center text-gray-600 dark:text-gray-400">
                {{ entity.relationships.length }}
              </td>
              <td class="px-4 py-2.5 text-gray-600 dark:text-gray-400 max-w-xs truncate">
                {{ entity.description }}
              </td>
            </tr>

            <!-- Expanded detail -->
            <tr v-if="expandedEntities.has(entity.name)">
              <td colspan="5" class="px-4 py-4 bg-gray-50/50 dark:bg-gray-800/30">
                <div class="space-y-4 ml-6">
                  <!-- Fields sub-table -->
                  <div>
                    <h4 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
                      Fields
                    </h4>
                    <div class="border border-gray-200 dark:border-gray-600 rounded overflow-hidden">
                      <table class="w-full text-xs">
                        <thead>
                          <tr class="bg-gray-100 dark:bg-gray-700">
                            <th class="text-left px-3 py-1.5 font-medium">Name</th>
                            <th class="text-left px-3 py-1.5 font-medium">Type</th>
                            <th class="text-center px-3 py-1.5 font-medium">PK</th>
                            <th class="text-center px-3 py-1.5 font-medium">Nullable</th>
                            <th class="text-center px-3 py-1.5 font-medium">Unique</th>
                            <th class="text-center px-3 py-1.5 font-medium">Indexed</th>
                            <th class="text-left px-3 py-1.5 font-medium">Default</th>
                            <th class="text-left px-3 py-1.5 font-medium">Description</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr
                            v-for="field in entity.fields"
                            :key="field.name"
                            class="border-t border-gray-100 dark:border-gray-600"
                          >
                            <td class="px-3 py-1.5 font-mono font-medium text-gray-900 dark:text-gray-100">
                              {{ field.name }}
                            </td>
                            <td class="px-3 py-1.5 font-mono text-blue-600 dark:text-blue-400">
                              {{ field.type }}
                            </td>
                            <td class="px-3 py-1.5 text-center">
                              <span v-if="field.primary_key" class="text-amber-500">●</span>
                              <span v-else class="text-gray-300">—</span>
                            </td>
                            <td class="px-3 py-1.5 text-center">
                              <span :class="field.nullable ? 'text-green-500' : 'text-red-400'">
                                {{ field.nullable ? '✓' : '✗' }}
                              </span>
                            </td>
                            <td class="px-3 py-1.5 text-center">
                              <span v-if="field.unique" class="text-blue-500">●</span>
                              <span v-else class="text-gray-300">—</span>
                            </td>
                            <td class="px-3 py-1.5 text-center">
                              <span v-if="field.indexed" class="text-purple-500">●</span>
                              <span v-else class="text-gray-300">—</span>
                            </td>
                            <td class="px-3 py-1.5 font-mono text-gray-500 dark:text-gray-400">
                              {{ field.default ?? '—' }}
                            </td>
                            <td class="px-3 py-1.5 text-gray-600 dark:text-gray-400">
                              {{ field.description }}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <!-- Relationships -->
                  <div v-if="entity.relationships.length">
                    <h4 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
                      Relationships
                    </h4>
                    <div class="flex flex-wrap gap-2">
                      <div
                        v-for="(rel, i) in entity.relationships"
                        :key="i"
                        class="flex items-center gap-2 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 text-xs"
                      >
                        <span class="font-medium text-gray-900 dark:text-gray-100">{{ entity.name }}</span>
                        <span class="px-1.5 py-0.5 rounded" :class="getRelTypeColor(rel.type)">
                          {{ formatRelType(rel.type) }}
                        </span>
                        <span class="font-medium text-gray-900 dark:text-gray-100">{{ rel.target_entity }}</span>
                        <span class="text-gray-400">(FK: {{ rel.foreign_key }}, {{ rel.on_delete }})</span>
                      </div>
                    </div>
                  </div>

                  <!-- Indexes -->
                  <div v-if="entity.indexes.length">
                    <h4 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
                      Indexes
                    </h4>
                    <div class="flex flex-wrap gap-2">
                      <span
                        v-for="idx in entity.indexes"
                        :key="idx.name"
                        class="text-xs px-2 py-1 rounded border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300"
                      >
                        {{ idx.name }} ({{ idx.fields.join(', ') }})
                        <span v-if="idx.unique" class="text-amber-500 ml-1">UNIQUE</span>
                      </span>
                    </div>
                  </div>

                  <!-- Constraints -->
                  <div v-if="entity.constraints.length">
                    <h4 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
                      Constraints
                    </h4>
                    <ul class="list-disc list-inside text-xs text-gray-600 dark:text-gray-400 space-y-0.5">
                      <li v-for="(c, i) in entity.constraints" :key="i">{{ c }}</li>
                    </ul>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- Enums section -->
    <div v-if="model.enums?.length" class="mt-4">
      <h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Enums</h4>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div
          v-for="enumDef in model.enums"
          :key="enumDef.name"
          class="border border-gray-200 dark:border-gray-700 rounded-lg p-3"
        >
          <div class="font-medium text-sm text-gray-900 dark:text-gray-100">{{ enumDef.name }}</div>
          <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">{{ enumDef.description }}</div>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="val in enumDef.values"
              :key="val.name"
              class="text-xs px-2 py-0.5 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 rounded"
              :title="val.description"
            >
              {{ val.name }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Change log (for enhancements) -->
    <div v-if="model.change_log?.length" class="mt-4">
      <h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Change Log</h4>
      <div class="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        <table class="w-full text-xs">
          <thead>
            <tr class="bg-gray-50 dark:bg-gray-800">
              <th class="text-left px-3 py-2 font-medium">Entity</th>
              <th class="text-left px-3 py-2 font-medium">Action</th>
              <th class="text-left px-3 py-2 font-medium">Reason</th>
              <th class="text-left px-3 py-2 font-medium">Fields Changed</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(change, i) in model.change_log"
              :key="i"
              class="border-t border-gray-100 dark:border-gray-700"
            >
              <td class="px-3 py-2 font-medium">{{ change.entity }}</td>
              <td class="px-3 py-2">
                <span class="px-1.5 py-0.5 rounded text-xs uppercase" :class="getChangeActionColor(change.action)">
                  {{ change.action }}
                </span>
              </td>
              <td class="px-3 py-2 text-gray-600 dark:text-gray-400">{{ change.reason }}</td>
              <td class="px-3 py-2 text-gray-500 font-mono">
                {{ change.fields_changed?.join(', ') || '—' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
