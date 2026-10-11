import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ChevronRight, Receipt, RefreshCw, RotateCcw, TrendingUp, DollarSign, BarChart3, PieChart as PieChartIcon, TableProperties, LockKeyhole, MoreHorizontal, Download, Bookmark } from 'lucide-react'
import { ChartCard } from '@/components/ui-kit/ChartCard'
import { GlowAreaChart } from '@/components/ui-kit/GlowAreaChart'
import { GlowCard } from '@/components/ui-kit/GlowCard'
import { KpiCard } from '@/components/ui-kit/KpiCard'
import { Skeleton } from '@/components/ui-kit/Skeleton'
import { EmptyState } from '@/components/ui-kit/EmptyState'
import { DynamicIcon } from '@/components/DynamicIcon'
import { useMetadataStore } from '@/store/metadataStore'
import { useUiStateStore } from '@/store/uiStateStore'
import { apiFetch } from '@/lib/api'
import { ConfirmDialog, Toast } from '@/components/ui-kit'
import { DEMO_USERS, useSessionStore } from '@/store/sessionStore'
import { PlaceholderPage } from '@/pages/PlaceholderPage'
import { ResponsiveContainer, CartesianGrid, Tooltip, XAxis, YAxis, BarChart, Bar, PieChart, Pie, Cell } from 'recharts'

type WidgetRow = Record<string, string | number | null>
type WidgetPayload = { rows?: WidgetRow[]; sql?: string; meta?: { date_range?: { start?: string; end?: string } } }
type WidgetFetchState = Record<string, { loading: boolean; error?: string; data?: WidgetPayload }>

const chartPalette = ['#D946EF', '#8B5CF6', '#22C55E', '#38BDF8', '#F59E0B', '#F472B6']

