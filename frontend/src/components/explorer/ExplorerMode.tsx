import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchOHLCV, fetchStockSignals } from '@/services/api'
import { useStore } from '@/store'
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts'
import {
  TrendingUp, BarChart3, DollarSign, FileText, Users, Megaphone,
  Star, StarOff, Bot, Activity, AlertTriangle, ArrowLeft,
} from 'lucide-react'
import clsx from 'clsx'

const TABS = [
  { id: 'overview',    label: 'Overview',         icon: Activity },
  { id: 'price',       label: 'Price',            icon: TrendingUp },
  { id: 'technicals',  label: 'Technicals',       icon: BarChart3 },
  { id: 'financials',  label: 'Financials',       icon: DollarSign },
  { id: 'shareholding',label: 'Shareholding',     icon: Users },
  { id: 'actions',     label: 'Corp. Actions',    icon: Megaphone },
  { id: 'ai',          label: 'AI Summary',       icon: Bot },
]

export default function ExplorerMode() {
  const { selectedStock, setSelectedStock, watchlist, addToWatchlist, removeFromWatchlist, setMode } = useStore()
  const [activeTab, setActiveTab] = useState('overview')
  const inWatchlist = selectedStock ? watchlist.includes(selectedStock) : false

  const { data: ohlcv = [] } = useQuery({
    queryKey: ['ohlcv', selectedStock],
    queryFn: () => fetchOHLCV(selectedStock!),
    enabled: !!selectedStock,
  })

  const { data: signals } = useQuery({
    queryKey: ['signals', selectedStock],
    queryFn: () => fetchStockSignals(selectedStock!),
    enabled: !!selectedStock,
  })

  if (!selectedStock) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6 text-center animate-fade-in">
        <TrendingUp size={48} className="text-text-muted" />
        <div>
          <h3 className="text-lg font-semibold text-text-primary mb-2">No stock selected</h3>
          <p className="text-sm text-text-muted">Search for a stock in the top bar or select one from the screener.</p>
        </div>
        <button onClick={() => setMode('dashboard')} className="btn-primary flex items-center gap-2">
          <BarChart3 size={14} /> Open Screener
        </button>
      </div>
    )
  }

  const lastRow = ohlcv[ohlcv.length - 1] as Record<string, number> | undefined
  const prevRow = ohlcv[ohlcv.length - 2] as Record<string, number> | undefined
  const change = lastRow && prevRow ? ((lastRow.Close - prevRow.Close) / prevRow.Close) * 100 : 0

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Stock header */}
      <div className="flex items-center gap-4 px-6 py-4 border-b border-border flex-shrink-0">
        <button onClick={() => setMode('dashboard')} className="btn-ghost p-1.5">
          <ArrowLeft size={14} />
        </button>

        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-text-primary">{selectedStock}</h2>
            <span className="tag-accent">NSE</span>
            <span className="tag-accent text-xs">EQ</span>
          </div>
          <p className="text-xs text-text-muted mt-0.5">National Stock Exchange of India</p>
        </div>

        {lastRow && (
          <div className="flex items-center gap-6">
            <div>
              <p className="text-2xl font-bold text-text-primary">₹{lastRow.Close?.toFixed(2)}</p>
              <p className={clsx('text-sm font-medium', change >= 0 ? 'text-bull' : 'text-bear')}>
                {change >= 0 ? '+' : ''}{change.toFixed(2)}%
              </p>
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
              <span className="text-text-muted">Open</span>  <span className="text-text-secondary font-mono">₹{lastRow.Open?.toFixed(2)}</span>
              <span className="text-text-muted">High</span>  <span className="text-bull font-mono">₹{lastRow.High?.toFixed(2)}</span>
              <span className="text-text-muted">Low</span>   <span className="text-bear font-mono">₹{lastRow.Low?.toFixed(2)}</span>
              <span className="text-text-muted">Volume</span><span className="text-accent font-mono">{((lastRow.Volume ?? 0) / 1e5).toFixed(1)}L</span>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => inWatchlist ? removeFromWatchlist(selectedStock) : addToWatchlist(selectedStock)}
            className={clsx('btn-ghost flex items-center gap-1.5', inWatchlist && 'text-gold')}
          >
            {inWatchlist ? <Star size={14} fill="currentColor" /> : <StarOff size={14} />}
            <span className="text-xs hidden xl:block">{inWatchlist ? 'Watching' : 'Watch'}</span>
          </button>
          <button onClick={() => {
            useStore.getState().addMessage({ id: Date.now().toString(), role: 'user', content: `Tell me about ${selectedStock} — summarize the recent price action, signals, and give an AI outlook.`, timestamp: new Date() })
            setMode('chat')
          }} className="btn-primary flex items-center gap-1.5 text-xs">
            <Bot size={13} /> Ask AI
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-0.5 px-6 py-2 border-b border-border flex-shrink-0 overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-all',
              activeTab === id
                ? 'bg-accent-dim text-accent border border-accent/20'
                : 'text-text-muted hover:text-text-primary hover:bg-surface-hover'
            )}
          >
            <Icon size={12} /> {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-6">
        {activeTab === 'overview'    && <OverviewTab    symbol={selectedStock} signals={signals} ohlcv={ohlcv} />}
        {activeTab === 'price'       && <PriceTab       symbol={selectedStock} ohlcv={ohlcv} />}
        {activeTab === 'technicals'  && <TechnicalsTab  symbol={selectedStock} signals={signals} ohlcv={ohlcv} />}
        {activeTab === 'financials'  && <FinancialsTab  symbol={selectedStock} />}
        {activeTab === 'shareholding'&& <ShareholdingTab symbol={selectedStock} />}
        {activeTab === 'actions'     && <ActionsTab     symbol={selectedStock} />}
        {activeTab === 'ai'          && <AITab          symbol={selectedStock} />}
      </div>
    </div>
  )
}

