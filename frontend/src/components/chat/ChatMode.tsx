import { useState, useRef, useEffect, useCallback } from 'react'
import { Bot, Send, User, Loader2, BarChart3, Download, RefreshCw, Sparkles, ChevronDown } from 'lucide-react'
import { useStore, ChatMessage } from '@/store'
import { postChat } from '@/services/api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import clsx from 'clsx'

const SUGGESTIONS = [
  'Which stocks moved more than 8% in the last 3 months?',
  'Show me all stocks where volume > 3× average before a breakout',
  'What sectors had the highest momentum in July?',
  'Find stocks similar to Suzlon before its rally',
  'Which stocks have score > 80 and are near 52-week high?',
  'Show top 20 momentum stocks with volume spike today',
  'Explain the momentum scoring model',
  'Compare RELIANCE and TCS on all metrics',
]

export default function ChatMode() {
  const { chatHistory, addMessage, clearChat } = useStore()
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatHistory])

  const send = useCallback(async (text: string) => {
    if (!text.trim() || loading) return
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content: text, timestamp: new Date() }
    addMessage(userMsg)
    setInput('')
    setLoading(true)
    try {
      const history = chatHistory.map((m) => ({ role: m.role, content: m.content }))
      const res = await postChat(text, history)
      addMessage({
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: res.answer,
        timestamp: new Date(),
        data: res.data,
        charts: res.charts,
        sql: res.sql,
      })
    } catch {
      addMessage({
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: '⚠️ Could not reach the AI backend. Make sure the FastAPI server is running on port 8000.',
        timestamp: new Date(),
      })
    } finally {
      setLoading(false)
    }
  }, [chatHistory, loading, addMessage])

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-accent flex items-center justify-center shadow-accent">
            <Sparkles size={15} className="text-white" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-text-primary">AI Research Assistant</h2>
            <p className="text-xs text-text-muted">Powered by LLM + SQL + ML • Context-aware</p>
          </div>
        </div>
        {chatHistory.length > 0 && (
          <button onClick={clearChat} className="btn-ghost flex items-center gap-1.5 text-xs">
            <RefreshCw size={12} /> New conversation
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {chatHistory.length === 0 ? (
          <EmptyState onSuggest={send} />
        ) : (
          chatHistory.map((msg) => <MessageBubble key={msg.id} msg={msg} />)
        )}

        {loading && (
          <div className="flex items-start gap-3 animate-fade-in">
            <div className="w-8 h-8 rounded-xl bg-accent flex items-center justify-center flex-shrink-0">
              <Bot size={14} className="text-white" />
            </div>
            <div className="glass rounded-2xl rounded-tl-none px-4 py-3 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin text-accent" />
              <span className="text-sm text-text-muted">Thinking…</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-border flex-shrink-0">
        <div className="glass rounded-2xl p-3 flex items-end gap-3 focus-within:border-accent border border-border transition-all">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask anything about NSE markets…  (Shift+Enter for new line)"
            rows={1}
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none resize-none max-h-40 overflow-y-auto"
            style={{ fieldSizing: 'content' } as React.CSSProperties}
          />
          <button
            onClick={() => send(input)}
            disabled={loading || !input.trim()}
            className={clsx(
              'p-2.5 rounded-xl transition-all flex-shrink-0',
              input.trim() && !loading
                ? 'bg-accent text-white hover:bg-blue-500 shadow-accent'
                : 'bg-surface text-text-muted cursor-not-allowed'
            )}
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
        <p className="text-xs text-text-muted text-center mt-2">
          AI can run SQL, generate charts, train models, and explain results in plain English.
        </p>
      </div>
    </div>
  )
}

function EmptyState({ onSuggest }: { onSuggest: (s: string) => void }) {
  return (
    <div className="flex flex-col items-center py-12 gap-8 animate-fade-in">
      <div className="text-center space-y-2">
        <div className="w-16 h-16 rounded-2xl bg-accent-dim border border-accent/20 flex items-center justify-center mx-auto mb-4">
          <Sparkles size={28} className="text-accent" />
        </div>
        <h3 className="text-lg font-semibold text-text-primary">What would you like to research?</h3>
        <p className="text-sm text-text-muted max-w-md">
          Ask in plain English. I'll query the market data, run analysis, generate charts, and explain the results.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-2xl">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onSuggest(s)}
            className="glass rounded-xl px-4 py-3 text-left text-sm text-text-secondary hover:text-text-primary hover:border-accent/30 border border-border transition-all hover:bg-surface-hover group"
          >
            <span className="text-accent group-hover:text-accent mr-2 text-xs">↗</span>
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user'

  return (
    <div className={clsx('flex items-start gap-3 animate-slide-up', isUser && 'flex-row-reverse')}>
      {/* Avatar */}
      <div className={clsx(
        'w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0',
        isUser ? 'bg-bg-300 border border-border' : 'bg-accent shadow-accent'
      )}>
        {isUser ? <User size={14} className="text-text-secondary" /> : <Bot size={14} className="text-white" />}
      </div>

      {/* Bubble */}
      <div className={clsx(
        'max-w-[80%] rounded-2xl px-4 py-3 space-y-3',
        isUser
          ? 'bg-accent-dim border border-accent/20 rounded-tr-none'
          : 'glass rounded-tl-none'
      )}>
        <div className={clsx('text-sm prose prose-invert max-w-none', isUser && 'text-accent')}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
        </div>

        {/* Generated SQL */}
        {msg.sql && (
          <details className="rounded-xl border border-border overflow-hidden">
            <summary className="px-3 py-2 text-xs text-text-muted cursor-pointer hover:bg-surface-hover flex items-center gap-1.5">
              <span className="text-accent font-mono">SQL</span> View generated query
            </summary>
            <pre className="px-3 py-2 text-xs font-mono text-gold bg-bg-100 overflow-x-auto">{msg.sql}</pre>
          </details>
        )}

        {/* Attached data table */}
        {msg.data && Array.isArray(msg.data) && msg.data.length > 0 && (
          <DataTable data={msg.data as Record<string, unknown>[]} />
        )}

        {/* Attached charts */}
        {msg.charts && (msg.charts as ChartSpec[]).map((c, i) => (
          <MiniChart key={i} spec={c as ChartSpec} />
        ))}

        <p className="text-xs text-text-muted">{new Date(msg.timestamp).toLocaleTimeString()}</p>
      </div>
    </div>
  )
}

interface ChartSpec { type: string; data: { name: string; value: number }[]; title?: string }

function MiniChart({ spec }: { spec: ChartSpec }) {
  if (!spec?.data?.length) return null
  const Chart = spec.type === 'bar' ? BarChart : LineChart
  const DataComp = spec.type === 'bar' ? Bar : Line

  return (
    <div className="bg-bg-100 rounded-xl p-3 border border-border">
      {spec.title && <p className="text-xs font-medium text-text-secondary mb-2">{spec.title}</p>}
      <ResponsiveContainer width="100%" height={160}>
        <Chart data={spec.data}>
          <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#8b96a7' }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 10, fill: '#8b96a7' }} axisLine={false} tickLine={false} width={40} />
          <Tooltip
            contentStyle={{ background: '#0f1520', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', fontSize: 12 }}
            labelStyle={{ color: '#e2e8f0' }}
          />
          {spec.type === 'bar' ? (
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {spec.data.map((_, i) => <Cell key={i} fill={`hsl(${200 + i * 15}, 70%, 55%)`} />)}
            </Bar>
          ) : (
            <Line dataKey="value" stroke="#1e90ff" strokeWidth={2} dot={false} />
          )}
        </Chart>
      </ResponsiveContainer>
    </div>
  )
}

function DataTable({ data }: { data: Record<string, unknown>[] }) {
  const [expanded, setExpanded] = useState(false)
  const cols = Object.keys(data[0] || {})
  const rows = expanded ? data : data.slice(0, 8)

  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border bg-bg-100">
              {cols.map((c) => (
                <th key={c} className="px-3 py-2 text-left text-text-muted font-medium uppercase tracking-wider whitespace-nowrap">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-border/50 hover:bg-surface-hover transition-colors">
                {cols.map((c) => {
                  const val = row[c]
                  const isNum = typeof val === 'number'
                  const isPct = isNum && (c.includes('pct') || c.includes('%'))
                  return (
                    <td key={c} className={clsx(
                      'px-3 py-2 whitespace-nowrap font-mono',
                      isPct && (val as number) > 0 ? 'text-bull' : isPct && (val as number) < 0 ? 'text-bear' : 'text-text-secondary'
                    )}>
                      {isPct ? `${(val as number) > 0 ? '+' : ''}${(val as number).toFixed(2)}%`
                        : isNum ? (val as number).toLocaleString() : String(val ?? '—')}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between px-3 py-2 bg-bg-100 border-t border-border">
        <span className="text-xs text-text-muted">{data.length} rows</span>
        <div className="flex items-center gap-2">
          {data.length > 8 && (
            <button onClick={() => setExpanded((e) => !e)} className="btn-ghost text-xs flex items-center gap-1">
              <ChevronDown size={11} className={clsx('transition-transform', expanded && 'rotate-180')} />
              {expanded ? 'Show less' : `Show all ${data.length}`}
            </button>
          )}
          <button
            onClick={() => {
              const csv = [cols.join(','), ...data.map((r) => cols.map((c) => r[c]).join(','))].join('\n')
              const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv])); a.download = 'results.csv'; a.click()
            }}
            className="btn-ghost text-xs flex items-center gap-1"
          >
            <Download size={11} /> CSV
          </button>
        </div>
      </div>
    </div>
  )
}