const formatMetricValue = (value: number, label: string) => {
  if (/revenue|gross|sales|value|target|budget|expense|cost|profit|avg_order|total/i.test(label)) {
    const abs = Math.abs(value)
    if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`
    if (abs >= 1_000) return `$${(value / 1_000).toFixed(2)}K`
    return `$${value.toLocaleString()}`
  }

  if (/pct|share|growth|rate|ratio|margin|attainment/i.test(label)) {
    return `${value.toFixed(1)}%`
  }

  if (/units|orders|count|quantity|customers|inventory/i.test(label)) {
    return value.toLocaleString()
  }

  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2)
}

const formatTableValue = (value: unknown): string => {
  if (typeof value === 'number') {
    return value.toLocaleString()
  }
  if (typeof value === 'string') {
    return value
  }
  return value == null ? '—' : String(value)
}

const friendlyWidgetType = (type?: string) => {
  if (!type) return ''
  switch (type.toLowerCase()) {
    case 'bar_chart':
      return 'Bar chart'
    case 'line_chart':
      return 'Line chart'
    case 'pie_chart':
      return 'Pie chart'
    case 'grid':
    case 'table':
      return 'Table'
    case 'kpi':
    case 'metric':
      return 'Metric'
    default:
      return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  }
}

const formatGridHeader = (column: string, widget: any, app?: any) => {
  const isVague = column.toLowerCase() === 'value' || column.toLowerCase() === 'val'
  if (!isVague) {
    return column.replace(/_/g, ' ')
  }

  // Find metric name from widget metadata
  let metricName = ''
  if (Array.isArray(widget?.measures) && widget.measures.length > 0) {
    metricName = String(widget.measures[0])
  } else if (widget?.metric) {
    metricName = String(widget.metric)
  } else if (Array.isArray(widget?.columns) && widget.columns.length > 0) {
    const measureCol = widget.columns.find((c: string) =>
      /revenue|sales|orders|units|volume|margin|profit|fee|wait|cost|expense|growth|rate|pct/i.test(c)
    )
    if (measureCol) {
      metricName = measureCol
    }
  }

  // Determine unit: ($), (%), (min), etc.
  const currencySymbol = app?.currency === 'INR' ? '₹' : '$'
  let unit = ''

  const targetText = (metricName || widget?.title || '').toLowerCase()
  if (/revenue|sales|cost|expense|fee|profit|spend|price|budget|gross|net/i.test(targetText)) {
    unit = ` (${currencySymbol})`
  } else if (/pct|percent|rate|margin|share|ratio|growth|discount/i.test(targetText)) {
    unit = ' (%)'
  } else if (/wait|time|duration|minutes|mins/i.test(targetText)) {
    unit = ' (min)'
  }

  if (metricName) {
    const cleanName = metricName
      .replace(/^sum_|^avg_|^total_/i, '')
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase())
    return `${cleanName}${unit}`
  }

  if (widget?.title) {
    const title = String(widget.title).trim()
    return `${title}${unit && !title.includes('(') ? unit : ''}`
  }

  return `Value${unit}`
}

interface DynamicPageProps {
  pageId: string
}

const widgetCardClass = 'min-h-[220px]'
const controlClassName = 'h-9 min-w-32 rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)] px-3 text-sm text-[var(--color-text-primary)] shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fuchsia-500/40'

export const DynamicPage: React.FC<DynamicPageProps> = ({ pageId }) => {
  const loading = useMetadataStore((state) => state.loading)
  const error = useMetadataStore((state) => state.error)
  const app = useMetadataStore((state) => state.app)
  const directories = useMetadataStore((state) => state.directories)
  const page = useMetadataStore((state) => state.getPage(pageId))
  const uiState = useUiStateStore((state) => state.pages[pageId])
  const initializePage = useUiStateStore((state) => state.initializePage)
  const setFilter = useUiStateStore((state) => state.setFilter)
  const setDateRange = useUiStateStore((state) => state.setDateRange)
  const setSort = useUiStateStore((state) => state.setSort)
  const resetPage = useUiStateStore((state) => state.resetPage)
  const clearHighlights = useUiStateStore((state) => state.clearHighlights)
  const activeUserId = useSessionStore((state) => state.activeUserId)
  const addSavedView = useSessionStore((state) => state.addSavedView)
  const user = DEMO_USERS.find((demoUser) => demoUser.id === activeUserId) ?? DEMO_USERS[0]
  const [widgetState, setWidgetState] = useState<WidgetFetchState>({})
  const [receiptOpen, setReceiptOpen] = useState<Record<string, boolean>>({})
  const [actionsOpen, setActionsOpen] = useState(false)
  const [pendingAction, setPendingAction] = useState<any>(null)
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const widgets = page?.widgets ?? []

  useEffect(() => {
    if (page) initializePage(page)
  }, [pageId, page, initializePage])

  useEffect(() => {
    if (!page || !uiState || !page.region_scoped || !user.regionScope) return
    const regionFilter = (page.filters ?? []).find((filter: any) => String(filter.name).toLowerCase() === 'region')
    if (!regionFilter) return
    const value = regionFilter.type === 'multi_select' ? [user.regionScope] : user.regionScope
    if (JSON.stringify(uiState.filters[regionFilter.name]) !== JSON.stringify(value)) {
      setFilter(page.id, regionFilter.name, value)
    }
  }, [page, uiState?.filters, user.regionScope, setFilter])

  useEffect(() => {
    if (!page || !uiState || !widgets.length) return

    let cancelled = false
    const controller = new AbortController()

    setWidgetState((current) => ({
      ...current,
      ...Object.fromEntries(widgets.map((widget: any) => [
        widget.id,
        { ...current[widget.id], loading: true, error: undefined },
      ])),
    }))

    const query = new URLSearchParams({
      page_id: page.id,
      filters: JSON.stringify(uiState.filters),
    })
    if (uiState.dateRange) query.set('date_range', uiState.dateRange)
    if (uiState.dateRange === 'custom' && uiState.customStart && uiState.customEnd) {
      query.set('start_date', uiState.customStart)
      query.set('end_date', uiState.customEnd)
    }
    if (uiState.sort) query.set('sort', uiState.sort)

    const fetchWidgetData = async (widget: any) => {
      try {
        const widgetQuery = new URLSearchParams(query)
        widgetQuery.set('widget_id', widget.id)
        const response = await apiFetch(`/api/widget-data?${widgetQuery.toString()}`, { signal: controller.signal })
        if (!response.ok) {
          const detail = await response.json().catch(() => null)
          throw new Error(detail?.detail ?? `Request failed with status ${response.status}`)
        }

        const data = await response.json()
        if (!cancelled) {
          setWidgetState((current) => ({ ...current, [widget.id]: { loading: false, data } }))
        }
      } catch (fetchError) {
        if (!cancelled && !(fetchError instanceof DOMException && fetchError.name === 'AbortError')) {
          setWidgetState((current) => ({
            ...current,
            [widget.id]: {
              loading: false,
              error: fetchError instanceof Error ? fetchError.message : 'Unable to load widget data',
            },
          }))
        }
      }
    }

    void Promise.all(widgets.map(fetchWidgetData))

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [pageId, page, widgets, uiState?.filters, uiState?.dateRange, uiState?.customStart, uiState?.customEnd, uiState?.sort])

  const directory = useMemo(
    () => directories.find((item) => item.id === page?.directory),
    [directories, page]
  )

  const subdirectory = useMemo(
    () => directory?.subdirectories?.find((item) => item.id === page?.subdirectory),
    [directory, page]
  )

  if (loading) {
    return (
      <div className="space-y-6 max-w-7xl mx-auto">
        <div className="space-y-3">
          <Skeleton className="h-4 w-52 rounded" />
          <Skeleton className="h-10 w-80 rounded-xl" />
          <Skeleton className="h-4 w-96 rounded" />
        </div>
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: 4 }).map((_, idx) => (
            <Skeleton key={idx} className="h-8 w-28 rounded-full" />
          ))}
        </div>
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 4 }).map((_, idx) => (
            <Skeleton key={idx} className="h-64 rounded-2xl" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-xl mx-auto mt-10">
        <GlowCard className="p-8 text-center space-y-4">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-amber-500/30 bg-amber-500/10 text-amber-300">
            <DynamicIcon name="AlertTriangle" className="h-6 w-6" />
          </div>
          <div>
            <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">Metadata unavailable</h2>
            <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
              The backend must be running before this page can load metadata.
            </p>
          </div>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="inline-flex items-center justify-center rounded-xl bg-gradient-to-r from-[#D946EF] to-[#8B5CF6] px-4 py-2 text-sm font-medium text-white shadow-[0_0_16px_rgba(217,70,239,0.3)] transition hover:opacity-90"
          >
            Retry
          </button>
        </GlowCard>
      </div>
    )
  }

  if (!page) {
    return <PlaceholderPage title="Page Not Found" section="404" is404={true} />
  }

  const highlightAnimation = (highlighted: boolean) => highlighted
    ? { boxShadow: ['0 0 0 0 rgba(217,70,239,0)', '0 0 0 3px rgba(217,70,239,0.55)', '0 0 0 0 rgba(217,70,239,0)'] }
    : { boxShadow: '0 0 0 0 rgba(217,70,239,0)' }

  const controlOptions = (options: any[] = []) => options.map((option) => ({
    id: typeof option === 'string' ? option : option.id ?? option.value ?? option.field,
    label: typeof option === 'string' ? option.replaceAll('_', ' ') : option.label ?? option.title ?? option.id ?? option.value ?? option.field,
  })).filter((option) => option.id != null)

  const showToast = (message: string) => setToastMessage(message)

  const exportGridData = () => {
    const grids = widgets.filter((widget: any) => widget.type === 'grid')
    const records: Array<Record<string, unknown>> = grids.flatMap((widget: any) => (widgetState[widget.id]?.data?.rows ?? []).map((row) => ({
      page: page.id,
      widget: widget.title,
      ...row,
    })))
    if (!records.length) {
      showToast('No loaded grid data to export.')
      return
    }
    const columns = Array.from(new Set(records.flatMap((record) => Object.keys(record))))
    const csvValue = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`
    const csv = [columns.map(csvValue).join(','), ...records.map((record) => columns.map((column) => csvValue(record[column])).join(','))].join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${page.id}.csv`
    anchor.click()
    URL.revokeObjectURL(url)
    showToast('Loaded grid data exported.')
  }

  const handlePageAction = (action: any) => {
    setActionsOpen(false)
    if (action.id === 'reset_filters') {
      resetPage(page.id)
      showToast('Filters reset.')
      return
    }
    if ((action.id === 'export_csv' || action.id === 'save_view') && action.requires_confirmation) {
      setPendingAction(action)
    }
  }

  const confirmPageAction = () => {
    if (pendingAction?.id === 'export_csv') exportGridData()
    if (pendingAction?.id === 'save_view' && uiState) {
      addSavedView({
        pageId: page.id,
        pageTitle: page.title,
        filters: uiState.filters,
        dateRange: uiState.dateRange,
        sort: uiState.sort,
      })
      showToast('View saved.')
    }
    setPendingAction(null)
  }

  const renderChartContent = (widget: any, payload?: WidgetPayload) => {
    const rows = payload?.rows ?? []
    if (!rows.length) {
      return (
        <EmptyState
          title="No data available"
          hint="This widget has no matching rows for the active filters and date window."
          inCard={false}
        />
      )
    }

    const palette = chartPalette

    if (widget.type === 'kpi') {
      const data = rows[0]
      const metric = (data?.metric as string) ?? 'value'
      const value = Number(data?.value ?? 0)
      const changePct = Number(data?.change_pct ?? 0)

      return (
        <KpiCard
          label={widget.title}
          value={value}
          prefix={/revenue|gross|sales|value|target|budget|expense|cost|profit/i.test(metric) ? '$' : ''}
          suffix={/pct|share|growth|rate|ratio|margin|attainment/i.test(metric) ? '%' : ''}
          trend={{
            value: `${changePct.toFixed(1)}%`,
            isPositive: changePct >= 0,
            variant: changePct >= 0 ? 'green' : 'red',
          }}
          caption={changePct >= 0 ? 'vs previous period' : 'below prior period'}
          icon={<TrendingUp className="w-4 h-4" />}
          iconColor={changePct >= 0 ? 'green' : 'purple'}
          glow={true}
          className="h-full min-h-[180px]"
        />
      )
    }

    if (widget.type === 'line_chart') {
      const seriesKeys = Object.keys(rows[0] ?? {}).filter((key) => key !== 'period')
      const series = seriesKeys.map((key, idx) => ({
        key,
        name: key,
        color: palette[idx % palette.length],
      }))

      return (
        <div className="h-[230px]">
          <GlowAreaChart data={rows} series={series} xAxisKey="period" height={220} />
        </div>
      )
    }

    if (widget.type === 'bar_chart') {
      return (
        <div className="h-[230px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 10, right: 8, left: -16, bottom: 20 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" stroke="var(--color-text-muted)" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="var(--color-text-muted)" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip
                formatter={(value) => [formatMetricValue(Number(value), 'value'), 'Value']}
                contentStyle={{
                  background: 'rgba(17, 17, 24, 0.95)',
                  border: '1px solid rgba(255,255,255,0.12)',
                  borderRadius: 12,
                }}
              />
              <Bar dataKey="value" radius={[10, 10, 0, 0]} fill="#D946EF" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )
    }

    if (widget.type === 'pie_chart') {
      const pieData: { name: string; value: number }[] = rows.map((row, idx) => ({
        name: String(row.label ?? `Series ${idx + 1}`),
        value: Number(row.value ?? 0),
      }))

      return (
        <div className="h-[230px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={72} paddingAngle={4}>
                {pieData.map((entry, idx) => (
                  <Cell key={`${entry.name}-${idx}`} fill={palette[idx % palette.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatMetricValue(Number(value), 'value')} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )
    }

    const columns = Object.keys(rows[0] ?? {})
    return (
      <div className="overflow-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-[var(--border)] text-[var(--color-text-secondary)]">
              {columns.map((column) => (
                <th key={column} className="py-2 pr-3 font-semibold text-xs tracking-wide">
                  {formatGridHeader(column, widget, app)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 8).map((row, idx) => (
              <tr key={`${widget.id}-${idx}`} className="border-b border-[var(--border)]/50 align-top">
                {columns.map((column) => (
                  <td key={`${column}-${idx}`} className="py-2 pr-3 text-[var(--color-text-primary)] tabular-nums">
                    {formatTableValue(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  const renderWidgetCard = (widget: any) => {
    const state = widgetState[widget.id]

    const widgetIcon = () => {
      if (widget.type === 'kpi') return <TrendingUp className="h-3.5 w-3.5" />
      if (widget.type === 'line_chart') return <BarChart3 className="h-3.5 w-3.5" />
      if (widget.type === 'pie_chart') return <PieChartIcon className="h-3.5 w-3.5" />
      if (widget.type === 'grid') return <TableProperties className="h-3.5 w-3.5" />
      return <DollarSign className="h-3.5 w-3.5" />
    }

    const cardContent = () => {
      if (!state || (state.loading && !state.data)) {
        return (
          <div className="flex min-h-32 items-center justify-center gap-2 text-xs text-[var(--color-text-muted)]">
            <RefreshCw className="h-4 w-4 animate-spin text-fuchsia-300" />
            Loading data
          </div>
        )
      }

      if (state.error) {
        return (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-3">
            <div className="rounded-full bg-rose-500/10 p-2 text-rose-300">
              <RefreshCw className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--color-text-primary)]">Widget unavailable</p>
              <p className="text-xs text-[var(--color-text-secondary)]">{state.error}</p>
            </div>
          </div>
        )
      }

      return renderChartContent(widget, state.data)
    }

    const receiptPanel = state?.data && receiptOpen[widget.id] ? (
      <div className="absolute right-3 top-14 z-10 w-[260px] rounded-xl border border-[var(--border)] bg-[var(--color-card)]/95 p-3 shadow-2xl backdrop-blur-md">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-secondary)]">Receipt</p>
        <div className="space-y-2 text-[10px] text-[var(--color-text-secondary)]">
          <div>
            <span className="font-medium text-[var(--color-text-primary)]">Page:</span> {page.id}
          </div>
          <div>
            <span className="font-medium text-[var(--color-text-primary)]">Widget:</span> {widget.id}
          </div>
          <div>
            <span className="font-medium text-[var(--color-text-primary)]">Date:</span> {state.data?.meta?.date_range?.start ?? 'n/a'} → {state.data?.meta?.date_range?.end ?? 'n/a'}
          </div>
          <div className="max-h-24 overflow-auto rounded-lg border border-[var(--border)] bg-[var(--color-card-raised)] p-2 font-mono text-[9px] leading-relaxed text-[var(--color-text-primary)]">
            {state.data?.sql ?? 'No SQL recorded'}
          </div>
        </div>
      </div>
    ) : null

    if (widget.type === 'kpi') {
      return (
        <div key={widget.id} className="relative">
          {receiptPanel}
          <div className="relative h-full">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <div className="rounded-lg border border-[var(--border)] bg-[var(--color-card-raised)] p-1.5 text-[var(--color-text-secondary)]">
                  {widgetIcon()}
                </div>
                <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">{widget.title}</p>
              </div>

              <button
                type="button"
                aria-label="Open widget receipt"
                onClick={() => setReceiptOpen((current) => ({ ...current, [widget.id]: !current[widget.id] }))}
                className="rounded-lg border border-[var(--border)] bg-[var(--color-card-raised)] p-1.5 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
              >
                <Receipt className="h-3.5 w-3.5" />
              </button>
            </div>
            {cardContent()}
          </div>
        </div>
      )
    }

    return (
      <ChartCard key={widget.id} title={widget.title} subtitle={friendlyWidgetType(widget.type)} className={widgetCardClass} glow>
        {receiptPanel}
        <div className="flex items-center justify-between pb-2">
          <div className="flex items-center gap-2 min-w-0">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--color-card-raised)] p-1.5 text-[var(--color-text-secondary)]">
              {widgetIcon()}
            </div>
          </div>

          <button
            type="button"
            aria-label="Open widget receipt"
            onClick={() => setReceiptOpen((current) => ({ ...current, [widget.id]: !current[widget.id] }))}
            className="rounded-lg border border-[var(--border)] bg-[var(--color-card-raised)] p-1.5 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
          >
            <Receipt className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="flex-1 min-h-[220px]">{cardContent()}</div>
      </ChartCard>
    )
  }

  return (
    <>
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="space-y-4">
        <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]">
          <Link to="/" className="hover:text-[var(--color-text-primary)] transition-colors">
            {app?.name ?? 'Meridian'}
          </Link>
          <ChevronRight className="h-3.5 w-3.5" />
          {directory && (
            <>
              <span className="text-[var(--color-text-secondary)]">{directory.title}</span>
              <ChevronRight className="h-3.5 w-3.5" />
            </>
          )}
          {subdirectory && (
            <>
              <span className="text-[var(--color-text-secondary)]">{subdirectory.title}</span>
              <ChevronRight className="h-3.5 w-3.5" />
            </>
          )}
          <span className="text-[#D946EF] font-medium">{page.title}</span>
        </div>

        <div className="flex flex-col gap-3 border-b border-[var(--border)] pb-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-fuchsia-500/25 bg-gradient-to-br from-fuchsia-500/15 to-purple-500/15 text-[#D946EF]">
                <DynamicIcon name={directory?.icon ?? 'Folder'} className="h-5 w-5" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)]">{page.title}</h1>
            </div>

            {!!page.actions?.length && (
              <div className="relative shrink-0">
                <button
                  type="button"
                  aria-haspopup="menu"
                  aria-expanded={actionsOpen}
                  onClick={() => setActionsOpen((open) => !open)}
                  className="inline-flex h-9 items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)] px-3 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                >
                  <MoreHorizontal className="h-4 w-4" />
                  Actions
                </button>
                {actionsOpen && (
                  <div role="menu" aria-label="Page actions" className="absolute right-0 top-full z-20 mt-2 w-56 rounded-xl border border-[var(--border)] bg-[var(--color-card)]/95 p-1.5 shadow-2xl backdrop-blur-xl">
                    {page.actions.map((action: any) => {
                      const denied = Boolean(action.requires_confirmation) && user.role === 'analyst'
                      return (
                        <button
                          key={action.id}
                          type="button"
                          role="menuitem"
                          disabled={denied}
                          title={denied ? 'Not permitted for your role' : undefined}
                          onClick={() => handlePageAction(action)}
                          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-[var(--color-text-secondary)] hover:bg-white/[0.06] hover:text-[var(--color-text-primary)] disabled:cursor-not-allowed disabled:opacity-45"
                        >
                          {action.id === 'export_csv' ? <Download className="h-3.5 w-3.5" /> : action.id === 'save_view' ? <Bookmark className="h-3.5 w-3.5" /> : <RotateCcw className="h-3.5 w-3.5" />}
                          <span>{action.label ?? action.id}</span>
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
          {user.role === 'regional_manager' && page.region_scoped && user.regionScope && (
            <span className="inline-flex w-fit items-center rounded-full border border-sky-400/25 bg-sky-400/10 px-2.5 py-1 text-xs font-medium text-sky-200">{user.regionScope} data only</span>
          )}
          <p className="text-sm text-[var(--color-text-secondary)] max-w-3xl">{page.description}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        {(page.filters ?? []).map((filter: any) => {
          const options = controlOptions(filter.allowed_values ?? filter.options ?? [])
          const regionLocked = user.role === 'regional_manager' && Boolean(page.region_scoped) && String(filter.name).toLowerCase() === 'region' && Boolean(user.regionScope)
          const filterValue = uiState?.filters[filter.name] ?? filter.default ?? filter.default_value
          const selectedValue = regionLocked
            ? filter.type === 'multi_select' ? [user.regionScope] : user.regionScope
            : filter.type === 'multi_select'
            ? Array.isArray(filterValue) ? filterValue : filterValue == null ? [] : [filterValue]
            : Array.isArray(filterValue) ? filterValue[0] ?? '' : filterValue ?? ''
          const highlighted = uiState?.highlights.includes(`filter:${filter.name}`) ?? false

          return (
            <motion.label
              key={`${page.id}-${filter.name}`}
              className="flex flex-col gap-1.5 rounded-xl px-1"
              animate={highlightAnimation(highlighted)}
              transition={{ duration: 1.5, ease: 'easeInOut' }}
              onAnimationComplete={() => highlighted && clearHighlights(page.id)}
            >
              <span className="flex items-center gap-1 px-1 text-xs font-medium text-[var(--color-text-secondary)]">
                {filter.label ?? filter.name}
                {regionLocked && <span title="Restricted to your region"><LockKeyhole aria-label="Restricted to your region" className="h-3 w-3 text-sky-300" /></span>}
              </span>
              <select
                aria-label={filter.label ?? filter.name}
                className={`${controlClassName} ${filter.type === 'multi_select' ? 'h-auto min-h-20 py-2' : ''}`}
                multiple={filter.type === 'multi_select'}
                size={filter.type === 'multi_select' ? Math.min(options.length, 4) : undefined}
                value={selectedValue}
                disabled={regionLocked}
                title={regionLocked ? 'Restricted to your region' : undefined}
                onChange={(event) => {
                  const value = filter.type === 'multi_select'
                    ? Array.from(event.currentTarget.selectedOptions, (option) => option.value)
                    : event.currentTarget.value || null
                  setFilter(page.id, filter.name, value)
                }}
              >
                {filter.type !== 'multi_select' && <option value="">All</option>}
                {options.map((option: any) => (
                  <option key={option.id} value={option.id}>{option.label}</option>
                ))}
              </select>
            </motion.label>
          )
        })}

        {!!page.date_range_options?.length && (
          <motion.label
            className="flex flex-col gap-1.5 rounded-xl px-1"
            animate={highlightAnimation(uiState?.highlights.includes('date_range') ?? false)}
            transition={{ duration: 1.5, ease: 'easeInOut' }}
            onAnimationComplete={() => uiState?.highlights.includes('date_range') && clearHighlights(page.id)}
          >
            <span className="px-1 text-xs font-medium text-[var(--color-text-secondary)]">Date range</span>
            <select
              aria-label="Date range"
              className={controlClassName}
              value={uiState?.dateRange ?? page.default_date_range ?? page.date_range_options?.[0] ?? ''}
              onChange={(event) => setDateRange(page.id, event.currentTarget.value)}
            >
              {controlOptions(page.date_range_options).map((option: any) => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
            </select>
            {uiState?.dateRange === 'custom' && (
              <div className="mt-2 flex gap-2">
                <input
                  type="date"
                  aria-label="Custom date range start"
                  value={uiState.customStart ?? ''}
                  className={`${controlClassName} min-w-0`}
                  onChange={(event) => useUiStateStore.getState().applyUiState(page.id, { customStart: event.currentTarget.value || null }, 'user')}
                />
                <input
                  type="date"
                  aria-label="Custom date range end"
                  value={uiState.customEnd ?? ''}
                  className={`${controlClassName} min-w-0`}
                  onChange={(event) => useUiStateStore.getState().applyUiState(page.id, { customEnd: event.currentTarget.value || null }, 'user')}
                />
              </div>
            )}
          </motion.label>
        )}

        {!!page.sort_options?.length && (
          <motion.label
            className="flex flex-col gap-1.5 rounded-xl px-1"
            animate={highlightAnimation(uiState?.highlights.includes('sort') ?? false)}
            transition={{ duration: 1.5, ease: 'easeInOut' }}
            onAnimationComplete={() => uiState?.highlights.includes('sort') && clearHighlights(page.id)}
          >
            <span className="px-1 text-xs font-medium text-[var(--color-text-secondary)]">Sort</span>
            <select
              aria-label="Sort"
              className={controlClassName}
              value={uiState?.sort ?? page.default_sort?.field ?? controlOptions(page.sort_options)[0]?.id ?? ''}
              onChange={(event) => setSort(page.id, event.currentTarget.value || null)}
            >
              {controlOptions(page.sort_options).map((option: any) => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
            </select>
          </motion.label>
        )}

        <button
          type="button"
          onClick={() => resetPage(page.id)}
          className="inline-flex h-9 items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)] px-3 text-sm text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Reset
        </button>
      </div>

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {widgets.map((widget: any) => renderWidgetCard(widget))}
      </div>
    </div>
    <ConfirmDialog
      open={Boolean(pendingAction)}
      title={pendingAction?.label ?? 'Confirm action'}
      description={pendingAction?.id === 'export_csv' ? 'Export the grid data currently loaded on this page.' : 'Save this page with its current filters, date range, and sort.'}
      consequences={pendingAction?.id === 'export_csv' ? ['A CSV file will be downloaded to your device.'] : ['This view will be stored in this browser for the active demo user.']}
      confirmLabel={pendingAction?.id === 'export_csv' ? 'Export CSV' : 'Save view'}
      onCancel={() => setPendingAction(null)}
      onConfirm={confirmPageAction}
    />
    <Toast message={toastMessage} onDismiss={() => setToastMessage(null)} />
    </>
  )
}
