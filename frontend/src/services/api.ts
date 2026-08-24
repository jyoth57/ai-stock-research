import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 60_000 })

// ── Screener ──────────────────────────────────────────────────────────────
export const fetchScan = (params?: Record<string, unknown>) =>
  api.get('/screener/scan', { params }).then((r) => r.data)

export const fetchExtendedScan = (params?: Record<string, unknown>) =>
  api.get('/screener/scan/extended', { params }).then((r) => r.data)

// ── Downloader ────────────────────────────────────────────────────────────
export const fetchUniverses = () =>
  api.get('/downloader/universes').then((r) => r.data)

export const startDownload = (payload: {
  universe: string
  start: string
  end?: string
  interval: string
  rebuild_db: boolean
}) => api.post('/downloader/start', payload).then((r) => r.data)

export const fetchDownloadStatus = () =>
  api.get('/downloader/status').then((r) => r.data)

export const cancelDownload = () =>
  api.post('/downloader/cancel').then((r) => r.data)

// ── Market overview ───────────────────────────────────────────────────────
export const fetchMarketOverview = () =>
  api.get('/market/overview').then((r) => r.data)

export const fetchSectorData = () =>
  api.get('/market/sectors').then((r) => r.data)

// ── Stock detail ──────────────────────────────────────────────────────────
export const fetchOHLCV = (symbol: string) =>
  api.get(`/stocks/${symbol}/ohlcv`).then((r) => r.data)

export const fetchStockSignals = (symbol: string) =>
  api.get(`/stocks/${symbol}/signals`).then((r) => r.data)

// ── AI Chat ───────────────────────────────────────────────────────────────
export const postChat = (question: string, history: { role: string; content: string }[]) =>
  api.post('/chat', { question, history }).then((r) => r.data as {
    answer: string
    data: Record<string, unknown>[]
    charts: unknown[]
    sql?: string
  })

export const fetchSymbolList = () =>
  api.get('/stocks/symbols').then((r) => r.data as string[])

// ── WebSocket chat (streaming) ────────────────────────────────────────────
export function createChatSocket(
  onMessage: (chunk: string) => void,
  onDone: (data: unknown) => void,
  onError: () => void,
): WebSocket {
  const ws = new WebSocket(`ws://${location.host}/ws/chat`)
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (msg.type === 'chunk') onMessage(msg.content)
    else if (msg.type === 'done') onDone(msg.data)
    else if (msg.type === 'error') onError()
  }
  return ws
}