// ── Price Chart (TradingView lightweight-charts) ───────────────────────────

function PriceTab({ symbol, ohlcv }: { symbol: string; ohlcv: Record<string, unknown>[] }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || !ohlcv.length) return
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#8b96a7' },
      grid:   { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.07)' },
      timeScale:       { borderColor: 'rgba(255,255,255,0.07)', timeVisible: true },
      width:  containerRef.current.clientWidth,
      height: 420,
    })

    const candles = chart.addCandlestickSeries({
      upColor: '#00d97e', downColor: '#ff4560',
      borderUpColor: '#00d97e', borderDownColor: '#ff4560',
      wickUpColor: '#00d97e', wickDownColor: '#ff4560',
    })

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })

    const candleData = ohlcv.map((d) => ({
      time: new Date(d.Date as string).toISOString().split('T')[0] as `${number}-${number}-${number}`,
      open:  d.Open  as number,
      high:  d.High  as number,
      low:   d.Low   as number,
      close: d.Close as number,
    })).sort((a, b) => a.time.localeCompare(b.time))

    const volData = ohlcv.map((d) => ({
      time:  new Date(d.Date as string).toISOString().split('T')[0] as `${number}-${number}-${number}`,
      value: d.Volume as number,
      color: (d.Close as number) >= (d.Open as number) ? 'rgba(0,217,126,0.4)' : 'rgba(255,69,96,0.4)',
    })).sort((a, b) => a.time.localeCompare(b.time))

    candles.setData(candleData)
    volumeSeries.setData(volData)
    chart.timeScale().fitContent()

    const ro = new ResizeObserver(() => chart.resize(containerRef.current!.clientWidth, 420))
    ro.observe(containerRef.current)
    return () => { chart.remove(); ro.disconnect() }
  }, [ohlcv])

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="glass rounded-2xl p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
            {symbol} — Candlestick + Volume
          </span>
        </div>
        <div ref={containerRef} />
      </div>
    </div>
  )
}

// ── Overview Tab ───────────────────────────────────────────────────────────

