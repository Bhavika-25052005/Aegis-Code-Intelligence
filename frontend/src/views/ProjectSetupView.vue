<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '../stores/project'

const router = useRouter()
const projectStore = useProjectStore()

const step = ref(1)
const form = ref({
  name: '',
  github_repo_url: '',
  github_pat: '',
  azure_devops_org_url: '',
  azure_devops_project: '',
  azure_devops_pat: '',
  workspace_path: '',
  pr_strategy: 'per_story',
  claude_max_budget_usd: 5.0,
})

const prStrategyOptions = [
  { label: 'Per Task', value: 'per_task', description: 'One PR for each task' },
  { label: 'Per User Story', value: 'per_story', description: 'One PR per user story (groups tasks)' },
  { label: 'Per Feature', value: 'per_feature', description: 'One PR for the entire feature' },
]

async function handleCreate() {
  const project = await projectStore.createProject(form.value)
  router.push(`/projects/${project.id}/backlog`)
}

function nextStep() {
  if (step.value < 3) step.value++
}

function prevStep() {
  if (step.value > 1) step.value--
}
</script>

<template>
  <div class="max-w-2xl mx-auto">
    <h2 class="text-2xl font-bold text-gray-800 dark:text-white mb-6">Create New Project</h2>

    <!-- Progress Steps -->
    <div class="flex items-center mb-8">
      <div v-for="s in 3" :key="s" class="flex items-center">
        <div
          class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium"
          :class="s <= step ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500'"
        >
          {{ s }}
        </div>
        <div v-if="s < 3" class="w-16 h-0.5" :class="s < step ? 'bg-blue-600' : 'bg-gray-200'"></div>
      </div>
      <div class="ml-4 text-sm text-gray-500">
        {{ step === 1 ? 'Basic Info' : step === 2 ? 'GitHub & Azure DevOps' : 'Configuration' }}
      </div>
    </div>

    <!-- Step 1: Basic Info -->
    <div v-show="step === 1" class="space-y-4">
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Project Name</label>
        <input
          v-model="form.name"
          type="text"
          placeholder="My Awesome Project"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Workspace Path (optional)</label>
        <input
          v-model="form.workspace_path"
          type="text"
          placeholder="Leave empty for auto-managed directory"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <p class="text-xs text-gray-400 mt-1">Where generated code will be stored locally</p>
      </div>
    </div>

    <!-- Step 2: GitHub & Azure DevOps -->
    <div v-show="step === 2" class="space-y-4">
      <h3 class="text-lg font-semibold text-gray-700 dark:text-gray-200">GitHub</h3>
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Repository URL</label>
        <input
          v-model="form.github_repo_url"
          type="text"
          placeholder="https://github.com/owner/repo"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Personal Access Token</label>
        <input
          v-model="form.github_pat"
          type="password"
          placeholder="ghp_xxxxxxxxxxxx"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>

      <hr class="border-gray-200 dark:border-gray-700" />

      <h3 class="text-lg font-semibold text-gray-700 dark:text-gray-200">Azure DevOps (Optional)</h3>
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Organization URL</label>
        <input
          v-model="form.azure_devops_org_url"
          type="text"
          placeholder="https://dev.azure.com/your-org"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Project Name</label>
        <input
          v-model="form.azure_devops_project"
          type="text"
          placeholder="MyProject"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Azure DevOps PAT</label>
        <input
          v-model="form.azure_devops_pat"
          type="password"
          placeholder="Azure DevOps Personal Access Token"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>
    </div>

    <!-- Step 3: Configuration -->
    <div v-show="step === 3" class="space-y-4">
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">PR Strategy</label>
        <div class="space-y-2">
          <label
            v-for="option in prStrategyOptions"
            :key="option.value"
            class="flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-colors"
            :class="form.pr_strategy === option.value
              ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
              : 'border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'"
          >
            <input
              v-model="form.pr_strategy"
              type="radio"
              :value="option.value"
              class="mt-0.5"
            />
            <div>
              <span class="font-medium text-gray-800 dark:text-white">{{ option.label }}</span>
              <p class="text-xs text-gray-500 dark:text-gray-400">{{ option.description }}</p>
            </div>
          </label>
        </div>
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Budget per Task (USD)</label>
        <input
          v-model.number="form.claude_max_budget_usd"
          type="number"
          min="0.5"
          max="50"
          step="0.5"
          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <p class="text-xs text-gray-400 mt-1">Maximum Claude API spend per individual task</p>
      </div>
    </div>

    <!-- Navigation Buttons -->
    <div class="flex justify-between mt-8">
      <button
        v-if="step > 1"
        @click="prevStep"
        class="px-4 py-2 text-gray-600 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
      >
        Back
      </button>
      <div v-else></div>

      <button
        v-if="step < 3"
        @click="nextStep"
        :disabled="step === 1 && !form.name"
        class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Next
      </button>
      <button
        v-else
        @click="handleCreate"
        :disabled="!form.name"
        class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Create Project
      </button>
    </div>
  </div>
</template>
