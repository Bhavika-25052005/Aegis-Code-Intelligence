<script setup lang="ts">
import { ref } from 'vue'

const settings = ref({
  workspace_path: '',
  claude_timeout: 300,
  claude_max_retries: 3,
  claude_max_budget: 5.0,
})

const saved = ref(false)

function saveSettings() {
  localStorage.setItem('codegen-hub-settings', JSON.stringify(settings.value))
  saved.value = true
  setTimeout(() => { saved.value = false }, 2000)
}

function loadSettings() {
  const stored = localStorage.getItem('codegen-hub-settings')
  if (stored) {
    settings.value = { ...settings.value, ...JSON.parse(stored) }
  }
}

loadSettings()
</script>

<template>
  <div class="max-w-2xl mx-auto space-y-6">
    <h2 class="text-2xl font-bold text-gray-800 dark:text-white">Settings</h2>

    <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 space-y-5">
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Default Workspace Path</label>
        <input
          v-model="settings.workspace_path"
          type="text"
          placeholder="Leave empty for auto-managed temp directory"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Claude Timeout (seconds)</label>
        <input
          v-model.number="settings.claude_timeout"
          type="number"
          min="60"
          max="1800"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <p class="text-xs text-gray-400 mt-1">Max time for a single task before timeout (60-1800s)</p>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Retries per Task</label>
        <input
          v-model.number="settings.claude_max_retries"
          type="number"
          min="0"
          max="10"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Default Max Budget per Task (USD)</label>
        <input
          v-model.number="settings.claude_max_budget"
          type="number"
          min="0.5"
          max="50"
          step="0.5"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>

      <div class="flex items-center justify-between pt-2">
        <button
          @click="saveSettings"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          Save Settings
        </button>
        <span v-if="saved" class="text-sm text-green-500 flex items-center gap-1">
          <i class="pi pi-check"></i> Saved
        </span>
      </div>
    </div>

    <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
      <h3 class="font-semibold text-gray-800 dark:text-white mb-3">Prerequisites</h3>
      <ul class="space-y-2 text-sm text-gray-600 dark:text-gray-300">
        <li class="flex items-center gap-2">
          <i class="pi pi-check-circle text-green-500"></i>
          Claude Code CLI installed and authenticated
        </li>
        <li class="flex items-center gap-2">
          <i class="pi pi-check-circle text-green-500"></i>
          Git installed and configured
        </li>
        <li class="flex items-center gap-2">
          <i class="pi pi-info-circle text-blue-500"></i>
          GitHub PAT with repo access scope
        </li>
      </ul>
    </div>
  </div>
</template>
