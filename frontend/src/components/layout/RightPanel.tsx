import { X, TrendingUp, BarChart3, Star, ExternalLink, Info } from 'lucide-react'
import { useStore } from '@/store'
import { useQuery } from '@tanstack/react-query'
import { fetchStockSignals } from '@/services/api'
import clsx from 'clsx'

export default function RightPanel() {
  const { rightPanelOpen, setRightPanelOpen, selectedStock, setSelectedStock, mode } = useStore()

  const { data: signals } = useQuery({
    queryKey: ['signals', selectedStock],
    queryFn: () => fetchStockSignals(selectedStock!),
    enabled: !!selectedStock && rightPanelOpen,
  })

  if (!rightPanelOpen) return null

  return (
    <aside className="w-72 glass-heavy border-l border-border flex flex-col flex-shrink-0 animate-slide-in overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
        <span className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          {selectedStock ? selectedStock : 'Context'}
        </span>
        <button onClick={() => setRightPanelOpen(false)} className="btn-ghost p-1">
          <X size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {selectedStock && signals ? (
          <StockContextPanel symbol={selectedStock} signals={signals} onOpen={() => setSelectedStock(selectedStock)} />
        ) : mode === 'chat' ? (
          <ChatContextPanel />
        ) : (
          <DefaultContextPanel />
        )}
      </div>
    </aside>
  )
}

function StockContextPanel({ symbol, signals, onOpen }: { symbol: string; signals: Record<string, unknown>; onOpen: () => void }) {
  const pct1d = signals?.pct_1d as number
  const score = signals?.momentum_score as number

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-text-primary">{symbol}</h3>
          <span className="text-xs text-text-muted">NSE Equity</span>
        </div>
        <button onClick={onOpen} className="btn-ghost p-1.5">
          <ExternalLink size={13} />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <StatBox label="Last Close" value={`₹${(signals?.last_close as number)?.toFixed(2) ?? '—'}`} />
        <StatBox
          label="1-Day"
          value={pct1d != null ? `${pct1d > 0 ? '+' : ''}${pct1d.toFixed(2)}%` : '—'}
          color={pct1d > 0 ? 'bull' : 'bear'}
        />
        <StatBox label="Vol/Avg" value={`${(signals?.volume_ratio as number)?.toFixed(1) ?? '—'}×`} />
        <StatBox label="Score" value={score != null ? `${score}/100` : '—'} color="accent" />
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">Active Signals</p>
        {[
          { key: 'volume_spike',  label: 'Volume Spike',  color: 'accent' },
          { key: 'breakout',      label: 'Breakout',      color: 'bull' },
          { key: 'near_52w_high', label: 'Near 52W High', color: 'gold' },
          { key: 'above_50dma',   label: 'Above 50 DMA',  color: 'bull' },
          { key: 'big_mover',     label: 'Big Mover >8%', color: 'bear' },
          { key: 'higher_lows',   label: 'Higher Lows',   color: 'bull' },
        ].map(({ key, label, color }) => (
          <div key={key} className={clsx(
            'flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-all',
            signals?.[key] ? 'bg-accent-dim border border-accent/20' : 'bg-bg-100 border border-border opacity-40'
          )}>
            <span className={signals?.[key] ? 'text-text-primary' : 'text-text-muted'}>{label}</span>
            <span className={clsx(
              'font-medium',
              signals?.[key]
                ? color === 'bull'   ? 'text-bull'
                : color === 'bear'   ? 'text-bear'
                : color === 'gold'   ? 'text-gold'
                : 'text-accent'
                : 'text-text-muted'
            )}>
              {signals?.[key] ? '✓' : '—'}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function StatBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="stat-card">
      <span className="text-xs text-text-muted">{label}</span>
      <span className={clsx(
        'font-semibold text-sm',
        color === 'bull' ? 'text-bull' : color === 'bear' ? 'text-bear' : color === 'accent' ? 'text-accent' : 'text-text-primary'
      )}>
        {value}
      </span>
    </div>
  )
}

function ChatContextPanel() {
  return (
    <div className="space-y-3 animate-fade-in">
      <div className="flex items-center gap-2 text-xs text-text-muted">
        <Info size={12} /> AI reasoning will appear here
      </div>
      <div className="glass rounded-lg p-3 text-xs text-text-secondary space-y-2">
        <p className="font-medium text-text-primary">How AI responds:</p>
        <p>• Translates your question into a data query</p>
        <p>• Runs scan / SQL / ML model</p>
        <p>• Returns tables, charts, and explanation</p>
        <p>• Cites the source data used</p>
      </div>
    </div>
  )
}

function DefaultContextPanel() {
  return (
    <div className="space-y-4 animate-fade-in text-xs text-text-muted">
      <p>Select a stock or start a conversation to see context here.</p>
      <div className="space-y-2">
        <p className="font-medium text-text-secondary uppercase tracking-wider">Quick access</p>
        {['RELIANCE', 'TCS', 'HDFCBANK', 'INFY'].map((s) => (
          <button
            key={s}
            onClick={() => useStore.getState().setSelectedStock(s)}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg glass hover:bg-surface-hover transition-colors text-left"
          >
            <TrendingUp size={11} className="text-accent" />
            <span className="text-text-primary">{s}</span>
            <BarChart3 size={11} className="ml-auto text-text-muted" />
          </button>
        ))}
      </div>
    </div>
  )
}
