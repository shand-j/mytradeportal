import { useEffect, useRef, useState } from 'react'

export interface ChatMessage {
  id: string
  role: 'customer' | 'ai' | 'business'
  body: string
  created_at?: string
}

interface ChatThreadProps {
  initialMessages: ChatMessage[]
  /** Send one message; resolve with the immediate reply (if any) and whether
      the thread is now closed. */
  onSend: (body: string) => Promise<{ reply?: string; closed?: boolean }>
  /** Optional close affordance ("No more questions") — hidden once used. */
  onEnd?: () => void
  endLabel?: string
  sendingLabel?: string
}

/**
 * Inline chat-bubble thread. Poll-free: the POST response carries the
 * immediate AI reply, so the conversation advances one hop per send.
 */
export function ChatThread({
  initialMessages,
  onSend,
  onEnd,
  endLabel = 'No more questions',
  sendingLabel = 'Sending…',
}: ChatThreadProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages.length, sending])

  async function handleSend(e: React.FormEvent) {
    e.preventDefault()
    const body = draft.trim()
    if (!body || sending) return
    setError('')
    setSending(true)
    setDraft('')
    setMessages((prev) => [
      ...prev,
      { id: `local-${Date.now()}`, role: 'customer', body },
    ])
    try {
      const result = await onSend(body)
      if (result.reply) {
        setMessages((prev) => [
          ...prev,
          { id: `reply-${Date.now()}`, role: 'ai', body: result.reply ?? '' },
        ])
      }
      if (result.closed && onEnd) onEnd()
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'That message did not send — please try again.',
      )
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="border-2 border-[var(--ink)] bg-[var(--paper)]">
      <div className="max-h-[380px] space-y-3 overflow-y-auto px-4 py-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'customer' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={
                message.role === 'customer'
                  ? 'max-w-[85%] border-2 border-[var(--ink)] bg-[var(--accent)] px-3.5 py-2.5 text-[14px] leading-relaxed text-[var(--ink-deep)]'
                  : 'max-w-[85%] border-2 border-[var(--rule)] bg-[var(--paper-2)] px-3.5 py-2.5 text-[14px] leading-relaxed'
              }
            >
              {message.role !== 'customer' && (
                <p className="mb-0.5 text-[10.5px] font-bold uppercase tracking-[0.08em] text-[var(--muted)]">
                  {message.role === 'ai' ? 'Assistant' : 'Team'}
                </p>
              )}
              <p className="whitespace-pre-line">{message.body}</p>
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start" role="status">
            <div className="border-2 border-[var(--rule)] bg-[var(--paper-2)] px-3.5 py-2.5 text-[13px] text-[var(--muted)]">
              {sendingLabel}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && (
        <p role="alert" className="border-t-2 border-[var(--rule)] px-4 py-2 text-[12.5px] text-[var(--accent-dark)]">
          {error}
        </p>
      )}

      <form onSubmit={handleSend} className="flex items-stretch gap-2 border-t-2 border-[var(--ink)] p-3">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type your reply…"
          aria-label="Type your reply"
          className="min-w-0 flex-1 border-2 border-[var(--ink)] bg-[var(--paper)] px-3 py-2 text-[14px] focus:outline-none"
        />
        <button
          type="submit"
          disabled={sending || !draft.trim()}
          className="border-2 border-[var(--ink)] bg-[var(--ink)] px-4 text-[12.5px] font-bold uppercase tracking-[0.06em] text-[var(--paper)] disabled:opacity-40"
        >
          Send
        </button>
      </form>

      {onEnd && (
        <div className="border-t border-[var(--rule)] px-4 py-2.5 text-center">
          <button
            type="button"
            onClick={onEnd}
            className="text-[12.5px] font-semibold text-[var(--muted)] underline underline-offset-2"
          >
            {endLabel}
          </button>
        </div>
      )}
    </div>
  )
}
