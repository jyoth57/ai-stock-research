import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchScan, fetchExtendedScan, fetchMarketOverview, fetchSectorData,
         startDownload, fetchDownloadStatus, cancelDownload } from '@/services/api'
import { useStore } from '@/store'
import {
  BarChart, Bar, LineChart, Line, Treemap, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell, ScatterChart, Scatter, ZAxis,
} from 'recharts'
import { TrendingUp, TrendingDown, Activity, BarChart3, Flame, Zap, Filter, Download, RefreshCw, Database, Calendar, CheckCircle2, XCircle, Loader2, StopCircle } from 'lucide-react'
import clsx from 'clsx'

const DASHBOARDS = [
  { id: 'overview',    label: 'Market Overview',   icon: Activity },
  { id: 'momentum',   label: 'Momentum',           icon: TrendingUp },
  { id: 'breakout',   label: 'Breakouts',          icon: Zap },
  { id: 'volume',     label: 'Volume',             icon: BarChart3 },
  { id: 'sectors',    label: 'Sector Rotation',    icon: Flame },
  { id: 'deepscan',  label: 'Deep Scan',           icon: Filter },
  { id: 'data',      label: 'Data Update',         icon: Database },
]

export default function DashboardMode() {
  const { activeDashboard, setActiveDashboard } = useStore()
  const [filters, setFilters] = useState({ volumeSpike: false, above50dma: false, nearHigh: false })

  const { data: scan = [], isLoading: scanLoading, refetch } = useQuery({
    queryKey: ['scan', filters],
    queryFn: () => fetchScan({ volume_spike: filters.volumeSpike, above_50dma: filters.above50dma, near_high: filters.nearHigh }),
  })

  const { data: overview } = useQuery({ queryKey: ['overview'], queryFn: fetchMarketOverview })
  const { data: sectors = [] } = useQuery({ queryKey: ['sectors'], queryFn: fetchSectorData })

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Sub-nav */}
      <div className="flex items-center gap-1 px-6 py-3 border-b border-border flex-shrink-0 overflow-x-auto">
        {DASHBOARDS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveDashboard(id)}
            className={clsx(
              'flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-all',
              activeDashboard === id
                ? 'bg-accent text-white shadow-accent'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
            )}
          >
            <Icon size={12} /> {label}
          </button>
        ))}

        <div className="ml-auto flex items-center gap-2 flex-shrink-0">
          {/* Quick filters */}
          {[
            { key: 'volumeSpike' as const, label: 'Vol Spike' },
            { key: 'above50dma' as const, label: '>50 DMA' },
            { key: 'nearHigh' as const, label: 'Near High' },
          ].map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setFilters((f) => ({ ...f, [key]: !f[key] }))}
              className={clsx(
                'text-xs px-3 py-1.5 rounded-lg border transition-all',
                filters[key]
                  ? 'bg-accent-dim border-accent/40 text-accent'
                  : 'border-border text-text-muted hover:border-accent/30'
              )}
            >
              {label}
            </button>
          ))}
          <button onClick={() => refetch()} className="btn-ghost p-1.5"><RefreshCw size={13} /></button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {activeDashboard === 'overview'  && <OverviewDashboard scan={scan} overview={overview} sectors={sectors} />}
        {activeDashboard === 'momentum' && <MomentumDashboard scan={scan} loading={scanLoading} />}
        {activeDashboard === 'breakout' && <BreakoutDashboard scan={scan} loading={scanLoading} />}
        {activeDashboard === 'volume'   && <VolumeDashboard scan={scan} loading={scanLoading} />}
        {activeDashboard === 'sectors'  && <SectorsDashboard sectors={sectors} />}
        {activeDashboard === 'deepscan' && <DeepScanDashboard />}
        {activeDashboard === 'data'     && <DataUpdateDashboard />}
      </div>
    </div>
  )
}

// ── Overview ───────────────────────────────────────────────────────────────

function OverviewDashboard({ scan, overview, sectors }: { scan: Record<string, unknown>[]; overview: Record<string, unknown> | undefined; sectors: Record<string, unknown>[] }) {
  const total   = scan.length
  const bullish = scan.filter((s) => (s.pct_1d as number) > 0).length
  const bearish = scan.filter((s) => (s.pct_1d as number) < 0).length
  const spikes  = scan.filter((s) => s.volume_spike).length
  const breaks  = scan.filter((s) => s.breakout).length

  const kpis = [
    { label: 'Total Stocks',    value: total,   icon: BarChart3,   color: 'text-text-primary' },
    { label: 'Advancing',       value: bullish, icon: TrendingUp,  color: 'text-bull' },
    { label: 'Declining',       value: bearish, icon: TrendingDown,color: 'text-bear' },
    { label: 'Volume Spikes',   value: spikes,  icon: Zap,         color: 'text-accent' },
    { label: 'Breakouts Today', value: breaks,  icon: Flame,       color: 'text-gold' },
  ]

  return (
    <div className="space-y-6 animate-fade-in">
      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {kpis.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="stat-card">
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-muted">{label}</span>
              <Icon size={14} className={color} />
            </div>
            <span className={clsx('text-2xl font-bold', color)}>{value.toLocaleString()}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top movers */}
        <Panel title="Top Movers Today" icon={TrendingUp}>
          <TopMoversChart data={scan} />
        </Panel>

        {/* Score distribution */}
        <Panel title="Momentum Score Distribution" icon={BarChart3}>
          <ScoreHistogram data={scan} />
        </Panel>
      </div>

      {/* Sector heatmap */}
      <Panel title="Sector Heatmap" icon={Flame}>
        <SectorHeatmap sectors={sectors} />
      </Panel>
    </div>
  )
}

