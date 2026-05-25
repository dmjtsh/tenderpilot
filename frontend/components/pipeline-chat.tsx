"use client"

import { useEffect, useRef, useState } from "react"
import { Sparkles, Send, Loader2 } from "lucide-react"

interface ChatMessage {
  role: "user" | "assistant"
  text: string
}

function renderMarkdown(text: string) {
  const lines = text.split("\n")
  const elements: React.ReactNode[] = []
  let listItems: React.ReactNode[] = []
  let listType: "ul" | "ol" | null = null

  function flushList() {
    if (listItems.length > 0 && listType) {
      const Tag = listType
      elements.push(<Tag key={`list-${elements.length}`} className={listType === "ol" ? "list-decimal pl-4 my-0.5 space-y-0.5" : "list-disc pl-4 my-0.5 space-y-0.5"}>{listItems}</Tag>)
      listItems = []
      listType = null
    }
  }

  function inlineFmt(s: string): React.ReactNode[] {
    const parts: React.ReactNode[] = []
    const re = /\*\*(.+?)\*\*/g
    let last = 0
    let m: RegExpExecArray | null
    while ((m = re.exec(s)) !== null) {
      if (m.index > last) parts.push(s.slice(last, m.index))
      parts.push(<strong key={m.index}>{m[1]}</strong>)
      last = re.lastIndex
    }
    if (last < s.length) parts.push(s.slice(last))
    return parts
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const olMatch = line.match(/^\d+\.\s+(.*)/)
    const ulMatch = line.match(/^[-·•]\s+(.*)/)

    if (olMatch) {
      if (listType !== "ol") flushList()
      listType = "ol"
      listItems.push(<li key={i}>{inlineFmt(olMatch[1])}</li>)
    } else if (ulMatch) {
      if (listType !== "ul") flushList()
      listType = "ul"
      listItems.push(<li key={i}>{inlineFmt(ulMatch[1])}</li>)
    } else {
      flushList()
      if (line.trim() === "") {
        elements.push(<br key={i} />)
      } else {
        elements.push(<p key={i} className="my-0.5">{inlineFmt(line)}</p>)
      }
    }
  }
  flushList()
  return <>{elements}</>
}

export function PipelineChat({ tenderId }: { tenderId: number }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [streamingText, setStreamingText] = useState("")
  const [noDocs, setNoDocs] = useState(false)
  const [quotaExceeded, setQuotaExceeded] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, streamingText])

  async function handleSend() {
    const q = input.trim()
    if (!q || loading) return

    setInput("")
    setMessages((prev) => [...prev, { role: "user", text: q }])
    setLoading(true)
    setStreamingText("")

    const history = messages.map((m) => ({ role: m.role, text: m.text }))
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const token = (await import("@/lib/auth")).getToken()
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080/api/v1"
      const res = await fetch(`${apiBase}/tenders/${tenderId}/chat/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: q, history }),
        signal: controller.signal,
      })

      if (res.status === 402) {
        setQuotaExceeded(true)
        setMessages((prev) => prev.slice(0, -1))
        setLoading(false)
        return
      }

      if (!res.ok || !res.body) {
        setMessages((prev) => [...prev, { role: "assistant", text: "Ошибка при получении ответа." }])
        setLoading(false)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let fullText = ""
      let buffer = ""

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.error === "no_docs") {
              setNoDocs(true)
              setMessages((prev) => prev.slice(0, -1))
              setLoading(false)
              return
            }
            if (data.chunk) {
              fullText += data.chunk
              setStreamingText(fullText)
            }
            if (data.done) {
              setMessages((prev) => [...prev, { role: "assistant", text: fullText }])
              setStreamingText("")
            }
          } catch { /* skip malformed */ }
        }
      }

      if (fullText && !streamingText) {
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last?.role === "assistant" && last.text === fullText) return prev
          return [...prev, { role: "assistant", text: fullText }]
        })
        setStreamingText("")
      }
    } catch (e: unknown) {
      if ((e as Error)?.name !== "AbortError") {
        setMessages((prev) => [...prev, { role: "assistant", text: "Ошибка при получении ответа." }])
      }
    } finally {
      setLoading(false)
      setStreamingText("")
      abortRef.current = null
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (quotaExceeded) {
    return (
      <div className="py-4">
        <p className="text-sm text-gray-700">Лимит вопросов исчерпан</p>
        <a href="/#pricing" className="text-xs text-violet-600 font-medium hover:underline">Улучшить тариф</a>
      </div>
    )
  }

  if (noDocs) {
    return <p className="text-sm text-gray-400 py-4">Вопросы недоступны: документы не найдены</p>
  }

  return (
    <div className="flex flex-col h-full">
      {(messages.length > 0 || streamingText) && (
        <div className="flex-1 overflow-auto space-y-3 mb-3">
          {messages.map((msg, i) => (
            <div key={i}>
              {msg.role === "user" ? (
                <div className="flex justify-end">
                  <div className="bg-gray-100 rounded-xl px-4 py-2.5 max-w-[80%]">
                    <p className="text-sm text-gray-900">{msg.text}</p>
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-2.5 max-w-[90%]">
                  <Sparkles className="w-4 h-4 text-gray-500 mt-0.5 shrink-0" />
                  <div className="text-sm text-gray-700 leading-relaxed">{renderMarkdown(msg.text)}</div>
                </div>
              )}
            </div>
          ))}
          {streamingText && (
            <div className="flex items-start gap-2.5 max-w-[90%]">
              <Sparkles className="w-4 h-4 text-gray-500 mt-0.5 shrink-0" />
              <div className="text-sm text-gray-700 leading-relaxed">{renderMarkdown(streamingText)}</div>
            </div>
          )}
          {loading && !streamingText && (
            <div className="flex items-center gap-2">
              <Loader2 className="w-4 h-4 text-gray-400 animate-spin" />
              <span className="text-sm text-gray-400">Думаю...</span>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}

      {messages.length === 0 && !streamingText && (
        <div className="flex-1 flex items-center justify-center mb-6">
          <p className="text-[15px] text-gray-400">Спросите о требованиях, сроках, условиях...</p>
        </div>
      )}

      <div className="flex gap-2.5 shrink-0 mt-3">
        <input
          type="text"
          className="flex-1 h-10 border border-gray-200 rounded-lg px-4 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-gray-300"
          placeholder="Задайте вопрос..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          maxLength={500}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || loading}
          className="h-10 w-10 flex items-center justify-center bg-[#111827] text-white rounded-full hover:bg-gray-800 transition-colors disabled:opacity-40 shrink-0"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
