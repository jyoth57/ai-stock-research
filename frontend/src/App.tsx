import { useStore } from '@/store'
import TopBar from '@/components/layout/TopBar'
import Sidebar from '@/components/layout/Sidebar'
import RightPanel from '@/components/layout/RightPanel'
import CommandPalette from '@/components/shared/CommandPalette'
import HomeMode      from '@/components/home/HomeMode'
import ChatMode      from '@/components/chat/ChatMode'
import DashboardMode from '@/components/dashboard/DashboardMode'
import ExplorerMode  from '@/components/explorer/ExplorerMode'
import WorkbenchMode from '@/components/workbench/WorkbenchMode'

export default function App() {
  const { mode, sidebarOpen, toggleSidebar } = useStore()

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-bg">
      <TopBar />

      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <Sidebar />

        {/* Toggle sidebar handle */}
        <button
          onClick={toggleSidebar}
          className="w-1 hover:w-2 bg-transparent hover:bg-accent/30 transition-all cursor-col-resize flex-shrink-0"
          title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        />

        {/* Main content */}
        <main className="flex-1 overflow-hidden relative">
          {mode === 'home'      && <HomeMode />}
          {mode === 'chat'      && <ChatMode />}
          {mode === 'dashboard' && <DashboardMode />}
          {mode === 'explorer'  && <ExplorerMode />}
          {mode === 'workbench' && <WorkbenchMode />}
        </main>

        {/* Right context panel */}
        <RightPanel />
      </div>

      {/* Command Palette (global overlay) */}
      <CommandPalette />
    </div>
  )
}
