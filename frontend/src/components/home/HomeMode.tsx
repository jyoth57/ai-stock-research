import { useQuery } from '@tanstack/react-query'
import { fetchScan, fetchMarketOverview } from '@/services/api'
import { useStore } from '@/store'
import {
  TrendingUp, TrendingDown, Zap, Flame, Bot, FlaskConical,
  BarChart3, Star, Activity, ArrowRight,
} from 'lucide-react'
import { AreaChart, Area, ResponsiveContainer, Tooltip } from 'recharts'
import clsx from 'clsx'

export default function HomeMode() {
  const { setMode, setSelectedStock, watchlist } = useStore()
  const { data: scan = [] } = useQuery({ queryKey: ['scan', {}], queryFn: () => fetchScan() })
  const { data: overview }  = useQuery({ queryKey: ['overview'], queryFn: fetchMarketOverview })

  const topGainers  = [...scan].sort((a, b) => (b.pct_1d as number) - (a.pct_1d as number)).slice(0, 5)
  const topLosers   = [...scan].sort((a, b) => (a.pct_1d as number) - (b.pct_1d as number)).slice(0, 5)
  const topBreakouts = scan.filter((s) => s.breakout && s.volume_spike).slice(0, 5)
  const topMomentum  = [...scan].sort((a, b) => (b.momentum_score as number) - (a.momentum_score as number)).slice(0, 5)
  const watchlistData = scan.filter((s) => watchlist.includes(s.symbol as string))

  const kpis = [
    { label: 'Stocks Scanned',  value: scan.length, color: 'text-text-primary', icon: BarChart3 },
    { label: 'Advancing',       value: scan.filter((s) => (s.pct_1d as number) > 0).length, color: 'text-bull', icon: TrendingUp },
    { label: 'Declining',       value: scan.filter((s) => (s.pct_1d as number) < 0).length, color: 'text-bear', icon: TrendingDown },
    { label: 'Volume Spikes',   value: scan.filter((s) => s.volume_spike).length, color: 'text-accent', icon: Zap },
    { label: 'Breakouts',       value: scan.filter((s) => s.breakout).length, color: 'text-gold', icon: Flame },
    { label: 'Score > 80',      value: scan.filter((s) => (s.momentum_score as number) > 80).length, color: 'text-bull', icon: Activity },
  ]

  return (
    <div className="flex flex-col h-full overflow-y-auto p-6 space-y-6 animate-fade-in">
      {/* Welcome */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Good morning, Quant 👋</h1>
          <p className="text-sm text-text-muted mt-0.5">
            {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
            {' · '}NSE markets{' '}
            <span className="text-bull">Live</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setMode('chat')} className="btn-primary flex items-center gap-2">
            <Bot size={14} /> Ask AI
          </button>
          <button onClick={() => setMode('workbench')} className="btn-ghost flex items-center gap-2">
            <FlaskConical size={14} /> Workbench
          </button>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {kpis.map(({ label, value, color, icon: Icon }) => (
          <button key={label} onClick={() => setMode('dashboard')} className="stat-card hover:border-accent/30 transition-all text-left">
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-muted">{label}</span>
              <Icon size={13} className={color} />
            </div>
            <span className={clsx('text-2xl font-bold', color)}>{value.toLocaleString()}</span>
          </button>
        ))}
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Top Gainers */}
        <MiniList
          title="Today's Top Gainers" icon={TrendingUp} iconColor="text-bull"
          items={topGainers} valueKey="pct_1d" valueSuffix="%" positive
          onSelectStock={setSelectedStock} onViewAll={() => setMode('dashboard')}
        />

        {/* Top Losers */}
        <MiniList
          title="Today's Top Losers" icon={TrendingDown} iconColor="text-bear"
          items={topLosers} valueKey="pct_1d" valueSuffix="%" negative
          onSelectStock={setSelectedStock} onViewAll={() => setMode('dashboard')}
        />

        {/* Momentum Leaders */}
        <MiniList
          title="Momentum Leaders" icon={Flame} iconColor="text-gold"
          items={topMomentum} valueKey="momentum_score" valueSuffix="/100"
          onSelectStock={setSelectedStock} onViewAll={() => setMode('dashboard')}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Breakout + Volume Spike */}
        <MiniList
          title="Breakouts with Volume Spike" icon={Zap} iconColor="text-accent"
          items={topBreakouts} valueKey="volume_ratio" valueSuffix="× vol"
          onSelectStock={setSelectedStock} onViewAll={() => setMode('dashboard')}
        />

        {/* Watchlist */}
        <div className="glass rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <div className="flex items-center gap-2">
              <Star size={13} className="text-gold" />
              <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">Watchlist</span>
            </div>
            <button onClick={() => setMode('explorer')} className="btn-ghost text-xs flex items-center gap-1">
              View <ArrowRight size={11} />
            </button>
          </div>
          <div className="divide-y divide-border/30">
            {watchlistData.length === 0 && watchlist.slice(0, 5).map((sym) => (
              <WatchlistRow key={sym} symbol={sym} data={undefined} onSelect={setSelectedStock} />
            ))}
            {watchlistData.map((d) => (
              <WatchlistRow key={d.symbol as string} symbol={d.symbol as string} data={d} onSelect={setSelectedStock} />
            ))}
          </div>
        </div>
      </div>

      {/* AI suggestions */}
      <AISuggestions />
    </div>
  )
}

