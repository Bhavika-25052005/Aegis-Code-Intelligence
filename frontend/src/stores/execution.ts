import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api/client'
import type { ExecutionStatus } from '../types'

export const useExecutionStore = defineStore('execution', () => {
  const status = ref<ExecutionStatus | null>(null)
  const logs = ref<string[]>([])
  const loading = ref(false)

  async function startExecution(projectId: string) {
    loading.value = true
    try {
      const { data } = await api.post(`/projects/${projectId}/execute`)
      status.value = data
    } finally {
      loading.value = false
    }
  }

  async function pauseExecution(projectId: string) {
    await api.post(`/projects/${projectId}/execute/pause`)
    if (status.value) status.value.status = 'paused'
  }

  async function resumeExecution(projectId: string) {
    await api.post(`/projects/${projectId}/execute/resume`)
    if (status.value) status.value.status = 'running'
  }

  async function fetchStatus(projectId: string) {
    const { data } = await api.get(`/projects/${projectId}/execute/status`)
    status.value = data
  }

  function addLog(message: string) {
    logs.value.push(message)
  }

  function clearLogs() {
    logs.value = []
  }

  function updateFromWebSocket(payload: Record<string, unknown>) {
    if (status.value && payload.completed_tasks !== undefined) {
      status.value.completed_tasks = payload.completed_tasks as number
    }
    if (status.value && payload.status !== undefined) {
      status.value.status = payload.status as string
    }
  }

  return { status, logs, loading, startExecution, pauseExecution, resumeExecution, fetchStatus, addLog, clearLogs, updateFromWebSocket }
})
