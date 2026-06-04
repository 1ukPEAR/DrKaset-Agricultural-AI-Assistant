import { useState, useCallback, useRef } from 'react'
import { chatAPI } from '../api'

export function useChat() {
  const [sessions, setSessions] = useState([])
  const [activeSession, setActiveSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [streaming, setStreaming] = useState(false)
  const [loadingSessions, setLoadingSessions] = useState(false)
  const abortRef = useRef(null)

  const appendAssistantToken = useCallback((token) => {
    if (token === undefined) return
    setMessages((prev) => {
      const copy = [...prev]
      if (!copy.length) return prev
      const last = { ...copy[copy.length - 1] }
      last.content += token
      last.loading = false
      copy[copy.length - 1] = last
      return copy
    })
  }, [])

  const updateAssistantMeta = useCallback((patch) => {
    setMessages((prev) => {
      const copy = [...prev]
      if (!copy.length) return prev
      const last = { ...copy[copy.length - 1] }
      Object.assign(last, patch)
      copy[copy.length - 1] = last
      return copy
    })
  }, [])

  const fetchSessions = useCallback(async () => {
    setLoadingSessions(true)
    try {
      const res = await chatAPI.listSessions()
      setSessions(res.data)
    } finally {
      setLoadingSessions(false)
    }
  }, [])

  const loadSession = useCallback(async (session) => {
    setActiveSession(session)
    const res = await chatAPI.getMessages(session.id)
    setMessages(res.data)
  }, [])

  const newSession = useCallback(() => {
    setActiveSession(null)
    setMessages([])
  }, [])

  const deleteSession = useCallback(async (session) => {
    if (!session?.id || streaming) return

    await chatAPI.deleteSession(session.id)
    setSessions((prev) => prev.filter((s) => s.id !== session.id))

    if (activeSession?.id === session.id) {
      setActiveSession(null)
      setMessages([])
    }
  }, [activeSession, streaming])

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || streaming) return

    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMsg])

    const assistantMsg = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      intent: null,
      created_at: new Date().toISOString(),
      loading: true,
    }
    setMessages((prev) => [...prev, assistantMsg])
    setStreaming(true)

    const token = localStorage.getItem('drkaset_token')
    const body = JSON.stringify({
      message: text,
      ...(activeSession ? { session_id: activeSession.id } : {}),
    })

    try {
      const controller = new AbortController()
      abortRef.current = controller

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body,
        signal: controller.signal,
      })

      if (!response.ok || !response.body) {
        throw new Error('Chat request failed')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let sessionId = activeSession?.id

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const events = buffer.split('\n\n')
        buffer = events.pop() ?? ''

        for (const eventBlock of events) {
          const eventLines = eventBlock
            .split('\n')
            .map((line) => line.trim())
            .filter(Boolean)

          if (!eventLines.length) continue

          let eventName = 'message'
          const dataLines = []

          for (const line of eventLines) {
            if (line.startsWith('event:')) {
              eventName = line.slice(6).trim()
              continue
            }
            if (line.startsWith('data:')) {
              dataLines.push(line.slice(5).trim())
            }
          }

          const raw = dataLines.join('\n').trim()
          if (!raw || raw === '{}') {
            continue
          }

          try {
            const parsed = JSON.parse(raw)

            if (eventName === 'meta') {
              if (parsed.session_id) {
                sessionId = parsed.session_id
                setActiveSession({ id: parsed.session_id, title: text.slice(0, 50) })
              }
              if (parsed.intent) {
                updateAssistantMeta({ intent: parsed.intent })
              }
              continue
            }

            if (eventName === 'done') {
              continue
            }

            if (parsed.token !== undefined) {
              appendAssistantToken(parsed.token)
            }
            if (parsed.intent) {
              updateAssistantMeta({ intent: parsed.intent })
            }
          } catch {
            // Ignore malformed streaming chunks.
          }
        }
      }

      if (sessionId) {
        const sessRes = await chatAPI.listSessions()
        setSessions(sessRes.data)
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setMessages((prev) => {
          const copy = [...prev]
          const last = { ...copy[copy.length - 1] }
          last.content = '**เกิดข้อผิดพลาด**\n\n- กรุณาลองส่งคำถามใหม่อีกครั้งครับ'
          last.loading = false
          last.error = true
          copy[copy.length - 1] = last
          return copy
        })
      }
    } finally {
      setStreaming(false)
    }
  }, [activeSession, streaming, appendAssistantToken, updateAssistantMeta])

  const stopStream = useCallback(() => {
    abortRef.current?.abort()
    setStreaming(false)
  }, [])

  return {
    sessions, activeSession, messages,
    streaming, loadingSessions,
    fetchSessions, loadSession, newSession, deleteSession,
    sendMessage, stopStream,
  }
}
