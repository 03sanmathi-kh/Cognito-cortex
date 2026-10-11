import React, { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Sparkles,
  TrendingUp,
  TrendingDown,
  ArrowRight,
  RefreshCw,
  Zap,
} from 'lucide-react'
import { useMetadataStore } from '@/store/metadataStore'
import { useCognitoPilotStore } from '@/store/cognitoPilotStore'
import { DynamicIcon } from '@/components/DynamicIcon'
import { apiFetch } from '@/lib/api'
import { RobotMascot } from '@/components/RobotMascot'

interface KpiData {
  pageId: string
  widgetId: string
  title: string
  value: number | null
  changePct: number | null
  loading: boolean
  error?: string
}

interface NoticedData {
  metric?: string
  metric_label?: string
  dimension?: string
  segment?: string
  direction?: 'drop' | 'rise' | 'neutral'
  headline?: string
  sentence?: string
  formatted_change?: string
  percent_change?: number
  formatted_pct_change?: string
  top_contributors?: Array<{ label: string; formatted_change: string }>
  chips?: string[]
}

export const DashboardOverview: React.FC = () => {
  const navigate = useNavigate()
  const app = useMetadataStore((state) => state.app)
  const pages = useMetadataStore((state) => state.pages)
  const openCognitoPilot = useCognitoPilotStore((state) => state.openPanel)

  const [noticed, setNoticed] = useState<NoticedData | null>(null)
  const [noticedLoading, setNoticedLoading] = useState(true)
  const [kpiList, setKpiList] = useState<KpiData[]>([])

  const isClinic = useMemo(() => {
    return (
      app?.id === 'clinic' ||
      String(app?.name || '').toLowerCase().includes('clinic') ||
      String(app?.description || '').toLowerCase().includes('clinic') ||
      String(app?.description || '').toLowerCase().includes('healthcare')
    )
  }, [app])

  // Extract top 4 KPI widgets from accessible pages
  const topKpis = useMemo(() => {
    const list: Array<{ pageId: string; widget: any }> = []
    for (const page of pages) {
      for (const widget of page.widgets || []) {
        if (widget.type === 'kpi') {
          list.push({ pageId: page.id, widget })
          if (list.length >= 4) return list
        }
      }
    }
    return list
  }, [pages])

  // Fetch KPI data
  useEffect(() => {
    if (!topKpis.length) return
    let cancelled = false

    const initialKpiState: KpiData[] = topKpis.map(({ pageId, widget }) => ({
      pageId,
      widgetId: widget.id,
      title: widget.title,
      value: null,
      changePct: null,
      loading: true,
    }))
    setKpiList(initialKpiState)

    topKpis.forEach(({ pageId, widget }, idx) => {
      const query = new URLSearchParams({
        page_id: pageId,
        widget_id: widget.id,
        date_range: 'this_quarter',
      })

      void apiFetch(`/api/widget-data?${query.toString()}`)
        .then((res) => (res.ok ? res.json() : Promise.reject('Failed to fetch KPI')))
        .then((data) => {
          if (cancelled) return
          const row = data?.rows?.[0]
          setKpiList((prev) => {
            const next = [...prev]
            if (next[idx]) {
              next[idx] = {
                ...next[idx],
                value: row?.value !== undefined ? Number(row.value) : null,
                changePct: row?.change_pct !== undefined ? Number(row.change_pct) : null,
                loading: false,
              }
            }
            return next
          })
        })
        .catch((err) => {
          if (cancelled) return
          setKpiList((prev) => {
            const next = [...prev]
            if (next[idx]) {
              next[idx] = { ...next[idx], loading: false, error: String(err) }
            }
            return next
          })
        })
    })

    return () => {
      cancelled = true
    }
  }, [topKpis, app?.id])

  // Fetch "Cognito Pilot noticed"
  useEffect(() => {
    let cancelled = false
    setNoticedLoading(true)

    void apiFetch('/api/noticed')
      .then((res) => (res.ok ? res.json() : Promise.reject('Failed to load insights')))
      .then((data) => {
        if (!cancelled) {
          setNoticed(data)
          setNoticedLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setNoticedLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [app?.id])

  const formatKpiValue = (val: number | null, title: string = '') => {
    if (val === null || val === undefined || Number.isNaN(val)) return 'n/a'
    const lower = title.toLowerCase()
    if (/rate|percent|pct|margin/i.test(lower)) {
      if (Math.abs(val) > 1000) return 'n/a'
      return `${val.toFixed(1)}%`
    }
    if (/revenue|fee|cost|expense|sales|price|budget/i.test(lower)) {
      const abs = Math.abs(val)
      if (abs >= 1_000_000) return `$${(val / 1_000_000).toFixed(2)}M`
      if (abs >= 1_000) return `$${(val / 1_000).toFixed(2)}K`
      return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    }
    return val.toLocaleString()
  }

  // 4 quick-link pages
  const quickLinks = useMemo(() => {
    return pages.slice(0, 4)
  }, [pages])

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* 1. Hero banner */}
      <section className="relative overflow-hidden rounded-3xl bg-[#3F1A57] dark:bg-[var(--color-card)] border border-purple-500/30 p-6 sm:p-8 text-white shadow-2xl transition-all">
        {/* Decorative background glow */}
        <div className="pointer-events-none absolute -right-16 -top-16 h-80 w-80 rounded-full bg-gradient-to-br from-fuchsia-600/30 to-violet-600/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-20 left-1/3 h-64 w-64 rounded-full bg-purple-500/20 blur-2xl" />

        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          {/* Left Text & CTA */}
          <div className="space-y-3 max-w-xl">
            <div className="inline-flex items-center gap-1.5 rounded-full border border-fuchsia-300/30 bg-fuchsia-500/20 px-3 py-1 text-xs font-semibold text-fuchsia-200 backdrop-blur-md">
              <Sparkles className="h-3.5 w-3.5 text-fuchsia-300 animate-pulse" />
              <span>Executive Intelligence Hub</span>
            </div>

            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold tracking-tight text-white">
              {app?.name || 'Cognito Cortex'}
            </h1>

            <p className="text-sm sm:text-base text-fuchsia-100/80 leading-relaxed font-normal">
              {app?.description || 'Active operational telemetry, revenue velocity, and comparative drivers across dimensions.'}
            </p>

            <div className="pt-2">
              <button
                type="button"
                onClick={() => openCognitoPilot()}
                className="inline-flex items-center gap-2.5 rounded-xl bg-gradient-to-r from-fuchsia-500 via-purple-500 to-violet-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-purple-950/50 hover:from-fuchsia-400 hover:to-violet-500 active:scale-95 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-fuchsia-400"
              >
                <Sparkles className="h-4 w-4" />
                <span>Ask Cognito Pilot</span>
              </button>
            </div>
          </div>

          {/* Right SVG Illustration with Animated Robot */}
          <div className="relative shrink-0 flex items-center justify-center self-center md:self-auto">
            <div className="relative h-44 w-64 sm:h-48 sm:w-72">
              {isClinic ? (
                /* Clinic SVG Illustration */
                <svg
                  viewBox="0 0 280 180"
                  className="h-full w-full overflow-visible drop-shadow-xl"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  {/* Calendar background plate */}
                  <rect x="20" y="25" width="85" height="95" rx="12" fill="#2E1140" stroke="#A855F7" strokeWidth="1.5" />
                  <rect x="20" y="25" width="85" height="26" rx="12" fill="#9333EA" />
                  <circle cx="40" cy="38" r="3" fill="#FFFFFF" opacity="0.9" />
                  <circle cx="55" cy="38" r="3" fill="#FFFFFF" opacity="0.9" />
                  <circle cx="70" cy="38" r="3" fill="#FFFFFF" opacity="0.9" />
                  <circle cx="85" cy="38" r="3" fill="#FFFFFF" opacity="0.9" />
                  {/* Calendar day dots */}
                  <circle cx="36" cy="65" r="3" fill="#D8B4FE" />
                  <circle cx="52" cy="65" r="3" fill="#D8B4FE" />
                  <circle cx="68" cy="65" r="3" fill="#D8B4FE" />
                  <circle cx="84" cy="65" r="3" fill="#D8B4FE" />
                  <circle cx="36" cy="80" r="3" fill="#D8B4FE" />
                  <circle cx="52" cy="80" r="3" fill="#38BDF8" />
                  <circle cx="68" cy="80" r="3" fill="#D8B4FE" />
                  <circle cx="84" cy="80" r="3" fill="#D8B4FE" />
                  <circle cx="36" cy="95" r="3" fill="#D8B4FE" />
                  <circle cx="52" cy="95" r="3" fill="#D8B4FE" />
                  <circle cx="68" cy="95" r="3" fill="#22C55E" />
                  <circle cx="84" cy="95" r="3" fill="#D8B4FE" />

                  {/* Medical Cross Badge */}
                  <g transform="translate(85, 15)">
                    <rect x="0" y="0" width="36" height="36" rx="10" fill="#22C55E" />
                    <rect x="15" y="8" width="6" height="20" rx="3" fill="#FFFFFF" />
                    <rect x="8" y="15" width="20" height="6" rx="3" fill="#FFFFFF" />
                  </g>

                  {/* EKG Heart Pulse Wave */}
                  <path
                    d="M 15 145 L 60 145 L 75 130 L 85 160 L 95 115 L 105 155 L 115 145 L 160 145"
                    stroke="#38BDF8"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <circle cx="95" cy="115" r="4.5" fill="#38BDF8" />
                  <circle cx="95" cy="115" r="8" stroke="#38BDF8" strokeWidth="1.5" opacity="0.6" />
                </svg>
              ) : (
                /* Sales SVG Illustration */
                <svg
                  viewBox="0 0 280 180"
                  className="h-full w-full overflow-visible drop-shadow-xl"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  {/* Gradient Bars */}
                  <defs>
                    <linearGradient id="barGrad1" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#D946EF" />
                      <stop offset="100%" stopColor="#8B5CF6" />
                    </linearGradient>
                    <linearGradient id="barGrad2" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#38BDF8" />
                      <stop offset="100%" stopColor="#2563EB" />
                    </linearGradient>
                    <linearGradient id="goldCoin" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor="#FDE047" />
                      <stop offset="100%" stopColor="#D97706" />
                    </linearGradient>
                  </defs>

                  {/* 3 Metric Bars */}
                  <rect x="25" y="90" width="22" height="60" rx="6" fill="url(#barGrad1)" />
                  <rect x="55" y="60" width="22" height="90" rx="6" fill="url(#barGrad2)" />
                  <rect x="85" y="40" width="22" height="110" rx="6" fill="url(#barGrad1)" />

                  {/* Rising line */}
                  <path
                    d="M 15 130 C 45 105, 65 75, 115 28"
                    stroke="#22C55E"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                  />
                  <circle cx="115" cy="28" r="5" fill="#22C55E" />
                  <circle cx="115" cy="28" r="9" stroke="#22C55E" strokeWidth="1.5" opacity="0.6" />

                  {/* Golden Coins */}
                  <g transform="translate(15, 30)">
                    <ellipse cx="20" cy="20" rx="14" ry="14" fill="url(#goldCoin)" />
                    <ellipse cx="20" cy="20" rx="10" ry="10" stroke="#FEF08A" strokeWidth="1.5" fill="none" />
                    <text x="17" y="24" fill="#78350F" fontSize="11" fontWeight="bold">$</text>
                  </g>
                  <g transform="translate(85, 110)">
                    <ellipse cx="18" cy="18" rx="12" ry="12" fill="url(#goldCoin)" />
                    <ellipse cx="18" cy="18" rx="8" ry="8" stroke="#FEF08A" strokeWidth="1.5" fill="none" />
                    <text x="15" y="22" fill="#78350F" fontSize="10" fontWeight="bold">$</text>
                  </g>
                </svg>
              )}

              {/* Animated Robot integrated into illustration */}
              <div className="absolute right-2 top-6 sm:right-4 sm:top-4 z-20">
                <RobotMascot size={76} />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 2. Row of 4 KPI cards */}
      <section className="space-y-2.5">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-secondary)]">
            Core Performance Metrics
          </h2>
          <span className="text-[11px] text-[var(--color-text-muted)]">This Quarter vs Previous</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {kpiList.map((kpi, idx) => {
            const hasChange = kpi.changePct !== null && kpi.changePct !== undefined
            const isNegative = hasChange && (kpi.changePct ?? 0) < 0

            return (
              <motion.div
                key={kpi.widgetId || idx}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, delay: idx * 0.05 }}
                className="rounded-2xl border border-[var(--border)] bg-[var(--color-card)] p-5 shadow-sm hover:border-purple-500/30 transition-all"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-[var(--color-text-secondary)] truncate">
                    {kpi.title}
                  </span>
                  <div className="p-1.5 rounded-lg bg-[var(--color-card-raised)] border border-[var(--border)] text-[var(--color-text-muted)]">
                    <Zap className="h-3.5 w-3.5 text-fuchsia-400" />
                  </div>
                </div>

                <div className="mt-3 flex items-baseline justify-between gap-2">
                  <div className="text-xl sm:text-2xl font-extrabold tracking-tight text-[var(--color-text-primary)]">
                    {kpi.loading ? (
                      <div className="h-7 w-24 rounded-lg bg-black/10 dark:bg-white/10 animate-pulse" />
                    ) : (
                      formatKpiValue(kpi.value, kpi.title)
                    )}
                  </div>

                  {hasChange && !kpi.loading && (
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-bold tabular-nums border ${
                        isNegative
                          ? 'bg-rose-500/10 text-rose-500 border-rose-500/20'
                          : 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                      }`}
                    >
                      {Math.abs(kpi.changePct ?? 0) > 1000 || Number.isNaN(kpi.changePct) ? (
                        <span>n/a</span>
                      ) : (
                        <>
                          {isNegative ? (
                            <TrendingDown className="h-3 w-3" />
                          ) : (
                            <TrendingUp className="h-3 w-3" />
                          )}
                          <span>
                            {(kpi.changePct ?? 0) > 0 ? '+' : ''}
                            {Number(kpi.changePct).toFixed(1)}%
                          </span>
                        </>
                      )}
                    </span>
                  )}
                </div>
              </motion.div>
            )
          })}
        </div>
      </section>

      {/* 3. "Cognito Pilot noticed" card */}
      <section className="rounded-2xl border border-purple-500/30 bg-gradient-to-br from-[var(--color-card)] via-[var(--color-card)] to-purple-950/15 p-5 sm:p-6 shadow-md space-y-3.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-xl bg-fuchsia-500/15 text-fuchsia-400 border border-fuchsia-500/30">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-fuchsia-400">
              Cognito Pilot Noticed
            </span>
            <h3 className="text-sm sm:text-base font-bold text-[var(--color-text-primary)]">
              {noticed?.headline || 'Analyzing active operational variations...'}
            </h3>
          </div>
        </div>

        {noticedLoading ? (
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)] py-2">
            <RefreshCw className="h-4 w-4 animate-spin text-fuchsia-400" />
            <span>Scanning dimensional trends across this quarter...</span>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs sm:text-sm text-[var(--color-text-primary)] leading-relaxed">
              {noticed?.sentence}
            </p>

            {/* Clickable question chips */}
            {noticed?.chips && noticed.chips.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <span className="text-[11px] font-semibold text-[var(--color-text-secondary)]">Investigate:</span>
                {noticed.chips.map((chip, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => openCognitoPilot(chip)}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-fuchsia-500/30 bg-fuchsia-500/10 hover:bg-fuchsia-500/20 px-3 py-1.5 text-xs font-medium text-fuchsia-300 hover:text-fuchsia-200 transition-all cursor-pointer shadow-sm active:scale-95"
                  >
                    <span>{chip}</span>
                    <ArrowRight className="h-3 w-3 opacity-70" />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {/* 4. "Jump to" row: 4 quick-link cards */}
      <section className="space-y-2.5">
        <h2 className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-secondary)]">
          Jump To Application Views
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {quickLinks.map((page) => (
            <motion.button
              key={page.id}
              type="button"
              onClick={() => navigate(page.route)}
              whileHover={{ y: -3 }}
              transition={{ duration: 0.15 }}
              className="flex flex-col justify-between text-left rounded-2xl border border-[var(--border)] bg-[var(--color-card)] p-5 shadow-sm hover:border-purple-500/40 hover:shadow-md transition-all cursor-pointer group"
            >
              <div>
                <div className="flex items-center justify-between gap-2">
                  <div className="p-2 rounded-xl bg-gradient-to-tr from-fuchsia-500/10 to-purple-500/20 text-fuchsia-400 border border-fuchsia-500/20 group-hover:scale-105 transition-transform">
                    <DynamicIcon name={page.icon || 'FileText'} className="h-4 w-4" />
                  </div>
                  <ArrowRight className="h-4 w-4 text-[var(--color-text-muted)] group-hover:text-fuchsia-400 group-hover:translate-x-1 transition-all" />
                </div>

                <h3 className="mt-3.5 text-sm font-bold text-[var(--color-text-primary)] group-hover:text-fuchsia-400 transition-colors">
                  {page.title}
                </h3>

                <p className="mt-1 text-xs text-[var(--color-text-secondary)] line-clamp-2 leading-relaxed">
                  {page.description || 'Explore interactive metrics, breakdowns and performance trends.'}
                </p>
              </div>

              <div className="mt-4 pt-3 border-t border-[var(--border)] flex items-center gap-1.5 text-[11px] font-semibold text-fuchsia-400">
                <span>Open View</span>
              </div>
            </motion.button>
          ))}
        </div>
      </section>
    </div>
  )
}
