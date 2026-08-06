import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api/client'
import type { BacklogTree } from '../types'

export const useBacklogStore = defineStore('backlog', () => {
  const backlog = ref<BacklogTree | null>(null)
  const loading = ref(false)

  async function fetchBacklog(projectId: string) {
    loading.value = true
    try {
      const { data } = await api.get(`/projects/${projectId}/backlog`)
      backlog.value = data
    } finally {
      loading.value = false
    }
  }

  async function uploadFile(projectId: string, file: File) {
    const formData = new FormData()
    formData.append('file', file)
    const { data } = await api.post(`/projects/${projectId}/backlog/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    await fetchBacklog(projectId)
    return data
  }

  async function importFromAzureDevOps(projectId: string, payload: { org_url: string; project: string; pat: string; query?: string }) {
    const { data } = await api.post(`/projects/${projectId}/backlog/azure-devops`, payload)
    await fetchBacklog(projectId)
    return data
  }

  async function deleteFeature(projectId: string, featureId: string) {
    await api.delete(`/projects/${projectId}/backlog/features/${featureId}`)
    await fetchBacklog(projectId)
  }

  return { backlog, loading, fetchBacklog, uploadFile, importFromAzureDevOps, deleteFeature }
})