function TopMoversChart({ data }: { data: Record<string, unknown>[] }) {
  const movers = [...data]
    .sort((a, b) => Math.abs(b.pct_1d as number) - Math.abs(a.pct_1d as number))
    .slice(0, 15)
    .map((d) => ({ name: d.symbol as string, value: d.pct_1d as number }))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={movers} margin={{ top: 5, right: 5, left: 0, bottom: 40 }}>
        <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#8b96a7' }} axisLine={false} angle={-45} textAnchor="end" />
        <YAxis tick={{ fontSize: 10, fill: '#8b96a7' }} axisLine={false} tickLine={false}
               tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`} />
        <Tooltip
          contentStyle={{ background: '#0f1520', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', fontSize: 12 }}
          formatter={(v: unknown) => [`${(v as number).toFixed(2)}%`, '1D Change']}
        />
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
          {movers.map((m, i) => <Cell key={i} fill={m.value >= 0 ? '#00d97e' : '#ff4560'} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function ScoreHistogram({ data }: { data: Record<string, unknown>[] }) {
  const buckets = Array.from({ length: 10 }, (_, i) => ({
    range: `${i * 10}–${(i + 1) * 10}`,
    count: data.filter((d) => {
      const s = d.momentum_score as number
      return s >= i * 10 && s < (i + 1) * 10
    }).length,
  }))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={buckets} margin={{ top: 5, right: 5, left: 0, bottom: 5 }}>
        <XAxis dataKey="range" tick={{ fontSize: 10, fill: '#8b96a7' }} axisLine={false} />
        <YAxis tick={{ fontSize: 10, fill: '#8b96a7' }} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={{ background: '#0f1520', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', fontSize: 12 }}
        />
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          {buckets.map((b, i) => (
            <Cell key={i} fill={`hsl(${180 + i * 15}, 70%, ${40 + i * 3}%)`} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function SectorHeatmap({ sectors }: { sectors: Record<string, unknown>[] }) {
  if (!sectors.length) {
    // fallback demo data
    const demo = [
      { name: 'IT',        size: 25, avg_pct: 1.8 },
      { name: 'Banking',   size: 22, avg_pct: -0.4 },
      { name: 'FMCG',      size: 15, avg_pct: 0.7 },
      { name: 'Auto',      size: 12, avg_pct: 2.1 },
      { name: 'Pharma',    size: 10, avg_pct: -1.2 },
      { name: 'Infra',     size: 8,  avg_pct: 3.4 },
      { name: 'Defence',   size: 5,  avg_pct: 4.1 },
      { name: 'Renewable', size: 3,  avg_pct: 2.8 },
    ]
    return <SectorTreemap data={demo} />
  }
  return <SectorTreemap data={sectors as { name: string; size: number; avg_pct: number }[]} />
}

interface SectorNode { name: string; size: number; avg_pct: number }

function SectorTreemap({ data }: { data: SectorNode[] }) {
  const COLORS = data.map((d) => {
    const pct = d.avg_pct
    if (pct > 2)  return '#00d97e'
    if (pct > 0)  return '#00a86b'
    if (pct > -1) return '#ff7f50'
    return '#ff4560'
  })

  return (
    <ResponsiveContainer width="100%" height={240}>
      <Treemap data={data} dataKey="size" aspectRatio={4 / 3} stroke="#0f1520"
        content={({ x, y, width, height, index, name, ...rest }) => {
          const item = data[index as number]
          const fill = COLORS[index as number]
          if ((width as number) < 30 || (height as number) < 20) return <g />
          return (
            <g>
              <rect x={x} y={y} width={width} height={height} fill={fill} fillOpacity={0.85} rx={4} />
              <text x={(x as number) + (width as number) / 2} y={(y as number) + (height as number) / 2 - 6}
                textAnchor="middle" fill="white" fontSize={12} fontWeight={600}>
                {name}
              </text>
              <text x={(x as number) + (width as number) / 2} y={(y as number) + (height as number) / 2 + 10}
                textAnchor="middle" fill="rgba(255,255,255,0.8)" fontSize={10}>
                {item?.avg_pct > 0 ? '+' : ''}{item?.avg_pct?.toFixed(1)}%
              </text>
            </g>
          )
        }}
      />
    </ResponsiveContainer>
  )
}

// ── Momentum Dashboard ─────────────────────────────────────────────────────

function MomentumDashboard({ scan, loading }: { scan: Record<string, unknown>[]; loading: boolean }) {
  const { setSelectedStock } = useStore()
  const top = [...scan].sort((a, b) => (b.momentum_score as number) - (a.momentum_score as number)).slice(0, 50)

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Panel title="Top 20 by Score" icon={TrendingUp}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={top.slice(0, 20)} layout="vertical" margin={{ top: 0, right: 40, left: 60, bottom: 0 }}>
              <XAxis type="number" tick={{ fontSize: 10, fill: '#8b96a7' }} axisLine={false} domain={[0, 100]} />
              <YAxis type="category" dataKey="symbol" tick={{ fontSize: 10, fill: '#e2e8f0' }} axisLine={false} tickLine={false} width={55} />
              <Tooltip contentStyle={{ background: '#0f1520', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', fontSize: 12 }} />
              <Bar dataKey="momentum_score" radius={[0, 4, 4, 0]}>
                {top.slice(0, 20).map((_, i) => <Cell key={i} fill={`hsl(${200 + i * 8}, 70%, 55%)`} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Score vs 20D Return" icon={Activity}>
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
              <XAxis dataKey="pct_20d" type="number" tick={{ fontSize: 10, fill: '#8b96a7' }} axisLine={false}
                tickFormatter={(v: number) => `${v.toFixed(0)}%`} label={{ value: '20D %', position: 'insideBottom', offset: -5, fill: '#8b96a7', fontSize: 10 }} />
              <YAxis dataKey="momentum_score" type="number" tick={{ fontSize: 10, fill: '#8b96a7' }} axisLine={false}
                label={{ value: 'Score', angle: -90, position: 'insideLeft', fill: '#8b96a7', fontSize: 10 }} />
              <ZAxis dataKey="volume_ratio" range={[30, 200]} />
              <Tooltip
                contentStyle={{ background: '#0f1520', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', fontSize: 12 }}
                content={({ payload }) => {
                  const d = payload?.[0]?.payload as Record<string, unknown>
                  if (!d) return null
                  return (
                    <div className="glass p-2 text-xs space-y-0.5">
                      <p className="font-semibold text-text-primary">{d.symbol as string}</p>
                      <p className="text-text-muted">Score: {(d.momentum_score as number).toFixed(0)}</p>
                      <p className="text-bull">20D: +{(d.pct_20d as number).toFixed(1)}%</p>
                    </div>
                  )
                }}
              />
              <Scatter data={top} fill="#1e90ff" fillOpacity={0.7} />
            </ScatterChart>
          </ResponsiveContainer>
        </Panel>
      </div>

      <StocksTable
        data={top}
        onSelect={setSelectedStock}
        columns={['symbol', 'last_close', 'pct_1d', 'pct_5d', 'pct_20d', 'volume_ratio', 'momentum_score']}
        loading={loading}
      />
    </div>
  )
}

// ── Breakout Dashboard ─────────────────────────────────────────────────────

function BreakoutDashboard({ scan, loading }: { scan: Record<string, unknown>[]; loading: boolean }) {
  const { setSelectedStock } = useStore()
  const breakouts = scan.filter((s) => s.breakout).sort((a, b) => (b.momentum_score as number) - (a.momentum_score as number))

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Total Breakouts',     value: breakouts.length },
          { label: 'With Volume Spike',   value: breakouts.filter((s) => s.volume_spike).length },
          { label: 'Above 50 DMA',        value: breakouts.filter((s) => s.above_50dma).length },
          { label: 'Near 52W High',       value: breakouts.filter((s) => s.near_52w_high).length },
        ].map(({ label, value }) => (
          <div key={label} className="stat-card">
            <span className="text-xs text-text-muted">{label}</span>
            <span className="text-2xl font-bold text-bull">{value}</span>
          </div>
        ))}
      </div>
      <StocksTable
        data={breakouts}
        onSelect={setSelectedStock}
        columns={['symbol', 'last_close', 'pct_1d', 'pct_20d', 'volume_ratio', 'above_50dma', 'near_52w_high', 'momentum_score']}
        loading={loading}
      />
    </div>
  )
}

// ── Volume Dashboard ────────────────────────────────────────────────────────

function VolumeDashboard({ scan, loading }: { scan: Record<string, unknown>[]; loading: boolean }) {
  const { setSelectedStock } = useStore()
  const spikes = [...scan].filter((s) => s.volume_spike).sort((a, b) => (b.volume_ratio as number) - (a.volume_ratio as number))

  return (
    <div className="space-y-6 animate-fade-in">
      <Panel title="Volume Ratio Distribution (top 30)" icon={BarChart3}>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={spikes.slice(0, 30)} margin={{ top: 5, right: 5, left: 0, bottom: 40 }}>
            <XAxis dataKey="symbol" tick={{ fontSize: 9, fill: '#8b96a7' }} axisLine={false} angle={-45} textAnchor="end" />
            <YAxis tick={{ fontSize: 10, fill: '#8b96a7' }} axisLine={false} tickLine={false}
              tickFormatter={(v: number) => `${v.toFixed(0)}×`} />
            <Tooltip contentStyle={{ background: '#0f1520', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', fontSize: 12 }}
              formatter={(v: unknown) => [`${(v as number).toFixed(1)}×`, 'Vol/Avg']} />
            <Bar dataKey="volume_ratio" radius={[4, 4, 0, 0]} fill="#1e90ff" fillOpacity={0.8} />
          </BarChart>
        </ResponsiveContainer>
      </Panel>
      <StocksTable
        data={spikes}
        onSelect={setSelectedStock}
        columns={['symbol', 'last_close', 'pct_1d', 'volume_ratio', 'breakout', 'momentum_score']}
        loading={loading}
      />
    </div>
  )
}
// ── Data Update Dashboard ──────────────────────────────────────────────────

const UNIVERSE_OPTIONS = [
  { value: 'large_cap', label: 'Large Cap',      sub: 'Nifty 50 — 50 stocks' },
  { value: 'mid_cap',   label: 'Mid Cap',         sub: 'Nifty Next 50 — 50 stocks' },
  { value: 'large_mid', label: 'Large + Mid Cap', sub: 'Nifty 100 — 100 stocks' },
  { value: 'all',       label: 'All NSE',         sub: 'Every EQ-series stock (~2 600+)' },
]

const INTERVAL_OPTIONS = [
  { value: '1d', label: 'Daily',  sub: '1 candle per trading session' },
  { value: '1w', label: 'Weekly', sub: 'Resampled from daily bars' },
]

type DownloadStatus = {
  status: string
  pct: number
  completed_days: number
  total_days: number
  symbols_saved: number
  current_date: string | null
  universe_label: string | null
  interval: string | null
  error: string | null
  elapsed_sec: number | null
}

function DataUpdateDashboard() {
  const today     = new Date().toISOString().slice(0, 10)
  const threeM    = new Date(Date.now() - 90 * 86400_000).toISOString().slice(0, 10)
  const oneY      = new Date(Date.now() - 365 * 86400_000).toISOString().slice(0, 10)
  const twoY      = new Date(Date.now() - 730 * 86400_000).toISOString().slice(0, 10)
  const fiveY     = new Date(Date.now() - 5 * 365 * 86400_000).toISOString().slice(0, 10)

  const [universe,   setUniverse]   = useState('large_cap')
  const [interval,   setInterval_]  = useState('1d')
  const [startDate,  setStartDate]  = useState(threeM)
  const [endDate,    setEndDate]    = useState(today)
  const [rebuildDb,  setRebuildDb]  = useState(true)

  const [jobStatus, setJobStatus] = useState<DownloadStatus | null>(null)
  const [polling,   setPolling]   = useState(false)
  const [error,     setError]     = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Polling loop ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!polling) {
      if (pollRef.current) clearInterval(pollRef.current)
      return
    }
    const tick = async () => {
      try {
        const s = await fetchDownloadStatus()
        setJobStatus(s)
        if (!['running', 'building_db'].includes(s.status)) {
          setPolling(false)
        }
      } catch { /* network hiccup — keep polling */ }
    }
    tick()
    pollRef.current = setInterval(tick, 1000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [polling])

  const handleStart = async () => {
    setError(null)
    try {
      await startDownload({
        universe,
        start: startDate,
        end: endDate,
        interval,
        rebuild_db: rebuildDb,
      })
      setPolling(true)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to start download'
      setError(msg)
    }
  }

  const handleCancel = async () => {
    try {
      await cancelDownload()
    } catch { /* ignore */ }
  }

  const isRunning = jobStatus && ['running', 'building_db'].includes(jobStatus.status)
  const isDone    = jobStatus?.status === 'done'
  const isFailed  = jobStatus?.status === 'error'
  const isCancelled = jobStatus?.status === 'cancelled'

  // Quick preset buttons
  const PRESETS = [
    { label: '3 Months', start: threeM },
    { label: '1 Year',   start: oneY  },
    { label: '2 Years',  start: twoY  },
    { label: '5 Years',  start: fiveY },
  ]

  return (
    <div className="space-y-6 animate-fade-in max-w-3xl">
      <div className="glass rounded-2xl p-6 space-y-6">

        {/* Header */}
        <div className="flex items-center gap-3">
          <Database size={18} className="text-accent" />
          <div>
            <h2 className="text-sm font-semibold text-text-primary">NSE Data Update</h2>
            <p className="text-xs text-text-muted mt-0.5">
              Downloads from NSE Bhavcopy archives. Data is merged with existing Parquets.
            </p>
          </div>
        </div>

        {/* Universe */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Universe</label>
          <div className="grid grid-cols-2 gap-2">
            {UNIVERSE_OPTIONS.map(opt => (
              <button key={opt.value} onClick={() => setUniverse(opt.value)}
                disabled={!!isRunning}
                className={clsx(
                  'text-left px-4 py-3 rounded-xl border transition-all',
                  universe === opt.value
                    ? 'bg-accent-dim border-accent/50 text-text-primary'
                    : 'border-border text-text-secondary hover:border-accent/30 hover:bg-surface-hover',
                  isRunning && 'opacity-50 cursor-not-allowed',
                )}>
                <div className="text-xs font-semibold">{opt.label}</div>
                <div className="text-[10px] text-text-muted mt-0.5">{opt.sub}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Interval */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Interval</label>
          <div className="flex gap-2">
            {INTERVAL_OPTIONS.map(opt => (
              <button key={opt.value} onClick={() => setInterval_(opt.value)}
                disabled={!!isRunning}
                className={clsx(
                  'flex-1 text-left px-4 py-3 rounded-xl border transition-all',
                  interval === opt.value
                    ? 'bg-accent-dim border-accent/50 text-text-primary'
                    : 'border-border text-text-secondary hover:border-accent/30 hover:bg-surface-hover',
                  isRunning && 'opacity-50 cursor-not-allowed',
                )}>
                <div className="text-xs font-semibold">{opt.label}</div>
                <div className="text-[10px] text-text-muted mt-0.5">{opt.sub}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Date range */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Date Range</label>
            <div className="flex gap-1.5">
              {PRESETS.map(p => (
                <button key={p.label} onClick={() => { setStartDate(p.start); setEndDate(today) }}
                  disabled={!!isRunning}
                  className="text-[10px] px-2 py-1 rounded border border-border text-text-muted hover:border-accent/40 hover:text-accent transition-all disabled:opacity-50">
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex-1 space-y-1">
              <span className="text-[10px] text-text-muted flex items-center gap-1"><Calendar size={10} /> From</span>
              <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
                max={endDate} disabled={!!isRunning}
                className="w-full bg-bg-200 border border-border rounded-lg px-3 py-2 text-xs text-text-primary focus:border-accent outline-none disabled:opacity-50" />
            </div>
            <div className="pt-5 text-text-muted text-xs">→</div>
            <div className="flex-1 space-y-1">
              <span className="text-[10px] text-text-muted flex items-center gap-1"><Calendar size={10} /> To</span>
              <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
                min={startDate} max={today} disabled={!!isRunning}
                className="w-full bg-bg-200 border border-border rounded-lg px-3 py-2 text-xs text-text-primary focus:border-accent outline-none disabled:opacity-50" />
            </div>
          </div>
        </div>

        {/* Options */}
        <div className="flex items-center gap-3">
          <button onClick={() => setRebuildDb(v => !v)} disabled={!!isRunning}
            className={clsx(
              'flex items-center gap-2 px-3 py-2 rounded-lg border text-xs transition-all',
              rebuildDb
                ? 'bg-accent-dim border-accent/40 text-accent'
                : 'border-border text-text-muted hover:border-accent/30',
              isRunning && 'opacity-50 cursor-not-allowed',
            )}>
            <div className={clsx('w-3.5 h-3.5 rounded border flex items-center justify-center transition-all',
              rebuildDb ? 'bg-accent border-accent' : 'border-border')}>
              {rebuildDb && <CheckCircle2 size={10} className="text-white" />}
            </div>
            Rebuild signals DB after download
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 text-xs text-red-400">
            <XCircle size={14} className="mt-0.5 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-3">
          {!isRunning ? (
            <button onClick={handleStart}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-accent text-white text-xs font-semibold hover:bg-accent/90 transition-all shadow-accent">
              <Database size={13} /> Start Download
            </button>
          ) : (
            <button onClick={handleCancel}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-red-500/20 border border-red-500/40 text-red-400 text-xs font-semibold hover:bg-red-500/30 transition-all">
              <StopCircle size={13} /> Cancel
            </button>
          )}
        </div>
      </div>

      {/* Progress panel — shown whenever a job exists */}
      {jobStatus && (
        <div className="glass rounded-2xl p-6 space-y-4">
          {/* Status header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {isRunning    && <Loader2 size={14} className="text-accent animate-spin" />}
              {isDone       && <CheckCircle2 size={14} className="text-bull" />}
              {isFailed     && <XCircle size={14} className="text-bear" />}
              {isCancelled  && <StopCircle size={14} className="text-yellow-400" />}
              <span className={clsx('text-xs font-semibold capitalize',
                isRunning   ? 'text-accent'        :
                isDone      ? 'text-bull'           :
                isFailed    ? 'text-bear'           :
                isCancelled ? 'text-yellow-400'     : 'text-text-muted')}>
                {jobStatus.status === 'building_db' ? 'Rebuilding Database…' : jobStatus.status}
              </span>
            </div>
            {jobStatus.elapsed_sec != null && (
              <span className="text-[10px] text-text-muted">{jobStatus.elapsed_sec}s elapsed</span>
            )}
          </div>

          {/* Progress bar */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-[10px] text-text-muted">
              <span>{jobStatus.completed_days} / {jobStatus.total_days} trading days</span>
              <span className="font-mono font-semibold text-accent">{jobStatus.pct}%</span>
            </div>
            <div className="h-2.5 bg-bg-200 rounded-full overflow-hidden">
              <div
                className={clsx('h-full rounded-full transition-all duration-300',
                  isDone    ? 'bg-bull'   :
                  isFailed  ? 'bg-bear'   :
                  'bg-accent'
                )}
                style={{ width: `${jobStatus.pct}%` }}
              />
            </div>
          </div>

          {/* Detail stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: 'Universe',       value: jobStatus.universe_label ?? '—' },
              { label: 'Interval',       value: jobStatus.interval === '1d' ? 'Daily' : 'Weekly' },
              { label: 'Current Date',   value: jobStatus.current_date ?? '—' },
              { label: 'Symbols Saved',  value: jobStatus.symbols_saved > 0 ? jobStatus.symbols_saved.toLocaleString() : '—' },
            ].map(({ label, value }) => (
              <div key={label} className="bg-bg-200/50 rounded-lg px-3 py-2.5">
                <div className="text-[10px] text-text-muted">{label}</div>
                <div className="text-xs font-semibold text-text-primary mt-0.5 truncate" title={String(value)}>{value}</div>
              </div>
            ))}
          </div>

          {/* Error detail */}
          {isFailed && jobStatus.error && (
            <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 text-xs text-red-400 font-mono break-all">
              {jobStatus.error}
            </div>
          )}

          {/* Done message */}
          {isDone && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-400">
              <CheckCircle2 size={14} />
              Download complete — {jobStatus.symbols_saved.toLocaleString()} symbols saved.
              {rebuildDb && ' Signals database has been rebuilt.'}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
// ── Deep Scan Dashboard ───────────────────────────────────────────────────

const TREND_COLORS: Record<string, string> = {
  'Strong Bullish': 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  'Bullish':        'bg-green-500/20   text-green-400   border-green-500/30',
  'Neutral':        'bg-yellow-500/20  text-yellow-400  border-yellow-500/30',
  'Bearish':        'bg-orange-500/20  text-orange-400  border-orange-500/30',
  'Strong Bearish': 'bg-red-500/20     text-red-400     border-red-500/30',
}

const GRADE_COLORS: Record<string, string> = {
  A: 'bg-emerald-500/20 text-emerald-300',
  B: 'bg-blue-500/20    text-blue-300',
  C: 'bg-yellow-500/20  text-yellow-300',
  D: 'bg-orange-500/20  text-orange-300',
  F: 'bg-red-500/20     text-red-300',
}

const BQ_COLORS: Record<string, string> = {
  Excellent: 'text-emerald-400',
  Good:      'text-green-400',
  Average:   'text-yellow-400',
  Poor:      'text-orange-400',
  None:      'text-text-muted',
}

function DeepScanDashboard() {
  const { setSelectedStock } = useStore()
  const [filters, setFilters] = useState({
    breakout: false, hh_hl: false, volume_confirmed: false,
    min_confidence: 0, grade: '',
  })

  const params: Record<string, unknown> = {}
  if (filters.breakout)          params.breakout = true
  if (filters.hh_hl)             params.hh_hl = true
  if (filters.volume_confirmed)  params.volume_confirmed = true
  if (filters.min_confidence > 0) params.min_confidence = filters.min_confidence
  if (filters.grade)             params.grade = filters.grade

  const { data: rows = [], isLoading, refetch } = useQuery({
    queryKey: ['extended_scan', filters],
    queryFn: () => fetchExtendedScan(params),
  })

  const GRADE_OPTIONS = ['', 'A', 'B', 'C', 'D', 'F']
  const CONF_OPTIONS  = [0, 40, 60, 75]

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Filter bar */}
      <div className="glass rounded-2xl px-4 py-3 flex items-center gap-3 flex-wrap">
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">Filters</span>

        {/* Toggle filters */}
        {([
          { key: 'breakout'         as const, label: 'Breakout Only' },
          { key: 'hh_hl'            as const, label: 'HH+HL' },
          { key: 'volume_confirmed' as const, label: 'Vol Confirmed' },
        ] as const).map(({ key, label }) => (
          <button key={key}
            onClick={() => setFilters(f => ({ ...f, [key]: !f[key] }))}
            className={clsx(
              'text-xs px-3 py-1.5 rounded-lg border transition-all',
              filters[key]
                ? 'bg-accent-dim border-accent/40 text-accent'
                : 'border-border text-text-muted hover:border-accent/30'
            )}>
            {label}
          </button>
        ))}

        {/* Grade filter */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-text-muted">Grade</span>
          <select value={filters.grade}
            onChange={e => setFilters(f => ({ ...f, grade: e.target.value }))}
            className="bg-bg-200 border border-border text-xs px-2 py-1.5 rounded-lg text-text-secondary">
            {GRADE_OPTIONS.map(g => <option key={g} value={g}>{g || 'All'}</option>)}
          </select>
        </div>

        {/* Min confidence */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-text-muted">Min Conf</span>
          <select value={filters.min_confidence}
            onChange={e => setFilters(f => ({ ...f, min_confidence: Number(e.target.value) }))}
            className="bg-bg-200 border border-border text-xs px-2 py-1.5 rounded-lg text-text-secondary">
            {CONF_OPTIONS.map(c => <option key={c} value={c}>{c || 'Any'}</option>)}
          </select>
        </div>

        <button onClick={() => refetch()} className="ml-auto btn-ghost p-1.5"><RefreshCw size={13} /></button>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label: 'Total',      value: rows.length },
          { label: 'Grade A',    value: rows.filter((r: Record<string, unknown>) => r.technical_grade === 'A').length },
          { label: 'Grade B',    value: rows.filter((r: Record<string, unknown>) => r.technical_grade === 'B').length },
          { label: 'Breakouts',  value: rows.filter((r: Record<string, unknown>) => r.breakout).length },
          { label: 'Str. Bull',  value: rows.filter((r: Record<string, unknown>) => r.trend_classification === 'Strong Bullish').length },
        ].map(({ label, value }) => (
          <div key={label} className="stat-card">
            <span className="text-xs text-text-muted">{label}</span>
            <span className="text-2xl font-bold text-accent">{value}</span>
          </div>
        ))}
      </div>

      {/* Full analysis table */}
      <DeepScanTable data={rows} onSelect={setSelectedStock} loading={isLoading} />
    </div>
  )
}

function DeepScanTable({ data, onSelect, loading }: {
  data: Record<string, unknown>[]
  onSelect: (s: string) => void
  loading: boolean
}) {
  const [sortCol, setSortCol] = useState('confidence_score')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const sorted = [...data].sort((a, b) => {
    const av = a[sortCol], bv = b[sortCol]
    const cmp = (av ?? '') < (bv ?? '') ? -1 : (av ?? '') > (bv ?? '') ? 1 : 0
    return sortDir === 'desc' ? -cmp : cmp
  })

  const handleSort = (col: string) => {
    if (sortCol === col) setSortDir(d => d === 'desc' ? 'asc' : 'desc')
    else { setSortCol(col); setSortDir('desc') }
  }

  const exportCsv = () => {
    const cols = Object.keys(data[0] ?? {})
    const csv = [cols.join(','), ...data.map(r => cols.map(c => JSON.stringify(r[c] ?? '')).join(','))].join('\n')
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv])); a.download = 'deep_scan.csv'; a.click()
  }

  // column groups for the sticky header
  const GROUPS = [
    { label: 'Identity',    cols: ['symbol', 'price', 'trend_classification', 'technical_grade'] },
    { label: 'EMA Stack',   cols: ['ema20', 'ema50', 'ema200', 'ema20_above_ema50', 'ema50_above_ema200', 'hh_hl', 'dist_from_ema20_pct'] },
    { label: 'Momentum',    cols: ['rsi_14', 'macd_signal', 'adx_14', 'atr_14'] },
    { label: 'Volume',      cols: ['volume_ratio', 'institutional'] },
    { label: 'Breakout',    cols: ['breakout', 'breakout_type', 'breakout_quality', 'breakout_age'] },
    { label: 'Levels',      cols: ['support', 'resistance', 'dist_52w_high_pct', 'rs_vs_nifty_20d'] },
    { label: 'Trade Plan',  cols: ['entry', 'stop_loss', 'target_1', 'target_2', 'target_3', 'risk_reward'] },
    { label: 'Assessment',  cols: ['confidence_score', 'probability_pct', 'max_drawdown_pct', 'holding_period'] },
    { label: 'Verdict',     cols: ['verdict'] },
  ]
  const allCols = GROUPS.flatMap(g => g.cols)

  return (
    <div className="glass rounded-2xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          {data.length.toLocaleString()} stocks — full technical analysis
        </span>
        <button onClick={exportCsv} className="btn-ghost flex items-center gap-1.5 text-xs">
          <Download size={12} /> Export CSV
        </button>
      </div>

      <div className="overflow-auto max-h-[70vh]">
        <table className="w-full text-xs border-collapse">
          {/* Group header row */}
          <thead className="sticky top-0 z-20">
            <tr className="bg-bg-200">
              {GROUPS.map(g => (
                <th key={g.label} colSpan={g.cols.length}
                  className="px-3 py-1.5 text-center text-text-muted font-semibold uppercase tracking-wider text-[10px] border-b border-border/40 border-r border-border/20">
                  {g.label}
                </th>
              ))}
            </tr>
            <tr className="bg-bg-200">
              {allCols.map(c => (
                <th key={c} onClick={() => handleSort(c)}
                  className="px-2 py-2 text-left text-text-muted font-medium whitespace-nowrap cursor-pointer hover:text-accent transition-colors select-none">
                  {COL_LABELS[c] ?? c}
                  {sortCol === c && <span className="ml-1 text-accent">{sortDir === 'desc' ? '↓' : '↑'}</span>}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {loading ? (
              <tr><td colSpan={allCols.length} className="px-3 py-8 text-center text-text-muted">Loading…</td></tr>
            ) : sorted.map((row, i) => (
              <tr key={i} onClick={() => onSelect(row.symbol as string)}
                className="border-t border-border/20 hover:bg-surface-hover transition-colors cursor-pointer">
                {allCols.map(c => {
                  const val = row[c]

                  if (c === 'symbol') return (
                    <td key={c} className="px-2 py-2 font-semibold text-accent whitespace-nowrap sticky left-0 bg-bg-100 z-10">{val as string}</td>
                  )

                  if (c === 'price' || c === 'entry' || c === 'stop_loss' ||
                      c === 'target_1' || c === 'target_2' || c === 'target_3' ||
                      c === 'support' || c === 'resistance') return (
                    <td key={c} className="px-2 py-2 font-mono text-text-primary whitespace-nowrap">₹{(val as number)?.toFixed(2) ?? '—'}</td>
                  )

                  if (c === 'trend_classification') {
                    const cls = TREND_COLORS[val as string] ?? 'bg-bg-200 text-text-muted'
                    return (
                      <td key={c} className="px-2 py-2 whitespace-nowrap">
                        <span className={clsx('px-2 py-0.5 rounded-full text-[10px] font-semibold border', cls)}>
                          {val as string}
                        </span>
                      </td>
                    )
                  }

                  if (c === 'technical_grade') {
                    const cls = GRADE_COLORS[val as string] ?? 'bg-bg-200 text-text-muted'
                    return (
                      <td key={c} className="px-2 py-2">
                        <span className={clsx('inline-flex w-6 h-6 items-center justify-center rounded font-bold text-xs', cls)}>{val as string}</span>
                      </td>
                    )
                  }

                  if (c === 'confidence_score') return (
                    <td key={c} className="px-2 py-2 whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <div className="w-14 h-1.5 bg-bg-200 rounded-full overflow-hidden">
                          <div className="h-full rounded-full"
                            style={{ width: `${val}%`, background: `hsl(${(val as number) * 1.2}, 70%, 55%)` }} />
                        </div>
                        <span className="font-mono text-accent">{val as number}</span>
                      </div>
                    </td>
                  )

                  if (c === 'rsi_14') {
                    const v = val as number
                    const cls = v > 70 ? 'text-rose-400' : v > 55 ? 'text-emerald-400' : v < 30 ? 'text-blue-400' : 'text-text-secondary'
                    return <td key={c} className={clsx('px-2 py-2 font-mono', cls)}>{v?.toFixed(1)}</td>
                  }

                  if (c === 'adx_14') {
                    const v = val as number
                    const lbl = v > 30 ? 'Strong' : v > 20 ? 'Moderate' : 'Weak'
                    return <td key={c} className="px-2 py-2 font-mono text-text-secondary whitespace-nowrap">{v?.toFixed(1)} <span className="text-text-muted text-[10px]">({lbl})</span></td>
                  }

                  if (c === 'macd_signal') {
                    const cls = val === 'Bullish' ? 'text-bull' : val === 'Bearish' ? 'text-bear' : 'text-text-muted'
                    return <td key={c} className={clsx('px-2 py-2 font-medium', cls)}>{val as string}</td>
                  }

                  if (c === 'breakout_quality') {
                    const cls = BQ_COLORS[val as string] ?? 'text-text-muted'
                    return <td key={c} className={clsx('px-2 py-2 font-medium', cls)}>{val as string}</td>
                  }

                  if (c === 'breakout_age') {
                    if (val == null) return <td key={c} className="px-2 py-2 text-text-muted">—</td>
                    const age = val as number
                    // Fresh = green, getting extended = yellow, stale = muted
                    const cls = age <= 2 ? 'text-emerald-400 font-semibold' : age <= 5 ? 'text-yellow-400' : 'text-text-muted'
                    return <td key={c} className={clsx('px-2 py-2 font-mono whitespace-nowrap', cls)}>{age}d</td>
                  }

                  if (c === 'dist_from_ema20_pct') {
                    const v = val as number
                    const cls = v > 0 ? 'text-bull' : v < 0 ? 'text-bear' : 'text-text-muted'
                    return <td key={c} className={clsx('px-2 py-2 font-mono whitespace-nowrap', cls)}>
                      {v > 0 ? '+' : ''}{v?.toFixed(1)}%
                    </td>
                  }

                  if (c === 'risk_reward') return (
                    <td key={c} className={clsx('px-2 py-2 font-mono whitespace-nowrap',
                      (val as number) >= 2 ? 'text-bull' : (val as number) >= 1 ? 'text-yellow-400' : 'text-bear')}>
                      1:{(val as number)?.toFixed(1)}
                    </td>
                  )

                  if (c === 'probability_pct') return (
                    <td key={c} className="px-2 py-2 font-mono text-accent whitespace-nowrap">{val as number}%</td>
                  )

                  if (c === 'max_drawdown_pct') return (
                    <td key={c} className="px-2 py-2 font-mono text-rose-400 whitespace-nowrap">-{(val as number)?.toFixed(1)}%</td>
                  )

                  if (c === 'rs_vs_nifty_20d') {
                    if (val == null) return <td key={c} className="px-2 py-2 text-text-muted">—</td>
                    const v = val as number
                    return <td key={c} className={clsx('px-2 py-2 font-mono', v >= 1 ? 'text-bull' : 'text-bear')}>{v.toFixed(2)}×</td>
                  }

                  if (c === 'volume_ratio') return (
                    <td key={c} className="px-2 py-2 font-mono text-accent whitespace-nowrap">{(val as number)?.toFixed(1)}×</td>
                  )

                  if (typeof val === 'boolean') return (
                    <td key={c} className={clsx('px-2 py-2 font-medium', val ? 'text-bull' : 'text-text-muted')}>{val ? '✓' : '—'}</td>
                  )

                  if (c === 'verdict') return (
                    <td key={c} className="px-2 py-2 text-text-muted max-w-xs truncate" title={val as string}>{val as string}</td>
                  )

                  if (c === 'holding_period') return (
                    <td key={c} className="px-2 py-2 text-text-secondary whitespace-nowrap text-[10px]">{val as string}</td>
                  )

                  if (c === 'institutional') return (
                    <td key={c} className={clsx('px-2 py-2 whitespace-nowrap text-[10px]',
                      val === 'Accumulation' ? 'text-bull' : val === 'Distribution' ? 'text-bear' : 'text-text-muted')}>
                      {val as string}
                    </td>
                  )

                  if (typeof val === 'number') return (
                    <td key={c} className="px-2 py-2 font-mono text-text-secondary">{val.toFixed(2)}</td>
                  )

                  return <td key={c} className="px-2 py-2 text-text-secondary">{String(val ?? '—')}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Sector Rotation ────────────────────────────────────────────────────────

function SectorsDashboard({ sectors }: { sectors: Record<string, unknown>[] }) {
  const demo = sectors.length ? sectors : [
    { name: 'Defence',    avg_pct: 4.1, count: 12, avg_score: 82 },
    { name: 'Renewable',  avg_pct: 3.1, count: 18, avg_score: 78 },
    { name: 'Auto',       avg_pct: 2.1, count: 24, avg_score: 70 },
    { name: 'IT',         avg_pct: 1.8, count: 45, avg_score: 68 },
    { name: 'Infra',      avg_pct: 1.2, count: 30, avg_score: 62 },
    { name: 'FMCG',       avg_pct: 0.7, count: 22, avg_score: 54 },
    { name: 'Banking',    avg_pct: -0.4, count: 38, avg_score: 46 },
    { name: 'Pharma',     avg_pct: -1.2, count: 28, avg_score: 40 },
  ]

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Panel title="Sector Performance" icon={TrendingUp}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={demo} layout="vertical" margin={{ top: 0, right: 60, left: 70, bottom: 0 }}>
              <XAxis type="number" tick={{ fontSize: 10, fill: '#8b96a7' }} axisLine={false}
                tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: '#e2e8f0' }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: '#0f1520', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', fontSize: 12 }} />
              <Bar dataKey="avg_pct" radius={[0, 4, 4, 0]}>
                {demo.map((d, i) => <Cell key={i} fill={(d.avg_pct as number) >= 0 ? '#00d97e' : '#ff4560'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Sector Heatmap" icon={Flame}>
          <SectorTreemap data={demo as SectorNode[]} />
        </Panel>
      </div>
    </div>
  )
}

// ── Shared components ──────────────────────────────────────────────────────

function Panel({ title, icon: Icon, children }: { title: string; icon: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="glass rounded-2xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Icon size={13} className="text-accent" />
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">{title}</span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}

const COL_LABELS: Record<string, string> = {
  symbol: 'Symbol', last_close: 'Close', pct_1d: '1D%', pct_5d: '5D%', pct_20d: '20D%',
  volume_ratio: 'Vol/Avg', momentum_score: 'Score', above_50dma: '>50DMA',
  near_52w_high: 'NearHigh', breakout: 'Breakout', volume_spike: 'VolSpike',
  // Extended technicals
  price: 'Price', trend_classification: 'Trend', ema20: 'EMA20', ema50: 'EMA50',
  ema200: 'EMA200', ema20_above_ema50: '20>50', ema50_above_ema200: '50>200',
  hh_hl: 'HH+HL', dist_from_ema20_pct: 'Δ EMA20%', rsi_14: 'RSI', macd_signal: 'MACD', adx_14: 'ADX',
  atr_14: 'ATR', dist_52w_high_pct: 'Δ52wH%', support: 'S1', resistance: 'R1',
  breakout_type: 'Breakout Type', breakout_quality: 'BQ', breakout_age: 'BO Age',
  rs_vs_nifty_20d: 'RS/Nifty', entry: 'Entry', stop_loss: 'SL',
  target_1: 'T1', target_2: 'T2', target_3: 'T3', risk_reward: 'R:R',
  institutional: 'Institutional', confidence_score: 'Confidence',
  technical_grade: 'Grade', holding_period: 'Hold', max_drawdown_pct: 'MaxDD%',
  probability_pct: 'Prob%', verdict: 'Verdict',
}

function StocksTable({ data, onSelect, columns, loading }: {
  data: Record<string, unknown>[]
  onSelect: (s: string) => void
  columns: string[]
  loading?: boolean
}) {
  const [sortCol, setSortCol] = useState('momentum_score')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [exportCsv] = useState(() => () => {
    const csv = [columns.join(','), ...data.map((r) => columns.map((c) => r[c]).join(','))].join('\n')
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv])); a.download = 'scan.csv'; a.click()
  })

  const sorted = [...data].sort((a, b) => {
    const av = a[sortCol] as number | string | boolean
    const bv = b[sortCol] as number | string | boolean
    const cmp = av < bv ? -1 : av > bv ? 1 : 0
    return sortDir === 'desc' ? -cmp : cmp
  })

  const handleSort = (col: string) => {
    if (sortCol === col) setSortDir((d) => d === 'desc' ? 'asc' : 'desc')
    else { setSortCol(col); setSortDir('desc') }
  }

  return (
    <div className="glass rounded-2xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          {data.length.toLocaleString()} stocks
        </span>
        <button onClick={exportCsv} className="btn-ghost flex items-center gap-1.5 text-xs">
          <Download size={12} /> Export CSV
        </button>
      </div>
      <div className="overflow-auto max-h-96">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-bg-200">
            <tr>
              {columns.map((c) => (
                <th key={c} onClick={() => handleSort(c)}
                  className="px-3 py-2.5 text-left text-text-muted font-medium uppercase tracking-wider whitespace-nowrap cursor-pointer hover:text-accent transition-colors select-none">
                  {COL_LABELS[c] ?? c}
                  {sortCol === c && <span className="ml-1 text-accent">{sortDir === 'desc' ? '↓' : '↑'}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={columns.length} className="px-3 py-8 text-center text-text-muted">Loading…</td></tr>
            ) : sorted.map((row, i) => (
              <tr key={i} onClick={() => onSelect(row.symbol as string)}
                className="border-t border-border/30 hover:bg-surface-hover transition-colors cursor-pointer">
                {columns.map((c) => {
                  const val = row[c]
                  if (c === 'symbol') return (
                    <td key={c} className="px-3 py-2 font-semibold text-accent whitespace-nowrap">{val as string}</td>
                  )
                  if (typeof val === 'boolean') return (
                    <td key={c} className={clsx('px-3 py-2 font-medium', val ? 'text-bull' : 'text-text-muted')}>
                      {val ? '✓' : '—'}
                    </td>
                  )
                  if (c.includes('pct')) return (
                    <td key={c} className={clsx('px-3 py-2 font-mono whitespace-nowrap', (val as number) > 0 ? 'text-bull' : (val as number) < 0 ? 'text-bear' : 'text-text-muted')}>
                      {(val as number) > 0 ? '+' : ''}{(val as number).toFixed(2)}%
                    </td>
                  )
                  if (c === 'volume_ratio') return (
                    <td key={c} className="px-3 py-2 font-mono text-accent whitespace-nowrap">{(val as number).toFixed(1)}×</td>
                  )
                  if (c === 'momentum_score') return (
                    <td key={c} className="px-3 py-2 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-bg-200 rounded-full overflow-hidden">
                          <div className="h-full bg-accent rounded-full" style={{ width: `${val}%` }} />
                        </div>
                        <span className="font-mono text-accent">{(val as number).toFixed(0)}</span>
                      </div>
                    </td>
                  )
                  if (c === 'last_close') return (
                    <td key={c} className="px-3 py-2 font-mono text-text-primary whitespace-nowrap">₹{(val as number).toFixed(2)}</td>
                  )
                  return <td key={c} className="px-3 py-2 text-text-secondary">{String(val ?? '—')}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
