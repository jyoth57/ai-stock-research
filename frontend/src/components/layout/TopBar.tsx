import { useState, useEffect, useRef } from 'react'
import { Search, Bot, LayoutDashboard, FlaskConical, TrendingUp, Command, Star, Settings, ChevronDown } from 'lucide-react'
import { useStore } from '@/store'
import { fetchSymbolList } from '@/services/api'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'

const PLACEHOLDERS = [
  'Ask AI anything about the market…',
  'Which stocks moved >8% last week?',
  'Find breakouts with volume spike…',
  'Compare RELIANCE and TCS…',
  'Show sector rotation heatmap…',
  'Stocks similar to Suzlon before rally…',
]

export default function TopBar() {
  const { setCommandPaletteOpen, setMode, mode } = useStore()
  const [placeholder, setPlaceholder] = useState(PLACEHOLDERS[0])
  const [query, setQuery] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: symbols = [] } = useQuery({ queryKey: ['symbols'], queryFn: fetchSymbolList, staleTime: Infinity })

  // Rotate placeholder
  useEffect(() => {
    let i = 0
    const t = setInterval(() => { i = (i + 1) % PLACEHOLDERS.length; setPlaceholder(PLACEHOLDERS[i]) }, 4000)
    return () => clearInterval(t)
  }, [])

  // ⌘K shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); setCommandPaletteOpen(true) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [setCommandPaletteOpen])

  const filteredSymbols = query.length >= 1
    ? symbols.filter((s: string) => s.startsWith(query.toUpperCase())).slice(0, 8)
    : []

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setShowSuggestions(false)
    if (symbols.includes(query.toUpperCase())) {
      useStore.getState().setSelectedStock(query.toUpperCase())
    } else {
      useStore.getState().addMessage({ id: Date.now().toString(), role: 'user', content: query, timestamp: new Date() })
      setMode('chat')
    }
    setQuery('')
  }

  const navItems = [
    { id: 'home',      label: 'Home',       icon: LayoutDashboard },
    { id: 'chat',      label: 'AI Chat',    icon: Bot },
    { id: 'dashboard', label: 'Dashboard',  icon: TrendingUp },
    { id: 'explorer',  label: 'Explorer',   icon: Star },
    { id: 'workbench', label: 'Workbench',  icon: FlaskConical },
  ] as const

  return (
    <header className="h-14 glass-heavy border-b border-border flex items-center gap-3 px-4 z-50 flex-shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 w-52 flex-shrink-0">
        <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center shadow-accent">
          <TrendingUp size={14} className="text-white" />
        </div>
        <span className="font-semibold text-sm text-text-primary">QuantAI</span>
        <span className="text-text-muted text-xs ml-1 hidden xl:block">Research</span>
      </div>

      {/* Nav pills */}
      <nav className="hidden md:flex items-center gap-1">
        {navItems.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setMode(id)}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all',
              mode === id
                ? 'bg-accent-dim text-accent'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
            )}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </nav>

      {/* Global search */}
      <form onSubmit={handleSubmit} className="flex-1 max-w-xl mx-auto relative">
        <div className="relative flex items-center">
          <Search size={14} className="absolute left-3 text-text-muted pointer-events-none" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => { setQuery(e.target.value); setShowSuggestions(true) }}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
            onFocus={() => setShowSuggestions(true)}
            placeholder={placeholder}
            className="w-full bg-surface pl-9 pr-24 py-2 rounded-lg text-sm text-text-primary
                       placeholder:text-text-muted border border-border focus:border-accent
                       focus:ring-1 focus:ring-accent/30 outline-none transition-all"
          />
          <div className="absolute right-3 flex items-center gap-1 text-text-muted">
            <kbd className="glass text-xs px-1.5 py-0.5 rounded font-mono">⌘K</kbd>
          </div>
        </div>

        {/* Autocomplete dropdown */}
        {showSuggestions && filteredSymbols.length > 0 && (
          <div className="absolute top-full mt-1 left-0 right-0 glass-heavy rounded-lg border border-border overflow-hidden z-50 animate-fade-in">
            {filteredSymbols.map((s: string) => (
              <button
                key={s}
                onMouseDown={() => { useStore.getState().setSelectedStock(s); setQuery(''); setShowSuggestions(false) }}
                className="w-full text-left px-4 py-2.5 text-sm flex items-center gap-3 hover:bg-surface-hover transition-colors"
              >
                <TrendingUp size={12} className="text-accent flex-shrink-0" />
                <span className="text-text-primary font-medium">{s}</span>
                <span className="text-text-muted text-xs ml-auto">NSE</span>
              </button>
            ))}
            <div className="border-t border-border px-4 py-2 text-xs text-text-muted flex items-center gap-1">
              <Bot size={11} /> Press Enter to ask AI
            </div>
          </div>
        )}
      </form>

      {/* Right actions */}
      <div className="flex items-center gap-2 ml-auto flex-shrink-0">
        <button onClick={() => setCommandPaletteOpen(true)} className="btn-ghost flex items-center gap-1.5">
          <Command size={14} />
          <span className="hidden xl:block text-xs">Palette</span>
        </button>
        <button className="btn-ghost">
          <Settings size={14} />
        </button>
        <div className="flex items-center gap-2 glass px-3 py-1.5 rounded-lg cursor-pointer hover:bg-surface-hover transition-colors">
          <div className="w-6 h-6 rounded-full bg-accent flex items-center justify-center text-xs font-bold">Q</div>
          <ChevronDown size={12} className="text-text-muted" />
        </div>
      </div>
    </header>
  )
}
