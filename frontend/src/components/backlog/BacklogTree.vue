<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { BacklogTree } from '../../types'

defineProps<{ backlog: BacklogTree }>()

const route = useRoute()
const router = useRouter()

const expandedFeatures = ref<Set<string>>(new Set())
const expandedStories = ref<Set<string>>(new Set())

function toggleFeature(id: string) {
  if (expandedFeatures.value.has(id)) {
    expandedFeatures.value.delete(id)
  } else {
    expandedFeatures.value.add(id)
  }
}

function toggleStory(id: string) {
  if (expandedStories.value.has(id)) {
    expandedStories.value.delete(id)
  } else {
    expandedStories.value.add(id)
  }
}

function analyzeStory(storyId: string) {
  const projectId = route.params.id as string
  router.push(`/projects/${projectId}/requirements/${storyId}`)
}

function getStatusBadge(status: string) {
  switch (status) {
    case 'completed': return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
    case 'in_progress': return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
    case 'failed': return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
    default: return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
  }
}
</script>

<template>
  <div class="space-y-3">
    <!-- Features -->
    <div
      v-for="feature in backlog.features"
      :key="feature.id"
      class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      <!-- Feature Header -->
      <div
        class="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50"
        @click="toggleFeature(feature.id)"
      >
        <i
          class="pi text-xs text-gray-400 transition-transform"
          :class="expandedFeatures.has(feature.id) ? 'pi-chevron-down' : 'pi-chevron-right'"
        ></i>
        <i class="pi pi-box text-purple-500"></i>
        <span class="font-medium text-gray-800 dark:text-white flex-1">{{ feature.title }}</span>
        <span class="text-xs px-2 py-0.5 rounded-full" :class="getStatusBadge(feature.status)">
          {{ feature.status }}
        </span>
        <span class="text-xs text-gray-400">{{ feature.user_stories.length }} stories</span>
      </div>

      <!-- User Stories -->
      <div v-if="expandedFeatures.has(feature.id)" class="border-t border-gray-100 dark:border-gray-700">
        <div
          v-for="story in feature.user_stories"
          :key="story.id"
          class="ml-6 border-l-2 border-gray-200 dark:border-gray-600"
        >
          <!-- Story Header -->
          <div
            class="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50"
            @click="toggleStory(story.id)"
          >
            <i
              class="pi text-xs text-gray-400 transition-transform"
              :class="expandedStories.has(story.id) ? 'pi-chevron-down' : 'pi-chevron-right'"
            ></i>
            <i class="pi pi-bookmark text-blue-500"></i>
            <span class="text-sm text-gray-700 dark:text-gray-200 flex-1">{{ story.title }}</span>
            <button
              class="px-3 py-1.5 text-xs rounded-lg border border-blue-200 text-blue-600 hover:bg-blue-50"
              @click.stop="analyzeStory(story.id)"
            >
              AI Analyze
            </button>
            <span class="text-xs px-2 py-0.5 rounded-full" :class="getStatusBadge(story.status)">
              {{ story.status }}
            </span>
            <span class="text-xs text-gray-400">{{ story.tasks.length }} tasks</span>
          </div>

          <!-- Tasks -->
          <div v-if="expandedStories.has(story.id)" class="ml-8 pb-2">
            <div
              v-for="task in story.tasks"
              :key="task.id"
              class="flex items-center gap-3 px-4 py-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50"
            >
              <i class="pi pi-check-square text-gray-400"></i>
              <span class="text-sm text-gray-600 dark:text-gray-300 flex-1">{{ task.title }}</span>
              <span class="text-xs px-2 py-0.5 rounded-full" :class="getStatusBadge(task.status)">
                {{ task.status }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
