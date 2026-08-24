import { useState } from 'react'
import {
  TrendingUp, BarChart3, AlertTriangle, Layers, Star, BookOpen,
  ChevronRight, Activity, Zap, Shield, DollarSign, Newspaper,
  Building2, Search, SlidersHorizontal, Bot, FlaskConical,
} from 'lucide-react'
import { useStore } from '@/store'
import clsx from 'clsx'

interface ModuleItem {
  label: string
  icon: React.ElementType
  badge?: string
  badgeColor?: string
  action?: () => void
}

interface Module {
  id: string
  label: string
  icon: React.ElementType
  items: ModuleItem[]
}

export default function Sidebar() {
  const { sidebarOpen, setMode, setSelectedStock, watchlist } = useStore()
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['signals', 'watchlist']))

  const toggle = (id: string) =>
    setExpanded((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n })

  const modules: Module[] = [
    {
      id: 'signals',
      label: 'Signals',
      icon: Zap,
      items: [
        { label: 'Momentum Scan',     icon: TrendingUp,  badge: '178', badgeColor: 'bull',   action: () => setMode('dashboard') },
        { label: 'Volume Spikes',     icon: BarChart3,   badge: '45',  badgeColor: 'accent', action: () => setMode('dashboard') },
        { label: 'Breakouts',         icon: Activity,    badge: '91',  badgeColor: 'gold',   action: () => setMode('dashboard') },
        { label: 'Big Movers >8%',    icon: AlertTriangle, badge: '23', badgeColor: 'bear', action: () => setMode('dashboard') },
      ],
    },
    {
      id: 'watchlist',
      label: 'Watchlist',
      icon: Star,
      items: watchlist.map((s) => ({
        label: s,
        icon: TrendingUp,
        action: () => setSelectedStock(s),
      })),
    },
    {
      id: 'technical',
      label: 'Technical',
      icon: Activity,
      items: [
        { label: 'RSI Oversold',   icon: SlidersHorizontal },
        { label: '52-Week Highs',  icon: TrendingUp },
        { label: 'Golden Cross',   icon: Layers },
        { label: 'Death Cross',    icon: Layers },
      ],
    },
    {
      id: 'fundamentals',
      label: 'Fundamentals',
      icon: DollarSign,
      items: [
        { label: 'High ROE',       icon: Shield },
        { label: 'Low Debt',       icon: Shield },
        { label: 'PAT Growth >25%',icon: TrendingUp },
        { label: 'Revenue CAGR',   icon: BarChart3 },
      ],
    },
    {
      id: 'sectors',
      label: 'Sectors',
      icon: Building2,
      items: [
        { label: 'IT',           icon: Layers },
        { label: 'Banking',      icon: Layers },
        { label: 'FMCG',         icon: Layers },
        { label: 'Auto',         icon: Layers },
        { label: 'Pharma',       icon: Layers },
        { label: 'Infra',        icon: Layers },
        { label: 'Renewable',    icon: Layers },
        { label: 'Defence',      icon: Layers },
      ],
    },
    {
      id: 'research',
      label: 'Saved Research',
      icon: BookOpen,
      items: [
        { label: 'My Screens',     icon: Search },
        { label: 'AI Reports',     icon: Bot },
        { label: 'Notebooks',      icon: FlaskConical },
        { label: 'Saved Queries',  icon: BookOpen },
      ],
    },
    {
      id: 'news',
      label: 'News & Events',
      icon: Newspaper,
      items: [
        { label: 'Corporate Actions', icon: Building2 },
        { label: 'Upcoming Results',  icon: AlertTriangle },
        { label: 'NSE Announcements', icon: Newspaper },
      ],
    },
  ]

  if (!sidebarOpen) {
    return (
      <aside className="w-14 flex flex-col items-center py-4 gap-3 border-r border-border flex-shrink-0">
        {modules.map(({ id, icon: Icon }) => (
          <button key={id} title={id} className="p-2 rounded-lg text-text-muted hover:text-accent hover:bg-accent-dim transition-colors">
            <Icon size={16} />
          </button>
        ))}
      </aside>
    )
  }

  return (
    <aside className="w-56 flex flex-col border-r border-border flex-shrink-0 overflow-hidden">
      {/* Module search */}
      <div className="px-3 py-3 border-b border-border flex-shrink-0">
        <div className="relative flex items-center">
          <Search size={12} className="absolute left-2.5 text-text-muted" />
          <input
            placeholder="Filter modules…"
            className="w-full bg-bg-100 pl-7 pr-3 py-1.5 rounded-md text-xs text-text-primary
                       placeholder:text-text-muted border border-border focus:border-accent outline-none"
          />
        </div>
      </div>

      {/* Scrollable modules */}
      <div className="flex-1 overflow-y-auto py-2">
        {modules.map(({ id, label, icon: Icon, items }) => (
          <div key={id} className="mb-1">
            {/* Module header */}
            <button
              onClick={() => toggle(id)}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-surface-hover transition-colors group"
            >
              <Icon size={13} className="text-text-muted group-hover:text-accent transition-colors flex-shrink-0" />
              <span className="text-xs font-medium text-text-secondary flex-1 text-left">{label}</span>
              <ChevronRight
                size={12}
                className={clsx('text-text-muted transition-transform', expanded.has(id) && 'rotate-90')}
              />
            </button>

            {/* Module items */}
            {expanded.has(id) && (
              <div className="animate-fade-in">
                {items.map(({ label: itemLabel, icon: ItemIcon, badge, badgeColor, action }) => (
                  <button
                    key={itemLabel}
                    onClick={action}
                    className="w-full flex items-center gap-2 pl-8 pr-3 py-1.5 hover:bg-surface-hover transition-colors group"
                  >
                    <ItemIcon size={11} className="text-text-muted group-hover:text-text-secondary flex-shrink-0" />
                    <span className="text-xs text-text-muted group-hover:text-text-primary flex-1 text-left truncate">
                      {itemLabel}
                    </span>
                    {badge && (
                      <span className={clsx(
                        'text-xs px-1.5 py-0.5 rounded-full font-medium flex-shrink-0',
                        badgeColor === 'bull'   && 'bg-bull-dim text-bull',
                        badgeColor === 'bear'   && 'bg-bear-dim text-bear',
                        badgeColor === 'accent' && 'bg-accent-dim text-accent',
                        badgeColor === 'gold'   && 'bg-gold-dim text-gold',
                        !badgeColor            && 'bg-surface text-text-muted',
                      )}>
                        {badge}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer quick actions */}
      <div className="border-t border-border p-3 flex gap-2 flex-shrink-0">
        <button onClick={() => setMode('chat')} className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md bg-accent-dim text-accent text-xs font-medium hover:bg-accent hover:text-white transition-all">
          <Bot size={12} /> Ask AI
        </button>
        <button onClick={() => setMode('workbench')} className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md bg-surface text-text-secondary text-xs font-medium hover:bg-surface-hover transition-all">
          <FlaskConical size={12} /> Lab
        </button>
      </div>
    </aside>
  )
}
