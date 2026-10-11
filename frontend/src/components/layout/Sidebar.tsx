import React, { useEffect, useMemo, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Sparkles,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  LogOut,
  Building2,
  ExternalLink,
  AlertTriangle,
} from 'lucide-react'
import { DynamicIcon } from '@/components/DynamicIcon'
import { useUIStore } from '@/store/themeStore'
import { useMetadataStore } from '@/store/metadataStore'
import { cn } from '@/lib/utils'

export const Sidebar: React.FC = () => {
  const { isSidebarCollapsed, toggleSidebar, setSidebarCollapsed } = useUIStore()
  const location = useLocation()
  const { app, directories, pages, loading, error, fetchMetadata } = useMetadataStore()

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 1024) {
        setSidebarCollapsed(true)
      }
    }
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [setSidebarCollapsed])

  const directoryGroups = useMemo(() => {
    return (directories ?? []).map((directory) => {
      const grouped = new Map<string, Array<typeof pages[number]>>()

      pages
        .filter((page) => page.directory === directory.id)
        .forEach((page) => {
          const key = page.subdirectory || 'general'
          const current = grouped.get(key) ?? []
          current.push(page)
          grouped.set(key, current)
        })

      const subdirectories = (directory.subdirectories ?? [])
        .map((subdirectory) => ({
          ...subdirectory,
          pages: grouped.get(subdirectory.id) ?? [],
        }))
        .filter((subdirectory) => subdirectory.pages.length > 0)

      return {
        ...directory,
        subdirectories,
      }
    }).filter((directory) => directory.subdirectories.length > 0)
  }, [directories, pages])

  const [openSections, setOpenSections] = useState<Record<string, boolean>>({})

  useEffect(() => {
    const next: Record<string, boolean> = {}
    const activePath = location.pathname

    directoryGroups.forEach((directory) => {
      next[directory.id] = directory.subdirectories.some((subdirectory) =>
        (subdirectory.pages ?? []).some((page) => activePath === page.route || activePath.startsWith(page.route))
      ) || activePath === '/'
    })

    setOpenSections((previous) => ({ ...previous, ...next }))
  }, [directoryGroups, location.pathname])

  const toggleSection = (sectionId: string) => {
    if (isSidebarCollapsed) {
      toggleSidebar()
    }
    setOpenSections((prev) => ({ ...prev, [sectionId]: !prev[sectionId] }))
  }

  if (loading) {
    return (
      <motion.aside
        initial={false}
        animate={{ width: isSidebarCollapsed ? 76 : 264 }}
        transition={{ duration: 0.25, ease: 'easeInOut' }}
        className="relative flex flex-col h-screen shrink-0 z-30 bg-[var(--sidebar-bg)] border-r border-[var(--sidebar-border)]"
      >
        <div className="h-16 px-4 flex items-center justify-between border-b border-[var(--border)]">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-white/[0.06] animate-pulse" />
            {!isSidebarCollapsed && <div className="h-6 w-24 rounded-lg bg-white/[0.06] animate-pulse" />}
          </div>
        </div>
        <div className="flex-1 px-3 py-4 space-y-4">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div key={idx} className="space-y-2">
              <div className="h-5 w-20 rounded-lg bg-white/[0.06] animate-pulse" />
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((__, itemIdx) => (
                  <div key={`${idx}-${itemIdx}`} className="h-9 rounded-xl bg-white/[0.06] animate-pulse" />
                ))}
              </div>
            </div>
          ))}
        </div>
      </motion.aside>
    )
  }

  if (error) {
    return (
      <motion.aside
        initial={false}
        animate={{ width: isSidebarCollapsed ? 76 : 264 }}
        transition={{ duration: 0.25, ease: 'easeInOut' }}
        className="relative flex flex-col h-screen shrink-0 z-30 bg-[var(--sidebar-bg)] border-r border-[var(--sidebar-border)]"
      >
        <div className="h-16 px-4 flex items-center border-b border-[var(--border)]">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-[#D946EF]/20 to-[#8B5CF6]/20 text-[#D946EF]">
              <Sparkles className="h-5 w-5" />
            </div>
            {!isSidebarCollapsed && <span className="font-bold text-base">Cognito Cortex</span>}
          </div>
        </div>
        <div className="flex flex-1 items-center justify-center px-4 py-6">
          <div className="w-full rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-center">
            <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-amber-500/15 text-amber-300">
              <AlertTriangle className="h-5 w-5" />
            </div>
            {!isSidebarCollapsed && (
              <>
                <p className="mt-3 text-sm font-medium text-[var(--color-text-primary)]">Backend unavailable</p>
                <p className="mt-1 text-xs text-[var(--color-text-secondary)]">The backend must be running before metadata loads.</p>
                <button
                  type="button"
                  onClick={() => void fetchMetadata()}
                  className="mt-4 inline-flex items-center justify-center rounded-xl bg-gradient-to-r from-[#D946EF] to-[#8B5CF6] px-3 py-2 text-xs font-medium text-white"
                >
                  Retry
                </button>
              </>
            )}
          </div>
        </div>
      </motion.aside>
    )
  }

  return (
    <motion.aside
      initial={false}
      animate={{ width: isSidebarCollapsed ? 76 : 264 }}
      transition={{ duration: 0.25, ease: 'easeInOut' }}
      className={cn(
        'relative flex flex-col h-screen shrink-0 z-30',
        'bg-[var(--sidebar-bg)] border-r border-[var(--sidebar-border)]',
        'transition-colors duration-200 select-none overflow-hidden'
      )}
    >
      <div className="h-16 px-4 flex items-center justify-between border-b border-[var(--border)] shrink-0">
        <NavLink
          to="/"
          className="flex items-center gap-3 group overflow-hidden rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--sidebar-bg)]"
        >
          <div className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-tr from-[#D946EF] via-[#A855F7] to-[#8B5CF6] shadow-md shadow-fuchsia-500/20 shrink-0 group-hover:scale-105 active:scale-95 transition-transform">
            <Sparkles className="w-5 h-5 text-white animate-pulse" />
          </div>

          <AnimatePresence mode="wait">
            {!isSidebarCollapsed && (
              <motion.div
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                transition={{ duration: 0.15 }}
                className="flex items-center gap-2 whitespace-nowrap"
              >
                <span className="font-bold text-lg tracking-tight text-[var(--color-text-primary)] font-sans">Cognito Cortex</span>
              </motion.div>
            )}
          </AnimatePresence>
        </NavLink>

        <button
          onClick={toggleSidebar}
          aria-label={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className={cn(
            'p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]',
            'hover:bg-white/[0.06] active:scale-90 transition-all cursor-pointer',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--sidebar-bg)]'
          )}
        >
          {isSidebarCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-4 scrollbar-thin">
        <div className="space-y-1">
          <NavLink
            to="/"
            className={cn(
              'relative flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-normal',
              'transition-all duration-150 group',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--sidebar-bg)]',
              location.pathname === '/'
                ? 'bg-gradient-to-r from-fuchsia-500/15 via-purple-500/5 to-transparent text-[var(--color-text-primary)] font-medium shadow-sm'
                : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-white/[0.04]',
              isSidebarCollapsed && 'justify-center px-0 py-2.5'
            )}
          >
            {location.pathname === '/' && (
              <motion.div
                layoutId="activeNavIndicator"
                className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r bg-gradient-to-b from-[#D946EF] to-[#8B5CF6] shadow-[0_0_12px_rgba(217,70,239,0.8)]"
              />
            )}
            <div className="relative shrink-0">
              <DynamicIcon
                name="Home"
                className={cn(
                  'w-4 h-4 transition-colors',
                  location.pathname === '/'
                    ? 'text-[#D946EF] drop-shadow-[0_0_8px_rgba(217,70,239,0.5)]'
                    : 'text-[var(--color-text-muted)] group-hover:text-[var(--color-text-secondary)]'
                )}
              />
            </div>
            {!isSidebarCollapsed && <span className="truncate flex-1 tracking-normal font-medium">Home</span>}
          </NavLink>
        </div>

        {directoryGroups.map((directory) => {
          const isOpen = !isSidebarCollapsed && Boolean(openSections[directory.id])
          const isSectionActive = directory.subdirectories.some((subdirectory) =>
            (subdirectory.pages ?? []).some((page) => location.pathname === page.route || location.pathname.startsWith(page.route))
          )

          return (
            <div key={directory.id} className="space-y-1">
              {!isSidebarCollapsed ? (
                <button
                  onClick={() => toggleSection(directory.id)}
                  className={cn(
                    'w-full px-2.5 py-1.5 flex items-center justify-between text-[11px] font-semibold tracking-wider uppercase rounded-lg',
                    'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors group cursor-pointer',
                    'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#D946EF]'
                  )}
                >
                  <div className="flex items-center gap-2">
                    <DynamicIcon
                      name={directory.icon ?? 'Folder'}
                      className={cn(
                        'w-3.5 h-3.5 transition-colors',
                        isSectionActive ? 'text-[#D946EF]' : 'text-[var(--color-text-muted)] group-hover:text-[var(--color-text-secondary)]'
                      )}
                    />
                    <span>{directory.title}</span>
                  </div>
                  <ChevronDown
                    className={cn(
                      'w-3 h-3 transition-transform duration-200',
                      isOpen ? 'rotate-0' : '-rotate-90'
                    )}
                  />
                </button>
              ) : (
                <div className="py-1 flex justify-center">
                  <div title={directory.title} className="w-7 h-0.5 rounded-full bg-white/[0.08]" />
                </div>
              )}

              <div className="space-y-1.5">
                {(isSidebarCollapsed || isOpen) &&
                  directory.subdirectories.map((subdirectory) => {
                    return (
                      <div key={subdirectory.id} className="space-y-1">
                        {!isSidebarCollapsed && (
                          <div className="px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
                            {subdirectory.title}
                          </div>
                        )}
                        {subdirectory.pages.map((page) => {
                          const isActive = location.pathname === page.route

                          return (
                            <NavLink
                              key={page.id}
                              to={page.route}
                              className={cn(
                                'relative flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-normal',
                                'transition-all duration-150 group',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--sidebar-bg)]',
                                'active:scale-[0.98]',
                                isActive
                                  ? 'bg-gradient-to-r from-fuchsia-500/15 via-purple-500/5 to-transparent text-[var(--color-text-primary)] font-medium shadow-sm'
                                  : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-white/[0.04]',
                                isSidebarCollapsed && 'justify-center px-0 py-2.5'
                              )}
                            >
                              {isActive && (
                                <motion.div
                                  layoutId="activeNavIndicator"
                                  className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r bg-gradient-to-b from-[#D946EF] to-[#8B5CF6] shadow-[0_0_12px_rgba(217,70,239,0.8)]"
                                />
                              )}

                              <div className="relative shrink-0">
                                <DynamicIcon
                                  name={directory.icon ?? 'Folder'}
                                  className={cn(
                                    'w-4 h-4 transition-colors',
                                    isActive
                                      ? 'text-[#D946EF] drop-shadow-[0_0_8px_rgba(217,70,239,0.5)]'
                                      : 'text-[var(--color-text-muted)] group-hover:text-[var(--color-text-secondary)]'
                                  )}
                                />
                              </div>

                              {!isSidebarCollapsed && (
                                <span className="truncate flex-1 tracking-normal">{page.title}</span>
                              )}
                            </NavLink>
                          )
                        })}
                      </div>
                    )
                  })}
              </div>
            </div>
          )
        })}
      </div>

      <div className="p-3 border-t border-[var(--sidebar-border)] shrink-0 space-y-2">
        {!isSidebarCollapsed ? (
          <div className="p-3 rounded-2xl bg-[var(--color-card-raised)] border border-[var(--border)] relative overflow-hidden group shadow-lg">
            <div className="absolute -right-4 -bottom-4 w-24 h-24 rounded-full bg-gradient-to-br from-fuchsia-500/10 to-purple-600/20 blur-xl pointer-events-none" />
            <div className="flex items-center gap-2 mb-1.5">
              <div className="p-1 rounded-lg bg-gradient-to-br from-[#D946EF]/20 to-[#8B5CF6]/20 border border-fuchsia-500/30 text-[#D946EF]">
                <Building2 className="w-3.5 h-3.5" />
              </div>
              <div className="truncate">
                <p className="text-xs font-semibold text-[var(--color-text-primary)] truncate">{app?.name ?? 'Meridian Distribution'}</p>
                <p className="text-[10px] text-[var(--color-text-muted)] flex items-center gap-1">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#22C55E] animate-pulse" />
                  Live Tenant
                </p>
              </div>
            </div>
            <button
              type="button"
              className={cn(
                'w-full py-1.5 px-3 rounded-xl text-xs font-medium text-white flex items-center justify-center gap-1.5',
                'bg-gradient-to-r from-[#D946EF] to-[#8B5CF6] hover:from-[#E879F9] hover:to-[#A78BFA]',
                'active:scale-95 shadow-[0_0_15px_rgba(217,70,239,0.3)] hover:shadow-[0_0_20px_rgba(217,70,239,0.5)]',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--sidebar-bg)]',
                'transition-all duration-200 cursor-pointer'
              )}
            >
              <span>Meridian Cloud</span>
              <ExternalLink className="w-3 h-3" />
            </button>
          </div>
        ) : (
          <div className="flex justify-center">
            <button
              title="Meridian Distribution (Active Tenant)"
              className="p-2.5 rounded-xl bg-[var(--color-card-raised)] border border-[var(--border)] text-[#D946EF] hover:bg-white/[0.06] active:scale-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] transition-all cursor-pointer"
            >
              <Building2 className="w-4 h-4" />
            </button>
          </div>
        )}

        <button
          type="button"
          className={cn(
            'w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-[var(--color-text-muted)]',
            'hover:text-[var(--color-text-primary)] hover:bg-white/[0.04] active:scale-95 transition-all cursor-pointer',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--sidebar-bg)]',
            isSidebarCollapsed && 'justify-center px-0'
          )}
          title={isSidebarCollapsed ? 'Logout' : undefined}
        >
          <LogOut className="w-3.5 h-3.5 shrink-0" />
          {!isSidebarCollapsed && <span>Logout</span>}
        </button>
      </div>
    </motion.aside>
  )
}