function MiniList({ title, icon: Icon, iconColor, items, valueKey, valueSuffix, positive, negative, onSelectStock, onViewAll }: {
  title: string; icon: React.ElementType; iconColor: string
  items: Record<string, unknown>[]; valueKey: string; valueSuffix: string
  positive?: boolean; negative?: boolean
  onSelectStock: (s: string) => void; onViewAll: () => void
}) {
  return (
    <div className="glass rounded-2xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Icon size={13} className={iconColor} />
          <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">{title}</span>
        </div>
        <button onClick={onViewAll} className="btn-ghost text-xs flex items-center gap-1">
          All <ArrowRight size={11} />
        </button>
      </div>
      <div className="divide-y divide-border/30">
        {items.map((item) => {
          const val = item[valueKey] as number
          return (
            <button
              key={item.symbol as string}
              onClick={() => onSelectStock(item.symbol as string)}
              className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-hover transition-colors"
            >
              <div className="flex items-center gap-2">
                <TrendingUp size={11} className="text-accent flex-shrink-0" />
                <span className="text-sm font-medium text-text-primary">{item.symbol as string}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-text-muted font-mono">₹{(item.last_close as number)?.toFixed(2)}</span>
                <span className={clsx(
                  'text-xs font-mono font-semibold',
                  positive || val > 0 ? 'text-bull' : negative || val < 0 ? 'text-bear' : 'text-accent'
                )}>
                  {typeof val === 'number' && valueKey === 'pct_1d' && val > 0 ? '+' : ''}
                  {val?.toFixed(valueKey === 'momentum_score' ? 0 : 2)}{valueSuffix}
                </span>
              </div>
            </button>
          )
        })}
        {items.length === 0 && (
          <div className="px-4 py-6 text-xs text-text-muted text-center">No data — run the screener first</div>
        )}
      </div>
    </div>
  )
}

function WatchlistRow({ symbol, data, onSelect }: { symbol: string; data: Record<string, unknown> | undefined; onSelect: (s: string) => void }) {
  const pct = data?.pct_1d as number | undefined
  return (
    <button onClick={() => onSelect(symbol)} className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-hover transition-colors">
      <span className="text-sm font-medium text-text-primary">{symbol}</span>
      <div className="flex items-center gap-3">
        {data?.last_close && <span className="text-xs font-mono text-text-muted">₹{(data.last_close as number).toFixed(2)}</span>}
        {pct != null
          ? <span className={clsx('text-xs font-mono font-semibold', pct >= 0 ? 'text-bull' : 'text-bear')}>{pct > 0 ? '+' : ''}{pct.toFixed(2)}%</span>
          : <span className="text-xs text-text-muted">—</span>
        }
      </div>
    </button>
  )
}

function AISuggestions() {
  const { setMode } = useStore()
  const prompts = [
    'Which stocks had the highest probability of a big move this week?',
    'Categorize all stocks that moved >8% by reason',
    'Find common characteristics before large volume spikes',
    'Show me the strongest sector rotation trends this month',
  ]
  return (
    <div className="glass rounded-2xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Bot size={13} className="text-accent" />
        <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">AI Research Suggestions</span>
      </div>
      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-2">
        {prompts.map((p) => (
          <button
            key={p}
            onClick={() => {
              useStore.getState().addMessage({ id: Date.now().toString(), role: 'user', content: p, timestamp: new Date() })
              setMode('chat')
            }}
            className="text-left text-xs px-4 py-3 glass rounded-xl border border-border hover:border-accent/30 hover:bg-surface-hover transition-all text-text-secondary hover:text-text-primary"
          >
            <span className="text-accent mr-1.5">↗</span>{p}
          </button>
        ))}
      </div>
    </div>
  )
}
