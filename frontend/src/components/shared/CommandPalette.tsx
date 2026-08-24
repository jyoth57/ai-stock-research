import { useEffect, useState, useRef } from 'react'
import { useStore } from '@/store'
import { Search, Bot, BarChart3, TrendingUp, FlaskConical, Command } from 'lucide-react'
import clsx from 'clsx'

interface Cmd { id: string; label: string; description?: string; icon: React.ElementType; action: () => void; tags?: string[] }

export default function CommandPalette() {
  const { commandPaletteOpen, setCommandPaletteOpen, setMode, setSelectedStock, addMessage } = useStore()
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const commands: Cmd[] = [
    { id: 'home',      label: 'Go to Home',          icon: Command,   action: () => setMode('home'),       tags: ['navigate'] },
    { id: 'chat',      label: 'Open AI Chat',         icon: Bot,       action: () => setMode('chat'),       tags: ['ai', 'chat'] },
    { id: 'dashboard', label: 'Open Dashboard',       icon: BarChart3, action: () => setMode('dashboard'),  tags: ['dash'] },
    { id: 'momentum',  label: 'Momentum Dashboard',   icon: TrendingUp,action: () => { setMode('dashboard'); useStore.getState().setActiveDashboard('momentum') }, tags: ['momentum'] },
    { id: 'breakout',  label: 'Breakout Dashboard',   icon: TrendingUp,action: () => { setMode('dashboard'); useStore.getState().setActiveDashboard('breakout') }, tags: ['breakout'] },
    { id: 'workbench', label: 'Open Workbench',       icon: FlaskConical,action: () => setMode('workbench'),tags: ['lab', 'sql', 'python'] },
    { id: 'scan_all',  label: 'Run Full Momentum Scan', icon: TrendingUp,action: () => { setMode('dashboard'); useStore.getState().setActiveDashboard('momentum') }, tags: ['scan'] },
    { id: 'big_movers',label: 'Ask: Stocks moved >8% today',icon: Bot,
      action: () => { addMessage({ id: Date.now().toString(), role: 'user', content: 'Which stocks moved more than 8% today?', timestamp: new Date() }); setMode('chat') }, tags: ['ai'] },
    { id: 'vol_spike', label: 'Ask: Volume spike stocks', icon: Bot,
      action: () => { addMessage({ id: Date.now().toString(), role: 'user', content: 'Show all stocks with volume > 3x average today', timestamp: new Date() }); setMode('chat') }, tags: ['ai', 'volume'] },
    { id: 'sector_rot',label: 'Ask: Sector rotation',    icon: Bot,
      action: () => { addMessage({ id: Date.now().toString(), role: 'user', content: 'What sectors had the highest momentum this month?', timestamp: new Date() }); setMode('chat') }, tags: ['ai', 'sector'] },
  ]

  const filtered = query.trim()
    ? commands.filter((c) =>
        c.label.toLowerCase().includes(query.toLowerCase()) ||
        c.tags?.some((t) => t.includes(query.toLowerCase()))
      )
    : commands

  useEffect(() => {
    if (commandPaletteOpen) { setQuery(''); setTimeout(() => inputRef.current?.focus(), 50) }
  }, [commandPaletteOpen])

  if (!commandPaletteOpen) return null

  const run = (cmd: Cmd) => { cmd.action(); setCommandPaletteOpen(false) }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-24"
      onClick={() => setCommandPaletteOpen(false)}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Palette */}
      <div
        className="relative w-full max-w-xl glass-heavy rounded-2xl shadow-panel overflow-hidden animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Search size={16} className="text-text-muted flex-shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setCommandPaletteOpen(false)
              if (e.key === 'Enter' && filtered[0]) run(filtered[0])
            }}
            placeholder="Search commands, stocks, dashboards…"
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none"
          />
          <kbd className="glass text-xs px-1.5 py-0.5 rounded font-mono text-text-muted">ESC</kbd>
        </div>

        {/* Results */}
        <div className="max-h-72 overflow-y-auto py-1">
          {filtered.map((cmd, i) => {
            const Icon = cmd.icon
            return (
              <button
                key={cmd.id}
                onClick={() => run(cmd)}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-surface-hover transition-colors text-left"
              >
                <div className="w-7 h-7 rounded-lg glass flex items-center justify-center flex-shrink-0">
                  <Icon size={13} className="text-accent" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-text-primary">{cmd.label}</p>
                  {cmd.description && <p className="text-xs text-text-muted truncate">{cmd.description}</p>}
                </div>
                {i === 0 && query && (
                  <kbd className="glass text-xs px-1.5 py-0.5 rounded font-mono text-text-muted flex-shrink-0">↵</kbd>
                )}
              </button>
            )
          })}
          {filtered.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-text-muted">No commands found</div>
          )}
        </div>

        <div className="border-t border-border px-4 py-2 flex items-center gap-4 text-xs text-text-muted">
          <span className="flex items-center gap-1"><kbd className="glass px-1 py-0.5 rounded font-mono">↑↓</kbd> navigate</span>
          <span className="flex items-center gap-1"><kbd className="glass px-1 py-0.5 rounded font-mono">↵</kbd> select</span>
          <span className="flex items-center gap-1"><kbd className="glass px-1 py-0.5 rounded font-mono">ESC</kbd> close</span>
        </div>
      </div>
    </div>
  )
}
