import React, { useEffect, useState, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Search,
  Sun,
  Moon,
  Bell,
  Mail,
  Sparkles,
  ChevronDown,
  Check,
  Building2,
  TrendingDown,
  TrendingUp,
  ArrowRight,
  FileText,
} from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { useUIStore } from '@/store/themeStore'
import { useMetadataStore } from '@/store/metadataStore'
import { useUiStateStore } from '@/store/uiStateStore'
import { DEMO_USERS, useSessionStore } from '@/store/sessionStore'
import { useCognitoPilotStore } from '@/store/cognitoPilotStore'
import { cn } from '@/lib/utils'

interface AppItem {
  id: string
  name: string
  description?: string
  active?: boolean
}

export const TopBar: React.FC = () => {
  const { theme, toggleTheme } = useUIStore()
  const navigate = useNavigate()
  const activeUserId = useSessionStore((state) => state.activeUserId)
  const setActiveUser = useSessionStore((state) => state.setActiveUser)
  const user = DEMO_USERS.find((demoUser) => demoUser.id === activeUserId) ?? DEMO_USERS[0]
  const pages = useMetadataStore((state) => state.pages)
  const asOf = useMetadataStore((state) => state.asOf)
  const refetchMetadata = useMetadataStore((state) => state.refetch)
  const clearPageState = useUiStateStore((state) => state.clearAll)
  const openCognitoPilot = useCognitoPilotStore((state) => state.openPanel)
  const clearSession = useCognitoPilotStore((state) => state.clearSession)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [appMenuOpen, setAppMenuOpen] = useState(false)
  const [apps, setApps] = useState<AppItem[]>([
    { id: 'meridian', name: 'Meridian Distribution', active: true }
  ])

  // Search state
  const searchInputRef = useRef<HTMLInputElement>(null)
  const searchContainerRef = useRef<HTMLDivElement>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchIndex, setSearchIndex] = useState(0)

  // Bell / notifications state
  const bellContainerRef = useRef<HTMLDivElement>(null)
  const [bellOpen, setBellOpen] = useState(false)
  const [hasUnread, setHasUnread] = useState(() => {
    try {
      return localStorage.getItem('cognito_notifications_read') !== 'true'
    } catch {
      return true
    }
  })
  const [insights, setInsights] = useState<Array<{
    id: string
    title: string
    description: string
    question: string
    direction: 'drop' | 'rise'
    formatted_change: string
    formatted_pct_change: string
  }>>([])
  const [insightsLoading, setInsightsLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await apiFetch('/api/apps')
        if (res.ok) {
          const data = await res.json()
          if (!cancelled && Array.isArray(data.apps)) {
            setApps(data.apps)
          }
        }
      } catch {
        // ignore
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const activeApp = apps.find((a) => a.active) || apps[0] || { id: 'meridian', name: 'Meridian Distribution' }

  // Load insights for active app
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        setInsightsLoading(true)
        const res = await apiFetch('/api/noticed')
        if (res.ok) {
          const data = await res.json()
          if (!cancelled && Array.isArray(data.insights)) {
            setInsights(data.insights)
          }
        }
      } catch {
        // ignore
      } finally {
        if (!cancelled) setInsightsLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [activeApp.id, activeUserId])

  // Global Ctrl+K to focus search input
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        searchInputRef.current?.focus()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  // Close menus on Escape or click outside
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setUserMenuOpen(false)
        setAppMenuOpen(false)
        setSearchOpen(false)
        setBellOpen(false)
      }
    }
    const handleClickOutside = (event: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(event.target as Node)) {
        setSearchOpen(false)
      }
      if (bellContainerRef.current && !bellContainerRef.current.contains(event.target as Node)) {
        setBellOpen(false)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  // Filter accessible pages matching search query (respecting role permissions)
  const searchResults = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return []
    const tokens = q.split(/\s+/).filter(Boolean)
    const matches: Array<{ page: typeof pages[0]; section: string }> = []
    for (const p of pages) {
      const allowedRoles = (p as any).allowed_roles
      if (Array.isArray(allowedRoles) && allowedRoles.length > 0 && !allowedRoles.includes(user.role)) {
        continue
      }
      const section = p.directory || p.subdirectory || 'Analytics'
      const widgetTitles = (p.widgets || []).map((w) => w.title || '').join(' ')
      const corpus = `${p.title} ${section} ${p.description || ''} ${widgetTitles}`.toLowerCase()
      if (tokens.every((t) => corpus.includes(t))) {
        matches.push({ page: p, section })
        if (matches.length >= 6) break
      }
    }
    return matches
  }, [searchQuery, pages, user.role])

  const totalSearchItems = searchResults.length + (searchQuery.trim() ? 1 : 0)

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (!searchOpen) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') {
        setSearchOpen(true)
      }
      return
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (totalSearchItems > 0) {
        setSearchIndex((prev) => (prev + 1) % totalSearchItems)
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (totalSearchItems > 0) {
        setSearchIndex((prev) => (prev - 1 + totalSearchItems) % totalSearchItems)
      }
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setSearchOpen(false)
      searchInputRef.current?.blur()
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (searchIndex >= 0 && searchIndex < searchResults.length) {
        const item = searchResults[searchIndex]
        navigate(item.page.route)
        setSearchOpen(false)
        setSearchQuery('')
      } else if (searchQuery.trim()) {
        openCognitoPilot(searchQuery.trim())
        setSearchOpen(false)
        setSearchQuery('')
      }
    }
  }

  const toggleBell = () => {
    setBellOpen((prev) => !prev)
    setHasUnread(false)
    try {
      localStorage.setItem('cognito_notifications_read', 'true')
    } catch {
      // ignore
    }
  }

  const switchApp = async (appId: string) => {
    if (appId === activeApp.id) {
      setAppMenuOpen(false)
      return
    }
    setAppMenuOpen(false)
    try {
      await apiFetch('/api/apps/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ app_id: appId }),
      })
      clearPageState()
      clearSession()
      navigate('/')
      await refetchMetadata()
      setApps((prev) => prev.map((a) => ({ ...a, active: a.id === appId })))
    } catch (err) {
      console.error('Failed to switch app', err)
    }
  }

  const switchUser = async (userId: string) => {
    if (userId === activeUserId) {
      setUserMenuOpen(false)
      return
    }
    setActiveUser(userId)
    clearPageState()
    setUserMenuOpen(false)
    navigate('/')
    await refetchMetadata()
  }

  const roleBadgeClass: Record<string, string> = {
    admin: 'border-fuchsia-400/30 bg-fuchsia-400/10 text-fuchsia-200',
    regional_manager: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
    analyst: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  }

  return (
    <header className="h-16 px-4 sm:px-6 flex items-center justify-between border-b border-[var(--border)] bg-[var(--background)]/85 backdrop-blur-md sticky top-0 z-20 transition-colors gap-3">
      {/* Search Bar Container */}
      <div ref={searchContainerRef} className="relative flex-1 min-w-[140px] max-w-[220px] xs:max-w-[280px] sm:max-w-xs md:max-w-md transition-all">
        <div className="relative flex items-center">
          <Search className="absolute left-3.5 w-4 h-4 text-[var(--color-text-muted)] pointer-events-none" />
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setSearchOpen(true)
              setSearchIndex(0)
            }}
            onFocus={() => {
              if (searchQuery.trim()) setSearchOpen(true)
            }}
            onKeyDown={handleSearchKeyDown}
            placeholder="Search records, analytics..."
            className={cn(
              'w-full pl-10 pr-4 sm:pr-20 py-2 rounded-xl text-xs sm:text-sm transition-all',
              'bg-[var(--color-card-raised)] border border-[var(--border)]',
              'text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]'
            )}
          />
          <div className="absolute right-3 hidden sm:flex items-center gap-1 pointer-events-none">
            <kbd className="px-1.5 py-0.5 text-[10px] font-mono font-medium rounded-md bg-white/[0.08] text-[var(--color-text-muted)] border border-white/[0.1] shadow-xs">Ctrl</kbd>
            <span className="text-[10px] text-[var(--color-text-muted)]">+</span>
            <kbd className="px-1.5 py-0.5 text-[10px] font-mono font-medium rounded-md bg-white/[0.08] text-[var(--color-text-muted)] border border-white/[0.1] shadow-xs">K</kbd>
          </div>
        </div>

        {/* Search Results Dropdown */}
        {searchOpen && searchQuery.trim() && (
          <div
            role="listbox"
            className="absolute left-0 top-full mt-2 w-full min-w-[280px] sm:min-w-[360px] rounded-2xl border border-[var(--border)] bg-[var(--color-card)] p-2 shadow-2xl backdrop-blur-xl z-50 overflow-hidden"
          >
            {searchResults.length === 0 ? (
              <div className="px-3 py-3 text-center text-xs text-[var(--color-text-muted)]">
                No pages found matching &ldquo;{searchQuery}&rdquo;
              </div>
            ) : (
              <div className="space-y-0.5">
                {searchResults.map((item, idx) => {
                  const isSelected = idx === searchIndex
                  return (
                    <button
                      key={item.page.id}
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      onClick={() => {
                        navigate(item.page.route)
                        setSearchOpen(false)
                        setSearchQuery('')
                      }}
                      onMouseEnter={() => setSearchIndex(idx)}
                      className={cn(
                        'flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left transition-colors cursor-pointer',
                        isSelected
                          ? 'bg-fuchsia-500/15 text-[var(--color-text-primary)] border border-fuchsia-500/30'
                          : 'hover:bg-black/5 dark:hover:bg-white/[0.06] text-[var(--color-text-primary)] border border-transparent'
                      )}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <FileText className="w-4 h-4 text-fuchsia-400 shrink-0" />
                        <div className="min-w-0">
                          <span className="block truncate text-xs font-semibold">{item.page.title}</span>
                          <span className="block truncate text-[10px] text-[var(--color-text-muted)]">{item.section}</span>
                        </div>
                      </div>
                      <ArrowRight className="w-3.5 h-3.5 text-[var(--color-text-muted)] shrink-0" />
                    </button>
                  )
                })}
              </div>
            )}

            {/* Last row: Ask Cognito Pilot */}
            <div className="mt-1 pt-1 border-t border-[var(--border)]">
              <button
                type="button"
                role="option"
                aria-selected={searchIndex === searchResults.length}
                onClick={() => {
                  openCognitoPilot(searchQuery.trim())
                  setSearchOpen(false)
                  setSearchQuery('')
                }}
                onMouseEnter={() => setSearchIndex(searchResults.length)}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left transition-colors cursor-pointer',
                  searchIndex === searchResults.length
                    ? 'bg-fuchsia-500/20 text-fuchsia-200 border border-fuchsia-500/40'
                    : 'bg-fuchsia-500/5 hover:bg-fuchsia-500/15 text-[var(--color-text-primary)] border border-fuchsia-500/15'
                )}
              >
                <Sparkles className="w-4 h-4 text-fuchsia-400 shrink-0 animate-pulse" />
                <span className="truncate text-xs font-medium text-fuchsia-300">
                  Ask Cognito Pilot: <span className="font-semibold text-white dark:text-fuchsia-100">&ldquo;{searchQuery}&rdquo;</span>
                </span>
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        <button
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          className={cn(
            'p-2 rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)]',
            'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
            'hover:border-white/[0.15] active:scale-95 active:translate-y-0.5',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]',
            'transition-all cursor-pointer relative'
          )}
        >
          <motion.div key={theme} initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} transition={{ duration: 0.2 }}>
            {theme === 'dark' ? <Sun className="w-4 h-4 text-[#F59E0B]" /> : <Moon className="w-4 h-4 text-[#8B5CF6]" />}
          </motion.div>
        </button>

        <button
          type="button"
          aria-label="Messages"
          className={cn('relative p-2 rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)]', 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]', 'hover:border-white/[0.15] active:scale-95 active:translate-y-0.5', 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]', 'transition-all cursor-pointer hidden xs:inline-flex')}
        >
          <Mail className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[#8B5CF6] shadow-[0_0_6px_#8B5CF6]" />
        </button>

        {/* Notifications / Bell */}
        <div ref={bellContainerRef} className="relative">
          <button
            type="button"
            aria-label="Notifications"
            aria-expanded={bellOpen}
            onClick={toggleBell}
            className={cn(
              'relative p-2 rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)]',
              'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
              'hover:border-white/[0.15] active:scale-95 active:translate-y-0.5',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]',
              'transition-all cursor-pointer'
            )}
          >
            <Bell className="w-4 h-4" />
            {hasUnread && (
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[#D946EF] shadow-[0_0_6px_#D946EF]" />
            )}
          </button>

          {bellOpen && (
            <div
              role="menu"
              aria-label="Notifications menu"
              className="absolute right-0 top-full mt-2 w-80 sm:w-96 rounded-2xl border border-[var(--border)] bg-[var(--color-card)] p-3 shadow-2xl backdrop-blur-xl z-50"
            >
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-[var(--border)]">
                <div className="flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-fuchsia-400" />
                  <span className="text-xs font-bold text-[var(--color-text-primary)]">Operational Insights</span>
                </div>
                <span className="text-[10px] text-[var(--color-text-muted)]">This quarter vs previous</span>
              </div>

              {insightsLoading ? (
                <div className="py-6 text-center text-xs text-[var(--color-text-muted)]">
                  Scanning active insights...
                </div>
              ) : insights.length === 0 ? (
                <div className="py-6 text-center text-xs text-[var(--color-text-muted)]">
                  No new insights
                </div>
              ) : (
                <div className="space-y-1.5 max-h-[380px] overflow-y-auto">
                  {insights.slice(0, 5).map((item) => {
                    const isDrop = item.direction === 'drop'
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          openCognitoPilot(item.question)
                          setBellOpen(false)
                        }}
                        className="flex w-full items-start gap-2.5 rounded-xl p-2.5 text-left bg-black/5 dark:bg-white/[0.03] hover:bg-fuchsia-500/10 border border-[var(--border)] hover:border-fuchsia-500/30 transition-all cursor-pointer group"
                      >
                        <div
                          className={cn(
                            'p-1.5 rounded-lg shrink-0 mt-0.5 border',
                            isDrop
                              ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                              : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                          )}
                        >
                          {isDrop ? <TrendingDown className="w-3.5 h-3.5" /> : <TrendingUp className="w-3.5 h-3.5" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-semibold text-[var(--color-text-primary)] group-hover:text-fuchsia-300 transition-colors line-clamp-1">
                            {item.title}
                          </p>
                          <p className="text-[11px] text-[var(--color-text-secondary)] line-clamp-1 mt-0.5">
                            {item.description}
                          </p>
                          <span className="inline-flex items-center gap-1 text-[10px] text-fuchsia-400 font-medium mt-1 group-hover:underline">
                            Investigate in Cognito Pilot <ArrowRight className="w-2.5 h-2.5" />
                          </span>
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="h-6 w-px bg-[var(--border)] mx-0.5 sm:mx-1 hidden xs:block" />

        {/* App Switcher Dropdown */}
        <div className="relative">
          <button
            type="button"
            aria-haspopup="menu"
            aria-expanded={appMenuOpen}
            aria-label={`Current app: ${activeApp.name}, switch app`}
            onClick={() => setAppMenuOpen((open) => !open)}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)]',
              'text-xs font-medium text-[var(--color-text-primary)] hover:border-fuchsia-400/40 hover:bg-fuchsia-500/10 transition-all cursor-pointer',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF]'
            )}
          >
            <Building2 className="w-3.5 h-3.5 text-fuchsia-400" />
            <span className="hidden sm:inline max-w-[130px] truncate">{activeApp.name}</span>
            <ChevronDown className="w-3 h-3 text-[var(--color-text-muted)]" />
          </button>

          {appMenuOpen && (
            <div
              role="menu"
              aria-label="Switch application"
              className="absolute right-0 top-full mt-2 w-64 rounded-xl border border-[var(--border)] bg-[var(--color-card)]/95 p-2 shadow-2xl backdrop-blur-xl z-30"
            >
              <p className="px-3 py-1.5 text-xs font-semibold text-[var(--color-text-secondary)]">Switch Application</p>
              {apps.map((appItem) => (
                <button
                  key={appItem.id}
                  type="button"
                  role="menuitemradio"
                  aria-checked={appItem.id === activeApp.id}
                  onClick={() => void switchApp(appItem.id)}
                  className="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF]"
                >
                  <div className="min-w-0">
                    <span className="block truncate text-xs font-medium text-[var(--color-text-primary)]">{appItem.name}</span>
                    {appItem.description && (
                      <span className="block truncate text-[10px] text-[var(--color-text-muted)]">{appItem.description}</span>
                    )}
                  </div>
                  {appItem.id === activeApp.id && <Check className="h-3.5 w-3.5 text-fuchsia-400 shrink-0" />}
                </button>
              ))}
            </div>
          )}
        </div>

        {asOf && (
          <span
            title={`Data as of ${asOf}`}
            className="hidden sm:inline-flex items-center rounded-full border border-[var(--border)] bg-[var(--color-card-raised)] px-2.5 py-1 text-[10px] font-medium text-[var(--color-text-secondary)] whitespace-nowrap"
          >
            Data as of {new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${asOf}T00:00:00Z`))}
          </span>
        )}

        <button
          type="button"
          onClick={() => openCognitoPilot()}
          className={cn('relative px-3 sm:px-4 py-2 rounded-xl text-xs font-semibold text-white tracking-wide', 'flex items-center gap-1.5 sm:gap-2 cursor-pointer overflow-hidden group', 'bg-gradient-to-r from-[#D946EF] to-[#8B5CF6]', 'hover:from-[#E879F9] hover:to-[#A78BFA] active:scale-95 active:translate-y-0.5', 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]', 'shadow-[0_0_20px_rgba(217,70,239,0.35)] hover:shadow-[0_0_28px_rgba(217,70,239,0.55)]', 'transition-all duration-200 shrink-0')}
        >
          <Sparkles className="w-3.5 h-3.5 animate-pulse text-white" />
          <span>Cognito Pilot</span>
          <span className="px-1.5 py-0.2 text-[9px] font-bold uppercase rounded bg-white/20 text-white hidden sm:inline">AI</span>
          <div className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-700 bg-gradient-to-r from-transparent via-white/20 to-transparent" />
        </button>

        <div className="h-6 w-px bg-[var(--border)] mx-0.5 sm:mx-1 hidden sm:block" />

        <div className="relative">
          <button
            type="button"
            aria-haspopup="menu"
            aria-expanded={userMenuOpen}
            aria-label={`${user.name}, switch demo role`}
            onClick={() => setUserMenuOpen((open) => !open)}
            className={cn('flex items-center gap-2.5 pl-1 rounded-xl cursor-pointer group text-left', 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]')}
          >
            <div className="relative">
              <div className="w-8 sm:w-9 h-8 sm:h-9 rounded-full bg-gradient-to-tr from-[#D946EF] to-[#8B5CF6] p-[1.5px] shadow-sm">
                <div className="w-full h-full rounded-full bg-[#10101A] flex items-center justify-center text-xs font-semibold text-white">{user.initials}</div>
              </div>
              <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-[#22C55E] border-2 border-[var(--background)]" />
            </div>
            <div className="hidden lg:flex flex-col text-left">
              <span className="text-xs font-semibold text-[var(--color-text-primary)] group-hover:text-[#D946EF] transition-colors leading-tight">{user.name}</span>
              <span className="text-[10px] text-[var(--color-text-muted)] leading-tight">{user.title}</span>
            </div>
            <ChevronDown className="w-3.5 h-3.5 text-[var(--color-text-muted)] group-hover:text-[var(--color-text-primary)] transition-colors" />
          </button>

          {userMenuOpen && (
            <div role="menu" aria-label="Switch demo role" className="absolute right-0 top-full mt-2 w-72 rounded-xl border border-[var(--border)] bg-[var(--color-card)]/95 p-2 shadow-2xl backdrop-blur-xl z-30">
              <p className="px-3 py-2 text-xs font-semibold text-[var(--color-text-secondary)]">Switch demo role</p>
              {DEMO_USERS.map((demoUser) => (
                <button
                  key={demoUser.id}
                  type="button"
                  role="menuitemradio"
                  aria-checked={demoUser.id === activeUserId}
                  onClick={() => void switchUser(demoUser.id)}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF]"
                >
                  <span className="flex-1 min-w-0">
                    <span className="block truncate text-sm font-medium text-[var(--color-text-primary)]">{demoUser.name}</span>
                    <span className="block truncate text-[10px] text-[var(--color-text-muted)]">{demoUser.title}</span>
                  </span>
                  <span className={cn('rounded-full border px-2 py-0.5 text-[10px] font-medium', roleBadgeClass[demoUser.role])}>{demoUser.roleLabel}</span>
                  {demoUser.id === activeUserId ? <Check className="h-4 w-4 text-[var(--color-text-primary)]" /> : <span className="w-4" />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
