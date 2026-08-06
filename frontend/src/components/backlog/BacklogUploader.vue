<script setup lang="ts">
import { ref } from 'vue'
import { useBacklogStore } from '../../stores/backlog'

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ uploaded: [] }>()

const backlogStore = useBacklogStore()
const dragover = ref(false)
const uploading = ref(false)
const error = ref('')

const acceptedFormats = '.xlsx,.xls,.csv,.json,.yaml,.yml'

async function handleFile(file: File) {
  error.value = ''
  uploading.value = true
  try {
    await backlogStore.uploadFile(props.projectId, file)
    emit('uploaded')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Upload failed'
  } finally {
    uploading.value = false
  }
}

function onDrop(event: DragEvent) {
  dragover.value = false
  const files = event.dataTransfer?.files
  if (files && files.length > 0) {
    handleFile(files[0])
  }
}

function onFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    handleFile(target.files[0])
  }
}
</script>

<template>
  <div
    class="border-2 border-dashed rounded-xl p-8 text-center transition-colors"
    :class="dragover ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20' : 'border-gray-300 dark:border-gray-600'"
    @dragover.prevent="dragover = true"
    @dragleave="dragover = false"
    @drop.prevent="onDrop"
  >
    <div v-if="uploading" class="space-y-3">
      <i class="pi pi-spin pi-spinner text-3xl text-blue-600"></i>
      <p class="text-gray-600 dark:text-gray-300">Parsing backlog file...</p>
    </div>
    <div v-else class="space-y-3">
      <i class="pi pi-cloud-upload text-4xl text-gray-400"></i>
      <p class="text-gray-600 dark:text-gray-300">
        Drag & drop your backlog file here, or
        <label class="text-blue-600 cursor-pointer hover:underline">
          browse
          <input type="file" :accept="acceptedFormats" class="hidden" @change="onFileSelect" />
        </label>
      </p>
      <p class="text-xs text-gray-400">Supported formats: Excel (.xlsx), CSV, JSON, YAML</p>
    </div>
    <p v-if="error" class="mt-3 text-sm text-red-500">{{ error }}</p>
  </div>
</template>