function OverviewTab({ symbol, signals, ohlcv }: { symbol: string; signals: Record<string, unknown> | undefined; ohlcv: Record<string, unknown>[] }) {
  const closeArr = ohlcv.map((d) => d.Close as number)
  const high52w = closeArr.length ? Math.max(...closeArr) : 0
  const low52w  = closeArr.length ? Math.min(...closeArr) : 0

  const signalItems = [
    { key: 'volume_spike',  label: 'Volume Spike (>2× avg)',  color: 'accent' },
    { key: 'breakout',      label: 'Breakout above resistance',color: 'bull' },
    { key: 'near_52w_high', label: 'Near 52-week high',       color: 'gold' },
    { key: 'above_50dma',   label: 'Price above 50-day MA',   color: 'bull' },
    { key: 'big_mover',     label: 'Big mover (>8% in 1 day)',color: 'bear' },
    { key: 'higher_lows',   label: 'Higher lows pattern',     color: 'bull' },
  ]

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 animate-fade-in">
      {/* Key metrics */}
      <div className="lg:col-span-2 space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Momentum Score', value: signals ? `${(signals.momentum_score as number).toFixed(0)}/100` : '—', color: 'text-accent' },
            { label: '1-Day Return',   value: signals ? `${(signals.pct_1d as number) > 0 ? '+' : ''}${(signals.pct_1d as number).toFixed(2)}%` : '—', color: (signals?.pct_1d as number) >= 0 ? 'text-bull' : 'text-bear' },
            { label: '20-Day Return',  value: signals ? `${(signals.pct_20d as number) > 0 ? '+' : ''}${(signals.pct_20d as number).toFixed(2)}%` : '—', color: (signals?.pct_20d as number) >= 0 ? 'text-bull' : 'text-bear' },
            { label: 'Vol / Avg',      value: signals ? `${(signals.volume_ratio as number).toFixed(1)}×` : '—', color: 'text-accent' },
            { label: '52W High',       value: high52w ? `₹${high52w.toFixed(2)}` : '—', color: 'text-gold' },
            { label: '52W Low',        value: low52w  ? `₹${low52w.toFixed(2)}`  : '—', color: 'text-bear' },
            { label: 'From 52W High',  value: signals ? `${(signals.pct_from_52w_high as number).toFixed(1)}%` : '—', color: 'text-text-primary' },
            { label: 'Data Points',    value: ohlcv.length.toString(), color: 'text-text-muted' },
          ].map(({ label, value, color }) => (
            <div key={label} className="stat-card">
              <span className="text-xs text-text-muted">{label}</span>
              <span className={clsx('text-base font-bold', color)}>{value}</span>
            </div>
          ))}
        </div>

        {/* Mini price chart */}
        <div className="glass rounded-2xl p-4">
          <p className="text-xs text-text-muted uppercase tracking-wider mb-3">Price history</p>
          <PriceMiniChart ohlcv={ohlcv} />
        </div>
      </div>

      {/* Signals panel */}
      <div className="space-y-3">
        <div className="glass rounded-2xl p-4">
          <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">Active Signals</p>
          <div className="space-y-2">
            {signalItems.map(({ key, label, color }) => {
              const active = signals?.[key] as boolean
              return (
                <div key={key} className={clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-xl border text-xs transition-all',
                  active ? 'border-accent/20 bg-accent-dim' : 'border-border bg-bg-100 opacity-40'
                )}>
                  <div className={clsx(
                    'w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold',
                    active
                      ? color === 'bull' ? 'bg-bull text-bg' : color === 'bear' ? 'bg-bear text-white' : color === 'gold' ? 'bg-gold text-bg' : 'bg-accent text-white'
                      : 'bg-bg-300 text-text-muted'
                  )}>
                    {active ? '✓' : '○'}
                  </div>
                  <span className={active ? 'text-text-primary' : 'text-text-muted'}>{label}</span>
                </div>
              )
            })}
          </div>
        </div>

        <button
          onClick={() => {
            useStore.getState().addMessage({ id: Date.now().toString(), role: 'user', content: `Analyze ${symbol} — explain the momentum signals, recent price action, and give a detailed AI research summary.`, timestamp: new Date() })
            useStore.getState().setMode('chat')
          }}
          className="w-full btn-primary flex items-center justify-center gap-2"
        >
          <Bot size={14} /> Generate AI Report
        </button>
      </div>
    </div>
  )
}

function PriceMiniChart({ ohlcv }: { ohlcv: Record<string, unknown>[] }) {
  const data = ohlcv.slice(-60).map((d) => ({ date: d.Date as string, close: d.Close as number }))
  if (!data.length) return <div className="h-32 flex items-center justify-center text-text-muted text-xs">No data</div>

  const { LineChart: LC, Line: L, ResponsiveContainer: RC, Tooltip: T, XAxis: XA } = { LineChart, Line, ResponsiveContainer, Tooltip, XAxis }
  return (
    <RC width="100%" height={120}>
      <LC data={data}>
        <XA dataKey="date" hide />
        <T contentStyle={{ background: '#0f1520', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', fontSize: 11 }}
          formatter={(v: unknown) => [`₹${(v as number).toFixed(2)}`, 'Close']}
          labelFormatter={(l: string) => new Date(l).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })} />
        <L dataKey="close" stroke="#1e90ff" strokeWidth={2} dot={false} />
      </LC>
    </RC>
  )
}

// ── Technicals Tab ─────────────────────────────────────────────────────────

