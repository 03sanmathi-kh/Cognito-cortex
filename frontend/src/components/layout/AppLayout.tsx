import React from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

export const AppLayout: React.FC = () => {
  return (
    <div className="relative flex h-screen w-screen overflow-hidden bg-[var(--background)] text-[var(--foreground)]">
      {/* Ambient background glows matching reference screenshot */}
      <div 
        aria-hidden="true" 
        className="pointer-events-none absolute -top-40 left-1/4 w-[600px] h-[350px] rounded-full bg-gradient-to-br from-[#D946EF]/10 via-[#8B5CF6]/8 to-transparent blur-[120px] z-0" 
      />
      <div 
        aria-hidden="true" 
        className="pointer-events-none absolute top-1/3 -right-20 w-[500px] h-[400px] rounded-full bg-gradient-to-bl from-[#8B5CF6]/8 via-[#D946EF]/5 to-transparent blur-[140px] z-0" 
      />

      {/* Subtle grid pattern overlay */}
      <div 
        aria-hidden="true" 
        className="pointer-events-none absolute inset-0 bg-grid-pattern opacity-60 z-0" 
      />

      {/* Collapsible Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <div className="relative flex flex-col flex-1 min-w-0 h-full overflow-hidden z-10">
        <TopBar />
        
        <main className="flex-1 overflow-y-auto overflow-x-hidden p-6 relative">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
