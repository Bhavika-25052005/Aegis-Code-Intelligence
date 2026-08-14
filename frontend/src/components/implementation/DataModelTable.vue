<script setup lang="ts">
import { ref } from 'vue'
import type { DataModel, DataModelField } from '../../types'

const props = defineProps<{ model: DataModel; readonly?: boolean }>()
const emit = defineEmits<{ (e: 'update', model: DataModel): void }>()

const expandedEntities = ref<Set<string>>(new Set())
const editingField = ref<{ entity: string; fieldIdx: number } | null>(null)

function toggleEntity(name: string) {
  if (expandedEntities.value.has(name)) expandedEntities.value.delete(name)
  else expandedEntities.value.add(name)
  expandedEntities.value = new Set(expandedEntities.value)
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function cloneModel(): DataModel {
  return JSON.parse(JSON.stringify(props.model))
}

function getRelTypeColor(type: string): string {
  const map: Record<string, string> = {
    one_to_many: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    many_to_one: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
    many_to_many: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
    one_to_one: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  }
  return map[type] ?? 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
}

function getChangeAction(entityName: string): string | null {
  return props.model.change_log?.find(c => c.entity === entityName)?.action ?? null
}
function getChangeColor(action: string): string {
  const map: Record<string, string> = {
    created: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
    modified: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
    removed: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  }
  return map[action] ?? 'bg-gray-100 text-gray-700'
}

// ── Entity editing ────────────────────────────────────────────────────────────
function addEntity() {
  const m = cloneModel()
  const name = `NewEntity${m.entities.length + 1}`
  m.entities.push({
    name, description: '', type: 'table',
    fields: [{ name: 'id', type: 'UUID', primary_key: true, nullable: false, unique: true, indexed: true, default: null, description: 'Primary key' }],
    relationships: [], indexes: [], constraints: [],
  })
  expandedEntities.value = new Set([...expandedEntities.value, name])
  emit('update', m)
}

function removeEntity(idx: number) {
  const m = cloneModel()
  m.entities.splice(idx, 1)
  emit('update', m)
}

function updateEntityDescription(idx: number, val: string) {
  const m = cloneModel()
  m.entities[idx].description = val
  emit('update', m)
}

// ── Field editing ─────────────────────────────────────────────────────────────
function addField(entityIdx: number) {
  const m = cloneModel()
  m.entities[entityIdx].fields.push({
    name: 'new_field', type: 'VARCHAR(255)',
    primary_key: false, nullable: true, unique: false, indexed: false, default: null, description: '',
  })
  const eName = m.entities[entityIdx].name
  expandedEntities.value = new Set([...expandedEntities.value, eName])
  emit('update', m)
}

function removeField(entityIdx: number, fieldIdx: number) {
  const m = cloneModel()
  m.entities[entityIdx].fields.splice(fieldIdx, 1)
  emit('update', m)
  editingField.value = null
}

function updateField(entityIdx: number, fieldIdx: number, key: keyof DataModelField, value: any) {
  const m = cloneModel()
  ;(m.entities[entityIdx].fields[fieldIdx] as any)[key] = value
  emit('update', m)
}

function startEditField(entityName: string, fieldIdx: number) {
  if (props.readonly) return
  editingField.value = { entity: entityName, fieldIdx }
}
function stopEditField() { editingField.value = null }
function isEditingField(entityName: string, fieldIdx: number) {
  return editingField.value?.entity === entityName && editingField.value?.fieldIdx === fieldIdx
}

const COMMON_TYPES = ['UUID', 'VARCHAR(255)', 'VARCHAR(100)', 'INTEGER', 'BIGINT', 'FLOAT', 'DECIMAL(10,2)', 'BOOLEAN', 'TEXT', 'DATETIME', 'DATE', 'JSON']
</script>

<template>
  <div class="space-y-4">
    <!-- Summary -->
    <p v-if="model.summary" class="text-sm text-gray-600 dark:text-gray-400 italic">{{ model.summary }}</p>

    <!-- Entities table -->
    <div class="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
            <th class="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">Entity</th>
            <th class="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">Type</th>
            <th class="text-center px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">Fields</th>
            <th class="text-center px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">Relations</th>
            <th class="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200 w-56">Description</th>
            <th v-if="!readonly" class="w-10 px-2 py-3"></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(entity, eIdx) in (model.entities || [])" :key="entity.name">
            <!-- Entity row -->
            <tr class="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
              <td class="px-4 py-2.5">
                <div class="flex items-center gap-2">
                  <button @click="toggleEntity(entity.name)" class="flex items-center gap-2 text-left flex-1">
                    <i class="pi text-xs text-gray-400 flex-shrink-0 transition-transform duration-200"
                      :class="expandedEntities.has(entity.name) ? 'pi-chevron-down' : 'pi-chevron-right'" />
                    <span class="font-semibold text-gray-900 dark:text-gray-100">{{ entity.name }}</span>
                  </button>
                  <span v-if="getChangeAction(entity.name)" class="text-xs px-1.5 py-0.5 rounded font-medium uppercase flex-shrink-0"
                    :class="getChangeColor(getChangeAction(entity.name)!)">
                    {{ getChangeAction(entity.name) }}
                  </span>
                </div>
              </td>
              <td class="px-4 py-2.5">
                <span class="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                  {{ entity.type || 'table' }}
                </span>
              </td>
              <td class="px-4 py-2.5 text-center text-gray-600 dark:text-gray-400 font-medium">{{ (entity.fields || []).length }}</td>
              <td class="px-4 py-2.5 text-center text-gray-600 dark:text-gray-400 font-medium">{{ (entity.relationships || []).length }}</td>
              <!-- Description — truncated with hover tooltip -->
              <td class="px-4 py-2.5 w-56">
                <span
                  class="text-xs text-gray-500 dark:text-gray-400 block truncate max-w-[200px] cursor-help"
                  :title="entity.description || ''"
                >{{ entity.description || '-' }}</span>
              </td>
              <td v-if="!readonly" class="px-2 py-2.5">
                <button @click="removeEntity(eIdx)" title="Remove entity"
                  class="text-gray-300 hover:text-red-500 dark:text-gray-600 dark:hover:text-red-400 transition-colors">
                  <i class="pi pi-trash text-xs"></i>
                </button>
              </td>
            </tr>

            <!-- Expanded fields -->
            <tr v-if="expandedEntities.has(entity.name)">
              <td :colspan="readonly ? 5 : 6" class="px-4 py-4 bg-gray-50/50 dark:bg-gray-800/30 border-b border-gray-100 dark:border-gray-700">
                <div class="space-y-4 ml-5">

                  <!-- Description edit (when not readonly) -->
                  <div v-if="!readonly" class="flex items-center gap-2">
                    <span class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase w-24 flex-shrink-0">Description</span>
                    <input :value="entity.description" @input="updateEntityDescription(eIdx, ($event.target as HTMLInputElement).value)"
                      placeholder="Entity description..."
                      class="flex-1 text-xs px-2.5 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-purple-500" />
                  </div>

                  <!-- Fields sub-table -->
                  <div>
                    <div class="flex items-center justify-between mb-2">
                      <h4 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Fields</h4>
                      <button v-if="!readonly" @click="addField(eIdx)"
                        class="flex items-center gap-1 text-xs text-purple-600 dark:text-purple-400 hover:underline">
                        <i class="pi pi-plus text-xs"></i> Add Field
                      </button>
                    </div>
                    <div class="border border-gray-200 dark:border-gray-600 rounded-lg overflow-hidden">
                      <table class="w-full text-xs">
                        <thead>
                          <tr class="bg-gray-100 dark:bg-gray-700/50">
                            <th class="text-left px-3 py-2 font-semibold text-gray-600 dark:text-gray-300">Name</th>
                            <th class="text-left px-3 py-2 font-semibold text-gray-600 dark:text-gray-300">Type</th>
                            <th class="text-center px-2 py-2 font-semibold text-gray-600 dark:text-gray-300 w-8">PK</th>
                            <th class="text-center px-2 py-2 font-semibold text-gray-600 dark:text-gray-300 w-16">Nullable</th>
                            <th class="text-center px-2 py-2 font-semibold text-gray-600 dark:text-gray-300 w-14">Unique</th>
                            <th class="text-center px-2 py-2 font-semibold text-gray-600 dark:text-gray-300 w-14">Indexed</th>
                            <th class="text-left px-3 py-2 font-semibold text-gray-600 dark:text-gray-300">Description</th>
                            <th v-if="!readonly" class="w-8 px-2 py-2"></th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="(field, fIdx) in (entity.fields || [])" :key="fIdx"
                            class="border-t border-gray-100 dark:border-gray-600 hover:bg-white dark:hover:bg-gray-700/30 transition-colors"
                            @click="!readonly && startEditField(entity.name, fIdx)">

                            <!-- View mode -->
                            <template v-if="!isEditingField(entity.name, fIdx)">
                              <td class="px-3 py-2 font-mono font-semibold text-gray-900 dark:text-gray-100">{{ field.name }}</td>
                              <td class="px-3 py-2 font-mono text-blue-600 dark:text-blue-400">{{ field.type }}</td>
                              <td class="px-2 py-2 text-center">
                                <span v-if="field.primary_key" class="text-amber-500">&#9679;</span>
                                <span v-else class="text-gray-300 dark:text-gray-600">-</span>
                              </td>
                              <td class="px-2 py-2 text-center" :class="field.nullable ? 'text-green-500' : 'text-red-400'">
                                {{ field.nullable ? '✓' : '✗' }}
                              </td>
                              <td class="px-2 py-2 text-center">
                                <span v-if="field.unique" class="text-blue-500">&#9679;</span>
                                <span v-else class="text-gray-300 dark:text-gray-600">-</span>
                              </td>
                              <td class="px-2 py-2 text-center">
                                <span v-if="field.indexed" class="text-purple-500">&#9679;</span>
                                <span v-else class="text-gray-300 dark:text-gray-600">-</span>
                              </td>
                              <td class="px-3 py-2 text-gray-500 dark:text-gray-400 max-w-[200px]">
                                <span class="truncate block cursor-help" :title="field.description || ''">
                                  {{ field.description || '-' }}
                                </span>
                              </td>
                              <td v-if="!readonly" class="px-2 py-2">
                                <button @click.stop="removeField(eIdx, fIdx)" title="Remove field"
                                  class="text-gray-300 hover:text-red-500 dark:text-gray-600 dark:hover:text-red-400 transition-colors">
                                  <i class="pi pi-times text-xs"></i>
                                </button>
                              </td>
                            </template>

                            <!-- Edit mode -->
                            <template v-else>
                              <td class="px-2 py-1.5" @click.stop>
                                <input :value="field.name" @input="updateField(eIdx, fIdx, 'name', ($event.target as HTMLInputElement).value)"
                                  class="w-full font-mono px-2 py-1 text-xs rounded border border-purple-400 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none" />
                              </td>
                              <td class="px-2 py-1.5" @click.stop>
                                <select :value="field.type" @change="updateField(eIdx, fIdx, 'type', ($event.target as HTMLSelectElement).value)"
                                  class="w-full font-mono px-2 py-1 text-xs rounded border border-purple-400 bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 focus:outline-none">
                                  <option v-for="t in COMMON_TYPES" :key="t" :value="t">{{ t }}</option>
                                  <option :value="field.type" v-if="!COMMON_TYPES.includes(field.type)">{{ field.type }}</option>
                                </select>
                              </td>
                              <td class="px-2 py-1.5 text-center" @click.stop>
                                <input type="checkbox" :checked="field.primary_key"
                                  @change="updateField(eIdx, fIdx, 'primary_key', ($event.target as HTMLInputElement).checked)"
                                  class="accent-amber-500" />
                              </td>
                              <td class="px-2 py-1.5 text-center" @click.stop>
                                <input type="checkbox" :checked="field.nullable"
                                  @change="updateField(eIdx, fIdx, 'nullable', ($event.target as HTMLInputElement).checked)"
                                  class="accent-green-500" />
                              </td>
                              <td class="px-2 py-1.5 text-center" @click.stop>
                                <input type="checkbox" :checked="field.unique"
                                  @change="updateField(eIdx, fIdx, 'unique', ($event.target as HTMLInputElement).checked)"
                                  class="accent-blue-500" />
                              </td>
                              <td class="px-2 py-1.5 text-center" @click.stop>
                                <input type="checkbox" :checked="field.indexed"
                                  @change="updateField(eIdx, fIdx, 'indexed', ($event.target as HTMLInputElement).checked)"
                                  class="accent-purple-500" />
                              </td>
                              <td class="px-2 py-1.5" @click.stop>
                                <input :value="field.description" @input="updateField(eIdx, fIdx, 'description', ($event.target as HTMLInputElement).value)"
                                  placeholder="Field description"
                                  class="w-full px-2 py-1 text-xs rounded border border-purple-400 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none" />
                              </td>
                              <td class="px-2 py-1.5 text-center" @click.stop>
                                <button @click="stopEditField" class="text-purple-500 hover:text-purple-700">
                                  <i class="pi pi-check text-xs"></i>
                                </button>
                              </td>
                            </template>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                    <p v-if="!readonly" class="text-xs text-gray-400 mt-1.5">Click a row to edit &middot; Click &#x2715; to delete a field</p>
                  </div>

                  <!-- Relationships -->
                  <div v-if="(entity.relationships || []).length > 0">
                    <h4 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Relationships</h4>
                    <div class="flex flex-wrap gap-2">
                      <div v-for="(rel, i) in entity.relationships" :key="i"
                        class="flex items-center gap-2 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 text-xs bg-white dark:bg-gray-800">
                        <span class="font-semibold text-gray-900 dark:text-gray-100">{{ entity.name }}</span>
                        <span class="px-2 py-0.5 rounded-full text-xs font-medium" :class="getRelTypeColor(rel.type)">
                          {{ rel.type.replace(/_/g,' ') }}
                        </span>
                        <span class="font-semibold text-gray-900 dark:text-gray-100">{{ rel.target_entity }}</span>
                        <span class="text-gray-400 font-mono text-[10px]">({{ rel.foreign_key }}, {{ rel.on_delete }})</span>
                      </div>
                    </div>
                  </div>

                  <!-- Indexes -->
                  <div v-if="(entity.indexes || []).length > 0">
                    <h4 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Indexes</h4>
                    <div class="flex flex-wrap gap-2">
                      <span v-for="idx in entity.indexes" :key="idx.name"
                        class="text-xs px-2 py-1 rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 font-mono">
                        {{ idx.name }} ({{ (idx.fields || []).join(', ') }})
                        <span v-if="idx.unique" class="text-amber-500 ml-1">UNIQUE</span>
                      </span>
                    </div>
                  </div>

                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>

      <!-- Add entity row -->
      <div v-if="!readonly"
        class="px-4 py-2.5 border-t border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/30">
        <button @click="addEntity"
          class="flex items-center gap-1.5 text-xs text-purple-600 dark:text-purple-400 hover:underline font-medium">
          <i class="pi pi-plus-circle text-sm"></i>
          Add Entity
        </button>
      </div>
    </div>

    <!-- Enums -->
    <div v-if="(model.enums || []).length > 0">
      <h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Enums</h4>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        <div v-for="enumDef in model.enums" :key="enumDef.name"
          class="border border-gray-200 dark:border-gray-700 rounded-xl p-3 bg-white dark:bg-gray-800">
          <div class="font-semibold text-sm text-gray-900 dark:text-gray-100 mb-0.5">{{ enumDef.name }}</div>
          <div v-if="enumDef.description" class="text-xs text-gray-500 dark:text-gray-400 mb-2" :title="enumDef.description">
            {{ enumDef.description }}
          </div>
          <div class="flex flex-wrap gap-1.5">
            <span v-for="val in (enumDef.values || [])" :key="val.name"
              class="text-xs px-2 py-0.5 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 rounded-full cursor-help"
              :title="val.description">
              {{ val.name }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Change log -->
    <div v-if="(model.change_log || []).length > 0">
      <h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Change Log</h4>
      <div class="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
        <table class="w-full text-xs">
          <thead>
            <tr class="bg-gray-50 dark:bg-gray-800">
              <th class="text-left px-3 py-2.5 font-semibold text-gray-600 dark:text-gray-300">Entity</th>
              <th class="text-left px-3 py-2.5 font-semibold text-gray-600 dark:text-gray-300">Action</th>
              <th class="text-left px-3 py-2.5 font-semibold text-gray-600 dark:text-gray-300">Reason</th>
              <th class="text-left px-3 py-2.5 font-semibold text-gray-600 dark:text-gray-300">Fields Changed</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(change, i) in model.change_log" :key="i" class="border-t border-gray-100 dark:border-gray-700">
              <td class="px-3 py-2 font-semibold text-gray-800 dark:text-gray-200">{{ change.entity }}</td>
              <td class="px-3 py-2">
                <span class="px-1.5 py-0.5 rounded text-xs uppercase font-medium" :class="getChangeColor(change.action)">{{ change.action }}</span>
              </td>
              <td class="px-3 py-2 text-gray-600 dark:text-gray-400 max-w-[200px]">
                <span class="truncate block" :title="change.reason">{{ change.reason }}</span>
              </td>
              <td class="px-3 py-2 text-gray-500 dark:text-gray-400 font-mono">{{ (change.fields_changed || []).join(', ') || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
