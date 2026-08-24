import { useState } from 'react'
import { Play, Plus, Save, Download, Code2, Table2, BarChart3, Bot, Trash2 } from 'lucide-react'
import clsx from 'clsx'
import { useStore } from '@/store'

interface Cell { id: string; type: 'sql' | 'python' | 'markdown' | 'result'; content: string; output?: string; running?: boolean }

const DEFAULT_CELLS: Cell[] = [
  { id: '1', type: 'markdown', content: '## Custom Research Notebook\nAdd SQL, Python, or markdown cells to build your analysis.' },
  { id: '2', type: 'sql', content: 'SELECT symbol, last_close, pct_1d, pct_20d, momentum_score\nFROM scan\nWHERE momentum_score > 80\n  AND volume_spike = true\nORDER BY momentum_score DESC\nLIMIT 20;' },
  { id: '3', type: 'python', content: 'import pandas as pd\n\n# Load scan results\ndf = scan_df[scan_df["momentum_score"] > 80]\nprint(f"Found {len(df)} high-momentum stocks")\ndf.head(10)' },
]

export default function WorkbenchMode() {
  const [cells, setCells] = useState<Cell[]>(DEFAULT_CELLS)
  const [activeCell, setActiveCell] = useState<string | null>(null)
  const { setMode } = useStore()

  const addCell = (type: Cell['type']) => {
    const newCell: Cell = { id: Date.now().toString(), type, content: '' }
    setCells((c) => [...c, newCell])
  }

  const updateCell = (id: string, content: string) =>
    setCells((cs) => cs.map((c) => c.id === id ? { ...c, content } : c))

  const deleteCell = (id: string) =>
    setCells((cs) => cs.filter((c) => c.id !== id))

  const runCell = async (cell: Cell) => {
    setCells((cs) => cs.map((c) => c.id === cell.id ? { ...c, running: true } : c))
    await new Promise((r) => setTimeout(r, 800))
    const output = cell.type === 'sql'
      ? '📊 Query executed — 20 rows returned\n(Connect FastAPI backend to see live results)'
      : cell.type === 'python'
      ? '✅ Code executed\nFound 42 high-momentum stocks\n(Connect FastAPI backend to run live Python)'
      : ''
    setCells((cs) => cs.map((c) => c.id === cell.id ? { ...c, running: false, output } : c))
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-6 py-3 border-b border-border flex-shrink-0">
        <span className="text-sm font-semibold text-text-primary mr-2">Research Workbench</span>
        <div className="flex items-center gap-1">
          {[
            { type: 'sql' as const,      label: 'SQL',      icon: Table2 },
            { type: 'python' as const,   label: 'Python',   icon: Code2 },
            { type: 'markdown' as const, label: 'Note',     icon: BarChart3 },
          ].map(({ type, label, icon: Icon }) => (
            <button key={type} onClick={() => addCell(type)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs glass rounded-lg hover:bg-surface-hover border border-border transition-all text-text-secondary hover:text-text-primary">
              <Plus size={11} /> <Icon size={11} /> {label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => {
            useStore.getState().addMessage({ id: Date.now().toString(), role: 'user', content: 'Help me build a screen for stocks with volume spike + breakout + above 50 DMA. Write the SQL and Python code.', timestamp: new Date() })
            setMode('chat')
          }} className="btn-ghost flex items-center gap-1.5 text-xs">
            <Bot size={12} /> AI Assist
          </button>
          <button className="btn-ghost flex items-center gap-1.5 text-xs"><Save size={12} /> Save</button>
          <button className="btn-ghost flex items-center gap-1.5 text-xs"><Download size={12} /> Export</button>
        </div>
      </div>

      {/* Cells */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {cells.map((cell) => (
          <WorkbenchCell
            key={cell.id}
            cell={cell}
            active={activeCell === cell.id}
            onFocus={() => setActiveCell(cell.id)}
            onBlur={() => setActiveCell(null)}
            onChange={(v) => updateCell(cell.id, v)}
            onRun={() => runCell(cell)}
            onDelete={() => deleteCell(cell.id)}
          />
        ))}

        {/* Add cell */}
        <button onClick={() => addCell('sql')}
          className="w-full py-3 border border-dashed border-border rounded-xl text-xs text-text-muted hover:border-accent/40 hover:text-accent transition-all flex items-center justify-center gap-2">
          <Plus size={13} /> Add cell
        </button>
      </div>
    </div>
  )
}

function WorkbenchCell({ cell, active, onFocus, onBlur, onChange, onRun, onDelete }: {
  cell: Cell; active: boolean
  onFocus: () => void; onBlur: () => void
  onChange: (v: string) => void; onRun: () => void; onDelete: () => void
}) {
  const typeConfig = {
    sql:      { label: 'SQL',      icon: Table2,  color: 'text-gold',   bg: 'bg-gold-dim border-gold/20' },
    python:   { label: 'Python',   icon: Code2,   color: 'text-bull',   bg: 'bg-bull-dim border-bull/20' },
    markdown: { label: 'Markdown', icon: BarChart3,color: 'text-accent', bg: 'bg-accent-dim border-accent/20' },
    result:   { label: 'Result',   icon: BarChart3,color: 'text-text-muted', bg: 'bg-bg-100 border-border' },
  }
  const { label, icon: Icon, color, bg } = typeConfig[cell.type]

  return (
    <div className={clsx('rounded-2xl border overflow-hidden transition-all glass', active ? 'border-accent/30' : 'border-border')}>
      {/* Cell header */}
      <div className={clsx('flex items-center gap-2 px-4 py-2 border-b border-border', bg)}>
        <Icon size={12} className={color} />
        <span className={clsx('text-xs font-mono font-medium', color)}>{label}</span>
        <div className="ml-auto flex items-center gap-1">
          {(cell.type === 'sql' || cell.type === 'python') && (
            <button onClick={onRun} disabled={cell.running}
              className={clsx('flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-all',
                cell.running ? 'bg-bg-200 text-text-muted' : 'bg-accent text-white hover:bg-blue-500')}>
              <Play size={10} className={clsx(cell.running && 'animate-spin')} />
              {cell.running ? 'Running…' : 'Run'}
            </button>
          )}
          <button onClick={onDelete} className="p-1 text-text-muted hover:text-bear transition-colors">
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {/* Editor area */}
      <textarea
        value={cell.content}
        onChange={(e) => onChange(e.target.value)}
        onFocus={onFocus}
        onBlur={onBlur}
        className="w-full bg-transparent px-4 py-3 text-sm font-mono text-text-primary placeholder:text-text-muted
                   outline-none resize-none min-h-[80px] leading-relaxed"
        style={{ fieldSizing: 'content' } as React.CSSProperties}
        placeholder={cell.type === 'sql' ? 'Write SQL…' : cell.type === 'python' ? 'Write Python…' : 'Write markdown…'}
      />

      {/* Output */}
      {cell.output && (
        <div className="border-t border-border bg-bg-100 px-4 py-3">
          <pre className="text-xs text-bull font-mono whitespace-pre-wrap">{cell.output}</pre>
        </div>
      )}
    </div>
  )
}
