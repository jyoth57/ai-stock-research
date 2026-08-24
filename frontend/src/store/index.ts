import { create } from 'zustand'

export type Mode = 'home' | 'chat' | 'dashboard' | 'explorer' | 'workbench'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  data?: unknown   // attached table / chart data
  charts?: unknown[]
}

export interface AppState {
  mode: Mode
  setMode: (m: Mode) => void

  selectedStock: string | null
  setSelectedStock: (s: string | null) => void

  sidebarOpen: boolean
  toggleSidebar: () => void

  rightPanelOpen: boolean
  setRightPanelOpen: (v: boolean) => void

  commandPaletteOpen: boolean
  setCommandPaletteOpen: (v: boolean) => void

  chatHistory: ChatMessage[]
  addMessage: (m: ChatMessage) => void
  clearChat: () => void

  activeDashboard: string
  setActiveDashboard: (d: string) => void

  watchlist: string[]
  addToWatchlist: (s: string) => void
  removeFromWatchlist: (s: string) => void
}

export const useStore = create<AppState>((set) => ({
  mode: 'home',
  setMode: (mode) => set({ mode }),

  selectedStock: null,
  setSelectedStock: (selectedStock) => set({ selectedStock, mode: 'explorer' }),

  sidebarOpen: true,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  rightPanelOpen: false,
  setRightPanelOpen: (rightPanelOpen) => set({ rightPanelOpen }),

  commandPaletteOpen: false,
  setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),

  chatHistory: [],
  addMessage: (m) => set((s) => ({ chatHistory: [...s.chatHistory, m] })),
  clearChat: () => set({ chatHistory: [] }),

  activeDashboard: 'overview',
  setActiveDashboard: (activeDashboard) => set({ activeDashboard }),

  watchlist: ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK'],
  addToWatchlist: (s) => set((st) => ({ watchlist: [...new Set([...st.watchlist, s])] })),
  removeFromWatchlist: (s) => set((st) => ({ watchlist: st.watchlist.filter((x) => x !== s) })),
}))
