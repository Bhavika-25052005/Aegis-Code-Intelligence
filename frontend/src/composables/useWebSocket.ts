import { ref, onUnmounted } from 'vue'
import type { WebSocketMessage } from '../types'

export function useWebSocket(projectId: string) {
  const connected = ref(false)
  const messages = ref<WebSocketMessage[]>([])
  let ws: WebSocket | null = null

  function connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/ws/projects/${projectId}/progress`

    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
    }

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data)
        messages.value.push(msg)
      } catch {
        // ignore non-JSON messages
      }
    }

    ws.onclose = () => {
      connected.value = false
      setTimeout(() => {
        if (!connected.value) connect()
      }, 3000)
    }

    ws.onerror = () => {
      ws?.close()
    }
  }

  function disconnect() {
    ws?.close()
    ws = null
  }

  onUnmounted(() => {
    disconnect()
  })

  return { connected, messages, connect, disconnect }
}