function TechnicalsTab({ signals }: { symbol: string; signals: Record<string, unknown> | undefined; ohlcv: Record<string, unknown>[] }) {
  const rows = [
    { indicator: 'Momentum Score',    value: signals ? `${(signals.momentum_score as number).toFixed(0)}/100` : '—',            interpretation: (signals?.momentum_score as number) > 70 ? 'Strong momentum' : 'Moderate' },
    { indicator: '50-Day MA',         value: signals?.above_50dma ? 'Above' : 'Below',   interpretation: signals?.above_50dma ? 'Bullish' : 'Bearish' },
    { indicator: 'Volume Ratio',      value: signals ? `${(signals.volume_ratio as number).toFixed(1)}×` : '—',               interpretation: (signals?.volume_ratio as number) > 2 ? 'Volume spike' : 'Normal' },
    { indicator: '52W High Distance', value: signals ? `${(signals.pct_from_52w_high as number).toFixed(1)}% below` : '—',    interpretation: (signals?.pct_from_52w_high as number) < 5 ? 'Near high' : 'Away from high' },
    { indicator: 'Breakout',          value: signals?.breakout ? 'Yes' : 'No',           interpretation: signals?.breakout ? 'Above resistance' : 'Below resistance' },
    { indicator: 'Higher Lows',       value: signals?.higher_lows ? 'Yes' : 'No',        interpretation: signals?.higher_lows ? 'Uptrend forming' : 'No clear trend' },
    { indicator: '1-Day Change',      value: signals ? `${(signals.pct_1d as number).toFixed(2)}%` : '—',                    interpretation: (signals?.pct_1d as number) > 8 ? 'Big mover' : 'Normal' },
    { indicator: '20-Day Change',     value: signals ? `${(signals.pct_20d as number).toFixed(2)}%` : '—',                   interpretation: (signals?.pct_20d as number) > 20 ? 'Strong trend' : 'Moderate' },
  ]

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="glass rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-bg-100">
              <th className="px-4 py-3 text-left text-xs text-text-muted font-medium uppercase tracking-wider">Indicator</th>
              <th className="px-4 py-3 text-left text-xs text-text-muted font-medium uppercase tracking-wider">Value</th>
              <th className="px-4 py-3 text-left text-xs text-text-muted font-medium uppercase tracking-wider">Interpretation</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ indicator, value, interpretation }) => (
              <tr key={indicator} className="border-t border-border/30 hover:bg-surface-hover transition-colors">
                <td className="px-4 py-3 text-text-secondary">{indicator}</td>
                <td className="px-4 py-3 font-mono text-text-primary">{value}</td>
                <td className="px-4 py-3">
                  <span className={clsx('text-xs px-2 py-0.5 rounded-full',
                    interpretation.toLowerCase().includes('bull') || interpretation.toLowerCase().includes('strong') || interpretation.toLowerCase().includes('spike') || interpretation.toLowerCase().includes('near') || interpretation.toLowerCase().includes('above') || interpretation.toLowerCase().includes('forming')
                      ? 'bg-bull-dim text-bull'
                      : interpretation.toLowerCase().includes('bear') || interpretation.toLowerCase().includes('below')
                      ? 'bg-bear-dim text-bear'
                      : 'bg-bg-200 text-text-muted'
                  )}>
                    {interpretation}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Placeholder tabs ───────────────────────────────────────────────────────

function PlaceholderTab({ title, icon: Icon, message }: { title: string; icon: React.ElementType; message: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-4 animate-fade-in">
      <Icon size={32} className="text-text-muted" />
      <p className="text-sm text-text-muted">{message}</p>
      <p className="text-xs text-text-muted">Connect to a fundamental data provider to enable this section.</p>
    </div>
  )
}

const FinancialsTab  = ({ symbol }: { symbol: string }) =>
  <PlaceholderTab title="Financials"   icon={DollarSign} message={`Quarterly P&L, Balance Sheet, and Cash Flow for ${symbol}`} />
const ShareholdingTab = ({ symbol }: { symbol: string }) =>
  <PlaceholderTab title="Shareholding" icon={Users}      message={`Promoter, FII, DII, and Retail holding data for ${symbol}`} />
const ActionsTab     = ({ symbol }: { symbol: string }) =>
  <PlaceholderTab title="Corp Actions" icon={Megaphone}  message={`Dividends, Splits, Bonuses, and Announcements for ${symbol}`} />

function AITab({ symbol }: { symbol: string }) {
  const { setMode } = useStore()
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-4 animate-fade-in">
      <Bot size={32} className="text-accent" />
      <p className="text-sm text-text-secondary">Get an AI-generated research summary for {symbol}</p>
      <button
        onClick={() => {
          useStore.getState().addMessage({ id: Date.now().toString(), role: 'user', content: `Generate a comprehensive AI research report for ${symbol}: price action, signals, momentum analysis, risk factors, and probability of a 10% move in the next 5 days.`, timestamp: new Date() })
          setMode('chat')
        }}
        className="btn-primary flex items-center gap-2"
      >
        <Bot size={14} /> Generate AI Research Report
      </button>
    </div>
  )
}

// Re-export charts used above (needed since recharts is used inline)
import { LineChart, Line, ResponsiveContainer, Tooltip, XAxis } from 'recharts'
