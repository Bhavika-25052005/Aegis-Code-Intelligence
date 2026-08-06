import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api/client'
import type { Project } from '../types'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const loading = ref(false)

  async function fetchProjects() {
    loading.value = true
    try {
      const { data } = await api.get('/projects')
      projects.value = data
    } finally {
      loading.value = false
    }
  }

  async function fetchProject(id: string) {
    loading.value = true
    try {
      const { data } = await api.get(`/projects/${id}`)
      currentProject.value = data
    } finally {
      loading.value = false
    }
  }

  async function createProject(payload: Partial<Project> & { github_pat?: string; azure_devops_pat?: string }) {
    const { data } = await api.post('/projects', payload)
    projects.value.unshift(data)
    currentProject.value = data
    return data
  }

  async function updateProject(id: string, payload: Record<string, unknown>) {
    const { data } = await api.put(`/projects/${id}`, payload)
    currentProject.value = data
    const idx = projects.value.findIndex(p => p.id === id)
    if (idx !== -1) projects.value[idx] = data
    return data
  }

  async function deleteProject(id: string) {
    await api.delete(`/projects/${id}`)
    projects.value = projects.value.filter(p => p.id !== id)
    if (currentProject.value?.id === id) currentProject.value = null
  }

  return { projects, currentProject, loading, fetchProjects, fetchProject, createProject, updateProject, deleteProject }
})
