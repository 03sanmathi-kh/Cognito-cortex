import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, ArrowUp, Bot, Check, LoaderCircle, Mic, MicOff, Receipt, RotateCcw, Sparkles, Square, Volume2, VolumeX, X } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { getSpeechRecognitionClass, cleanSpokenText, selectEnglishVoice, type SpeechRecognitionInstance } from '@/lib/speech'
import { RobotMascot } from './RobotMascot'
import { useCognitoPilotStore } from '@/store/cognitoPilotStore'
import { useMetadataStore } from '@/store/metadataStore'
import { DEMO_USERS, useSessionStore } from '@/store/sessionStore'
import { useUiStateStore } from '@/store/uiStateStore'

type AgentPlanStep = { tool: string; args: Record<string, unknown> }
type AgentSuggestion = { id: string; title: string; route: string }
export type AgentReceipt = {
  label: string
  value: number | string
  formatted?: string
  page_id: string | null
  route: string | null
  filters?: Record<string, unknown>
  date_range?: string | { start?: string; end?: string; [key: string]: any } | null
  sort?: string | null
  query_index?: number
}
type AgentResponse = {
  plan: AgentPlanStep[]
  answer: string
  evidence: { page: { id: string; title: string } | null; filters: Record<string, unknown>; query: string | null }
  chart: { title: string; chart_type: 'bar' | 'line' | 'pie'; columns: string[]; rows: Array<Record<string, string | number>> } | null
  error: { message: string; suggestions: AgentSuggestion[] } | null
  clarify: string | null
  outcome?: 'answered' | 'clarify' | 'refused' | 'error'
  refusal_reason?: 'not_in_app' | 'not_permitted' | 'out_of_scope' | 'out_of_data_range' | null
  suggestions?: Array<string | AgentSuggestion>
  session_id?: string | null
  analysis?: Record<string, any> | null
  faithfulness?: { checked: number; unverified: any[] } | null
  receipts?: AgentReceipt[]
  requires_confirmation?: boolean
  confirmation_reason?: string | null
}
type UndoTarget = {
  page_id: string | null
  path: string
  filters: Record<string, unknown>
  date_range: string | null
  custom_start?: string | null
  custom_end?: string | null
  sort: string | null
  sort_direction?: string | null
  direction?: string | null
}
type ChatMessage = {
  id: number
  role: 'user' | 'assistant'
  content: string
  result?: AgentResponse
  confirmationStatus?: 'pending' | 'applied' | 'cancelled'
  verificationStatus?: 'Verified' | 'Mismatch' | null
  undoBefore?: UndoTarget | null
}

const chartColors = ['#D946EF', '#8B5CF6', '#22C55E', '#38BDF8']
const planLabel: Record<string, string> = {
  navigate: 'Open page',
  set_filter: 'Set filter',
  set_date_range: 'Set date range',
  sort: 'Sort data',
  run_query: 'Query data',
  make_chart: 'Build chart',
}

const prettyArgs = (step: AgentPlanStep) => {
  const { tool, args } = step
  if (tool === 'make_chart') return String(args.type ?? 'chart')
  if (tool === 'navigate') return String(args.page_id ?? '')
  if (tool === 'set_filter') return `${String(args.field)}: ${Array.isArray(args.value) ? args.value.join(', ') : String(args.value)}`
  if (tool === 'set_date_range') return `${String(args.start)} to ${String(args.end)}`
  if (tool === 'sort') return `${String(args.field)} (${String(args.order ?? args.direction ?? 'asc')})`
  if (tool === 'run_query') return String(args.page_id ?? '')
  return ''
}

export const stepToPlainWords = (step: AgentPlanStep, pagesList: Array<{ id: string; title?: string }>): string => {
  const { tool, args } = step
  if (tool === 'navigate') {
    const pageId = String(args.page_id ?? '')
    const page = pagesList.find((p) => p.id === pageId)
    return `Open ${page?.title || pageId}`
  }
  if (tool === 'set_filter') {
    const field = String(args.field ?? '')
    const val = Array.isArray(args.value) ? args.value.join(', ') : String(args.value ?? '')
    return `Set ${field} = ${val}`
  }
  if (tool === 'set_date_range') {
    const period = String(args.period ?? '')
    if (period && period !== 'custom') {
      return `Set date range = ${period.replace(/_/g, ' ')}`
    }
    return `Set date range (${String(args.start ?? '')} to ${String(args.end ?? '')})`
  }
  if (tool === 'sort') {
    const field = String(args.field ?? '')
    const order = String(args.order ?? args.direction ?? 'asc')
    return `Sort by ${field} (${order})`
  }
  if (tool === 'run_query') {
    const pageId = String(args.page_id ?? '')
    const page = pagesList.find((p) => p.id === pageId)
    return `Query data for ${page?.title || pageId || 'view'}`
  }
  if (tool === 'make_chart') {
    return `Create ${String(args.type ?? 'bar')} chart`
  }
  return `${planLabel[tool] ?? tool}: ${prettyArgs(step)}`
}

function formatMessageText(text: string): React.ReactNode {
  if (!text) return null
  const lines = text.split('\n')
  return (
    <div className="space-y-1.5 text-sm leading-relaxed text-[var(--color-text-primary)]">
      {lines.map((line, lineIdx) => {
        const trimmed = line.trim()
        if (!trimmed) {
          return <div key={lineIdx} className="h-1.5" />
        }
        const isBullet = trimmed.startsWith('- ') || trimmed.startsWith('* ')
        const content = isBullet ? trimmed.slice(2) : line

        const parts = content.split(/\*\*(.*?)\*\*/)
        const rendered = parts.map((part, pIdx) => {
          if (pIdx % 2 === 1) {
            return (
              <strong key={pIdx} className="font-semibold text-[var(--color-text-primary)]">
                {part}
              </strong>
            )
          }
          return part
        })

        if (isBullet) {
          return (
            <div key={lineIdx} className="flex items-start gap-2 pl-1.5">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-text-secondary)]" />
              <div className="flex-1">{rendered}</div>
            </div>
          )
        }

        return <div key={lineIdx}>{rendered}</div>
      })}
    </div>
  )
}

function formatDateShort(iso: string): string {
  try {
    const parts = iso.split('-')
    if (parts.length === 3) {
      const year = parts[0]
      const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
      const mIdx = parseInt(parts[1], 10) - 1
      const day = parseInt(parts[2], 10)
      if (mIdx >= 0 && mIdx < 12) {
        return `${monthNames[mIdx]} ${day}, ${year}`
      }
    }
  } catch {}
  return iso
}

function formatEvidencePeriod(period: any): string {
  if (!period) return 'This quarter (Jul 1 – Sep 30, 2026)'
  if (typeof period === 'string') {
    const p = period.trim().toLowerCase()
    if (p === 'this_quarter') return 'This quarter (Jul 1 – Sep 30, 2026)'
    if (p === 'last_quarter') return 'Last quarter (Apr 1 – Jun 30, 2026)'
    if (p === 'this_month') return 'This month (Sep 1 – Sep 30, 2026)'
    if (p === 'last_month') return 'Last month (Aug 1 – Aug 31, 2026)'
    if (p === 'this_year') return 'This year (Jan 1 – Sep 30, 2026)'
    if (p === 'last_7_days') return 'Last 7 days (Sep 24 – Sep 30, 2026)'
    if (p === 'last_30_days') return 'Last 30 days (Sep 1 – Sep 30, 2026)'
    if (period.includes('(') || period.includes('–')) return period
    return `${period.replace(/_/g, ' ')} (Jul 1 – Sep 30, 2026)`
  }
  if (typeof period === 'object') {
    const start = period.start ? formatDateShort(period.start) : ''
    const end = period.end ? formatDateShort(period.end) : ''
    const label = period.label || (period.start?.includes('2026-07') ? 'This quarter' : (period.start?.includes('2026-04') ? 'Last quarter' : ''))
    if (start && end) {
      return label ? `${label} (${start} – ${end})` : `${start} – ${end}`
    }
  }
  return 'This quarter (Jul 1 – Sep 30, 2026)'
}

function formatFilterValues(filters: any): string[] {
  if (!filters) return []
  if (Array.isArray(filters)) {
    return filters.flatMap((f) => formatFilterValues(f))
  }
  if (typeof filters === 'object') {
    const items: string[] = []
    for (const [, val] of Object.entries(filters)) {
      if (val === null || val === undefined || val === '') continue
      if (Array.isArray(val)) {
        if (val.length > 0 && val.length < 4) {
          items.push(val.join(', '))
        }
      } else {
        items.push(String(val))
      }
    }
    return items
  }
  return [String(filters)]
}

function buildEvidenceLines(evidence: any): string[] {
  if (!evidence) return []
  const executedQueries = Array.isArray(evidence.queries) && evidence.queries.length > 0
    ? evidence.queries
    : null

  if (executedQueries) {
    const lines: string[] = []
    const seen = new Set<string>()
    for (const q of executedQueries) {
      const filterVals = formatFilterValues(q.filters)
      const periodStr = formatEvidencePeriod(q.period || evidence.period || evidence.date_range)
      const parts = [...filterVals, periodStr].filter(Boolean)
      const line = parts.join(' · ')
      if (line && !seen.has(line)) {
        seen.add(line)
        lines.push(line)
      }
    }
    if (lines.length > 0) return lines
  }

  const filterVals = formatFilterValues(evidence.filters)
  const periodStr = formatEvidencePeriod(evidence.period || evidence.date_range)
  const parts = [...filterVals, periodStr].filter(Boolean)
  const line = parts.length > 0 ? parts.join(' · ') : `All items · ${periodStr}`
  return [line]
}

interface GroupedReceiptFact {
  label: string
  value: string
  rawValue: number
}

interface GroupedReceipt {
  item: string
  facts: GroupedReceiptFact[]
  representativeReceipt: any
  pageInfo?: string
}

function groupReceipts(receipts: any[]): GroupedReceipt[] {
  const groupsMap = new Map<string, GroupedReceipt>()

  for (const receipt of receipts) {
    let item = receipt.item
    let factLabel = ''

    if (!item) {
      const rawLabel = String(receipt.label || '').trim()
      const match = rawLabel.match(/^(.*?)\s+(% change|share of change|share|change|current|previous)$/i)
      if (match) {
        item = match[1].trim()
        factLabel = match[2].trim().toLowerCase()
        if (factLabel === 'share') factLabel = 'share of change'
      } else {
        item = rawLabel
        factLabel = 'value'
      }
    } else {
      const rawLabel = String(receipt.label || '').trim()
      factLabel = rawLabel.replace(item, '').trim().toLowerCase()
      if (factLabel === 'share') factLabel = 'share of change'
      if (!factLabel) factLabel = 'value'
    }

    if (!groupsMap.has(item)) {
      groupsMap.set(item, {
        item,
        facts: [],
        representativeReceipt: receipt,
        pageInfo: receipt.page_id || receipt.route ? String(receipt.page_id || receipt.route) : undefined,
      })
    }

    const group = groupsMap.get(item)!
    if (!group.representativeReceipt.route && receipt.route) {
      group.representativeReceipt = receipt
    }
    const formattedVal = receipt.formatted || String(receipt.value)
    if (!group.facts.some((f) => f.label === factLabel && f.value === formattedVal)) {
      group.facts.push({
        label: factLabel,
        value: formattedVal,
        rawValue: receipt.value,
      })
    }
  }

  return Array.from(groupsMap.values())
}

function ContributorRow({ item, idx }: { item: any; idx: number }) {
  const label = item.label || item.dimension || item.segment || `Item ${idx + 1}`
  const change = item.change ?? 0
  const rawShare = item.share !== undefined && item.share !== null
    ? item.share
    : item.share_of_total_change
  const hasShare = rawShare !== undefined && rawShare !== null
  const share = hasShare ? Math.abs(rawShare) : null
  const sharePct = share !== null ? (share * 100).toFixed(1) : null
  const barWidth = share !== null ? Math.min(100, Math.max(3, Math.round(share * 100))) : 0

  const formattedChange = item.formatted_change || `${change < 0 ? '-' : ''}$${Math.abs(change).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  const pctChangeVal = item.pct_change ?? item.percent_change
  const pctChangeStr = pctChangeVal !== undefined && pctChangeVal !== null
    ? `${pctChangeVal > 0 ? '+' : ''}${Number(pctChangeVal).toFixed(1)}% vs before`
    : ''

  return (
    <div className="space-y-1">
      <div className="flex items-start justify-between gap-2 text-[11px]">
        <span className="font-medium text-[var(--color-text-primary)] min-w-0 break-words leading-tight flex-1">
          {label}
        </span>
        <span className="font-mono text-[10px] text-[var(--color-text-secondary)] shrink-0 text-right whitespace-nowrap pl-1">
          {hasShare
            ? `${formattedChange} · ${sharePct}% share of change${pctChangeStr ? ` · ${pctChangeStr}` : ''}`
            : `${formattedChange}${pctChangeStr ? ` · ${pctChangeStr}` : ''}`}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--border)]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-fuchsia-500 to-violet-500"
          style={{ width: `${barWidth}%` }}
        />
      </div>
    </div>
  )
}

function DriverGroupBarChart({ items }: { items: any[] }) {
  if (!items || items.length === 0) return null
  const displayItems = items.slice(0, 4)
  const maxAbsChange = Math.max(
    ...displayItems.map((it) => Math.abs(Number(it.change ?? it.value ?? it.absolute_change ?? 1))),
    1
  )

  const rowHeight = 26
  const chartHeight = displayItems.length * rowHeight

  return (
    <div className="my-1.5 w-full rounded-lg bg-black/10 p-1.5 border border-[var(--border)]">
      <svg
        viewBox={`0 0 280 ${chartHeight}`}
        className="w-full overflow-visible font-sans"
        style={{ height: chartHeight }}
      >
        {displayItems.map((item, i) => {
          const label = String(item.label || item.dimension || item.segment || `Item ${i + 1}`)
          const rawVal = Number(item.change ?? item.value ?? item.absolute_change ?? 0)
          const isNeg = rawVal < 0
          const barColor = isNeg ? 'var(--color-danger, #F43F5E)' : 'var(--color-green, #22C55E)'
          const absVal = Math.abs(rawVal)
          const barWidth = Math.max(4, Math.min(180, Math.round((absVal / maxAbsChange) * 180)))
          const formattedChange = item.formatted_change
            || `${rawVal < 0 ? '-' : '+'}$${absVal.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
          const y = i * rowHeight

          return (
            <g key={i}>
              <text
                x="0"
                y={y + 11}
                fill="var(--color-text-primary)"
                fontSize="10"
                fontWeight="500"
              >
                {label.length > 15 ? label.slice(0, 13) + '…' : label}
              </text>
              <text
                x="280"
                y={y + 11}
                textAnchor="end"
                fill={barColor}
                fontSize="10"
                fontFamily="monospace"
                fontWeight="600"
              >
                {formattedChange}
              </text>
              <rect
                x="0"
                y={y + 15}
                width="280"
                height="4.5"
                rx="2"
                fill="var(--border)"
                opacity="0.3"
              />
              <rect
                x="0"
                y={y + 15}
                width={barWidth}
                height="4.5"
                rx="2"
                fill={barColor}
              />
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function TrendLineChart({ points, summary }: { points?: any[]; summary?: any }) {
  const pts = points && points.length >= 2 ? points : (summary?.points || [])
  if (!pts || pts.length < 2) return null
  const numPoints = pts.map((p: any, idx: number) => ({
    period: String(p.period || `P${idx + 1}`),
    value: Number(p.value ?? 0),
    formatted: p.formatted || String(p.value ?? 0),
  }))

  const values = numPoints.map((p: any) => p.value)
  const minVal = Math.min(...values)
  const maxVal = Math.max(...values)
  const range = (maxVal - minVal) || 1

  const svgWidth = 280
  const svgHeight = 90
  const padTop = 18
  const padBottom = 20
  const padX = 24
  const drawWidth = svgWidth - padX * 2
  const drawHeight = svgHeight - padTop - padBottom

  const coords = numPoints.map((p: any, i: number) => {
    const x = padX + (i / (numPoints.length - 1)) * drawWidth
    const y = padTop + drawHeight - ((p.value - minVal) / range) * drawHeight
    return { x, y, ...p }
  })

  let maxIdx = 0
  let minIdx = 0
  values.forEach((v: number, idx: number) => {
    if (v > values[maxIdx]) maxIdx = idx
    if (v < values[minIdx]) minIdx = idx
  })

  const pathD = coords.reduce((acc: string, pt: any, i: number) => `${acc} ${i === 0 ? 'M' : 'L'} ${pt.x} ${pt.y}`, '')
  const areaD = `${pathD} L ${coords[coords.length - 1].x} ${padTop + drawHeight} L ${coords[0].x} ${padTop + drawHeight} Z`

  const highPt = coords[maxIdx]
  const lowPt = coords[minIdx]

  return (
    <div className="mt-3 rounded-xl border border-[var(--border)] bg-black/10 p-2.5">
      <div className="mb-1 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
        <span>Trend Overview</span>
        <span className="font-mono text-[9px] text-[var(--color-text-muted)]">{pts.length} points</span>
      </div>
      <svg
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        className="w-full overflow-visible font-sans"
        style={{ height: svgHeight }}
      >
        <defs>
          <linearGradient id="trendAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#D946EF" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#D946EF" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        <path d={areaD} fill="url(#trendAreaGrad)" />
        <path
          d={pathD}
          fill="none"
          stroke="var(--color-accent-magenta, #D946EF)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {highPt && (
          <g>
            <circle
              cx={highPt.x}
              cy={highPt.y}
              r="4"
              fill="var(--color-green, #22C55E)"
              stroke="#FFFFFF"
              strokeWidth="1.5"
            />
            <text
              x={highPt.x}
              y={Math.max(12, highPt.y - 7)}
              textAnchor="middle"
              fontSize="9"
              fontWeight="700"
              fill="var(--color-green, #22C55E)"
            >
              High: ${highPt.value >= 1000 ? `${(highPt.value / 1000).toFixed(1)}k` : highPt.value.toFixed(0)}
            </text>
          </g>
        )}
        {lowPt && (
          <g>
            <circle
              cx={lowPt.x}
              cy={lowPt.y}
              r="4"
              fill="var(--color-danger, #F43F5E)"
              stroke="#FFFFFF"
              strokeWidth="1.5"
            />
            <text
              x={lowPt.x}
              y={Math.min(svgHeight - 2, lowPt.y + 13)}
              textAnchor="middle"
              fontSize="9"
              fontWeight="700"
              fill="var(--color-danger, #F43F5E)"
            >
              Low: ${lowPt.value >= 1000 ? `${(lowPt.value / 1000).toFixed(1)}k` : lowPt.value.toFixed(0)}
            </text>
          </g>
        )}
        <text
          x={padX}
          y={svgHeight - 2}
          textAnchor="start"
          fontSize="9"
          fill="var(--color-text-muted)"
        >
          {coords[0].period}
        </text>
        <text
          x={svgWidth - padX}
          y={svgHeight - 2}
          textAnchor="end"
          fontSize="9"
          fill="var(--color-text-muted)"
        >
          {coords[coords.length - 1].period}
        </text>
      </svg>
    </div>
  )
}

function AnalysisCard({
  analysis,
  faithfulness,
}: {
  analysis: Record<string, any>
  faithfulness?: { checked: number; unverified: any[] } | null
}) {
  const headline = analysis.headline || `${analysis.metric || 'Metric'} Analysis`
  const baseline = analysis.baseline || {}
  const curVal = baseline.current_value
  const prevVal = baseline.previous_value
  const pctChange = baseline.percent_change
  const isDown = pctChange !== undefined && pctChange < 0
  const isUp = pctChange !== undefined && pctChange > 0

  const topDimensions = (analysis.top_dimensions || []).slice(0, 2)
  const topSegments = (analysis.top_segments || []).slice(0, 3)
  const fallbackContributors = (analysis.contributors || []).slice(0, 5)

  const steepestDecliners = (analysis.steepest_decliners || []).length > 0
    ? analysis.steepest_decliners
    : (analysis.top_dimensions || []).flatMap((d: any) => d.steepest_decliners || [])
  const steepestRisers = (analysis.steepest_risers || []).length > 0
    ? analysis.steepest_risers
    : (analysis.top_dimensions || []).flatMap((d: any) => d.steepest_risers || [])
  const steepestItems = isUp ? steepestRisers : steepestDecliners
  const steepestSegments = analysis.steepest_segments || []
  const allSteepestRaw = [...steepestItems.slice(0, 3), ...steepestSegments.slice(0, 3)]
  const allSteepest = [...allSteepestRaw].sort((a: any, b: any) => {
    const pA = Number(a.pct_change ?? a.percent_change ?? 0)
    const pB = Number(b.pct_change ?? b.percent_change ?? 0)
    if (isUp) {
      return pB - pA
    }
    if (pA !== pB) return pA - pB
    return Math.abs(Number(b.change ?? 0)) - Math.abs(Number(a.change ?? 0))
  })

  const queries = analysis.queries || []
  const unverified = faithfulness?.unverified || []

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)] p-3 space-y-2.5">
      {/* Summary Header Card */}
      <div className="rounded-xl border border-[var(--border)] bg-black/15 p-2.5 shadow-sm">
        <div className="flex items-center justify-between gap-2 border-b border-[var(--border)] pb-2">
          <div className="min-w-0">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
              {analysis.metric || 'Metric'} Analysis
            </span>
            <h4 className="text-xs font-semibold text-[var(--color-text-primary)] truncate">{headline}</h4>
          </div>
          {pctChange !== undefined && (
            <span
              className={`shrink-0 inline-flex items-center rounded-md px-2 py-0.5 text-xs font-bold ${
                isDown
                  ? 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                  : isUp
                  ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                  : 'bg-zinc-500/15 text-zinc-300 border border-zinc-500/30'
              }`}
            >
              {pctChange > 0 ? '+' : ''}{Number(pctChange).toFixed(1)}%
            </span>
          )}
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
          <div>
            <span className="text-[10px] text-[var(--color-text-muted)]">Current</span>
            <p className="font-mono font-semibold text-[var(--color-text-primary)]">
              {typeof curVal === 'number' ? `$${curVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : (curVal ? `$${curVal}` : 'N/A')}
            </p>
          </div>
          <div>
            <span className="text-[10px] text-[var(--color-text-muted)]">Previous</span>
            <p className="font-mono text-[var(--color-text-secondary)]">
              {typeof prevVal === 'number' ? `$${prevVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : (prevVal ? `$${prevVal}` : 'N/A')}
            </p>
          </div>
        </div>
        {analysis.mixed_change && (
          <p className="mt-1.5 border-t border-[var(--border)] pt-1 text-[10px] text-[var(--color-text-muted)]">
            Mixed: some items rose, others fell
          </p>
        )}
      </div>

      {/* SVG Trend Line Chart if trend points present */}
      {(analysis.points?.length || analysis.type === 'trend') && (
        <TrendLineChart points={analysis.points} summary={analysis.summary} />
      )}

      {/* Grouped by dimension (top 2) with SVG Horizontal Bar Chart */}
      {topDimensions.length > 0 ? (
        <div className="space-y-3">
          {topDimensions.map((dim: any, dIdx: number) => (
            <div key={dIdx} className="space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                {dim.dimension_label || dim.dimension} Drivers
              </p>
              <DriverGroupBarChart items={dim.contributors || []} />
              <div className="space-y-1.5">
                {(dim.contributors || []).slice(0, 3).map((item: any, idx: number) => (
                  <ContributorRow key={idx} item={item} idx={idx} />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : fallbackContributors.length > 0 ? (
        <div className="space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
            Main Contributors
          </p>
          <DriverGroupBarChart items={fallbackContributors} />
          <div className="space-y-1.5">
            {fallbackContributors.map((item: any, idx: number) => (
              <ContributorRow key={idx} item={item} idx={idx} />
            ))}
          </div>
        </div>
      ) : null}

      {/* Top segments row group when present */}
      {topSegments.length > 0 && (
        <div className="border-t border-[var(--border)] pt-2 space-y-1.5">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
            Top Segments
          </p>
          <DriverGroupBarChart items={topSegments} />
          <div className="space-y-1.5">
            {topSegments.map((seg: any, idx: number) => (
              <ContributorRow key={idx} item={seg} idx={idx} />
            ))}
          </div>
        </div>
      )}

      {/* Steepest drops group (decliners and segments) */}
      {allSteepest.length > 0 && (
        <div className="border-t border-[var(--border)] pt-2 space-y-1.5">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
            {isUp ? 'Steepest Risers' : 'Steepest Drops'}
          </p>
          <DriverGroupBarChart items={allSteepest} />
          <div className="space-y-1.5">
            {allSteepest.map((item: any, idx: number) => (
              <ContributorRow key={idx} item={item} idx={idx} />
            ))}
          </div>
        </div>
      )}

      {/* Collapsible Queries Used */}
      {queries.length > 0 && (
        <details className="border-t border-[var(--border)] pt-2">
          <summary className="cursor-pointer text-[10px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]">
            Queries used ({queries.length})
          </summary>
          <div className="mt-1.5 max-h-32 space-y-1.5 overflow-auto">
            {queries.map((q: any, qIdx: number) => (
              <div key={qIdx} className="rounded border border-[var(--border)] bg-black/20 p-2 text-[9px]">
                <pre className="whitespace-pre-wrap break-all font-mono text-[var(--color-text-muted)]">{q.sql}</pre>
                {q.parameters && q.parameters.length > 0 && (
                  <p className="mt-1 font-mono text-[var(--color-text-secondary)]">
                    Params: {JSON.stringify(q.parameters)}
                  </p>
                )}
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Unverified note */}
      {unverified.length > 0 && (
        <p className="mt-1 text-[10px] text-amber-300/80">
          Some numbers could not be verified.
        </p>
      )}
    </section>
  )
}

export function StreamingAnswerText({
  fullText,
  isFinished,
  onFinish,
}: {
  fullText: string
  isFinished: boolean
  onFinish: () => void
}) {
  const [revealedChars, setRevealedChars] = useState(isFinished ? fullText.length : 0)
  const onFinishRef = useRef(onFinish)
  useEffect(() => {
    onFinishRef.current = onFinish
  })

  useEffect(() => {
    if (isFinished) {
      setRevealedChars(fullText.length)
      return
    }
    if (!fullText) {
      onFinishRef.current()
      return
    }
    const interval = setInterval(() => {
      setRevealedChars((prev) => {
        const next = prev + 30
        if (next >= fullText.length) {
          clearInterval(interval)
          onFinishRef.current()
          return fullText.length
        }
        return next
      })
    }, 50)
    return () => clearInterval(interval)
  }, [fullText, isFinished])

  const visibleText = isFinished ? fullText : fullText.slice(0, revealedChars)

  return (
    <div className="flex-1 text-sm leading-relaxed">
      <div className="inline">
        {formatMessageText(visibleText)}
        {!isFinished && (
          <span
            className="inline-block w-1.5 h-3.5 ml-1 align-middle bg-fuchsia-400"
            style={{ animation: 'cursor-blink 0.8s infinite' }}
          />
        )}
      </div>
      {!isFinished && (
        <div className="mt-1.5">
          <button
            type="button"
            onClick={() => {
              setRevealedChars(fullText.length)
              onFinishRef.current()
            }}
            className="inline-flex items-center rounded-md bg-fuchsia-500/15 border border-fuchsia-500/30 px-2 py-0.5 text-[11px] font-medium text-fuchsia-300 hover:bg-fuchsia-500/25 transition-colors"
          >
            Skip
          </button>
        </div>
      )}
    </div>
  )
}

export function RobotMascotButton({
  isOpen,
  isLoading,
  isSpeaking = false,
  onClick,
}: {
  isOpen: boolean
  isLoading: boolean
  isSpeaking?: boolean
  onClick: () => void
}) {
  const showThinking = isLoading && !isSpeaking
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={isOpen ? 'Close Cognito Pilot' : 'Open Cognito Pilot'}
      className={`mascot-animated fixed bottom-6 z-50 flex h-14 w-14 items-center justify-center rounded-2xl border border-fuchsia-500/40 bg-gradient-to-br from-fuchsia-600 via-purple-600 to-violet-700 p-2 shadow-[0_4px_24px_rgba(217,70,239,0.4)] transition-all hover:scale-105 active:scale-95 group focus:outline-none focus:ring-2 focus:ring-fuchsia-400 ${
        isOpen ? 'right-[456px]' : 'right-6'
      }`}
      style={{
        animation: showThinking
          ? 'mascot-fast-bob 0.85s ease-in-out infinite'
          : isSpeaking
          ? 'mascot-bob 1.5s ease-in-out infinite'
          : 'mascot-bob 3s ease-in-out infinite',
      }}
    >
      <svg
        viewBox="0 0 64 64"
        className="h-10 w-10 overflow-visible drop-shadow"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <line x1="32" y1="14" x2="32" y2="6" stroke="#FAF5FF" strokeWidth="2.5" strokeLinecap="round" />
        <circle
          cx="32"
          cy="5"
          r={showThinking ? '4' : '3.5'}
          fill={showThinking ? '#FDE047' : isSpeaking ? '#C084FC' : '#38BDF8'}
          className="robot-antenna"
        />
        <circle cx="32" cy="5" r="2" fill="#FAF5FF" />
        <rect x="12" y="22" width="4" height="8" rx="2" fill="#C084FC" />
        <rect x="48" y="22" width="4" height="8" rx="2" fill="#C084FC" />
        <rect x="16" y="14" width="32" height="24" rx="8" fill="#FFFFFF" />
        <rect x="20" y="18" width="24" height="14" rx="5" fill="#090D16" />
        {showThinking ? (
          <>
            <circle cx="27" cy="25" r="2.5" fill="#38BDF8" className="robot-eye" />
            <circle cx="37" cy="25" r="2.5" fill="#D946EF" className="robot-eye" />
            <path d="M28 29 Q32 27 36 29" stroke="#38BDF8" strokeWidth="1.5" strokeLinecap="round" />
          </>
        ) : isSpeaking ? (
          <>
            <circle cx="27" cy="24" r="2.5" fill="#38BDF8" className="robot-eye" />
            <circle cx="37" cy="24" r="2.5" fill="#38BDF8" className="robot-eye" />
            <path d="M28 29 Q32 27 36 29" stroke="#38BDF8" strokeWidth="1.5" strokeLinecap="round" />
          </>
        ) : (
          <>
            <circle cx="27" cy="24" r="2.5" fill="#38BDF8" className="robot-eye" />
            <circle cx="37" cy="24" r="2.5" fill="#38BDF8" className="robot-eye" />
            <path d="M28 27 Q32 30 36 27" stroke="#38BDF8" strokeWidth="1.5" strokeLinecap="round" />
          </>
        )}
        <rect x="29" y="38" width="6" height="3" rx="1.5" fill="#C084FC" />
        <rect x="18" y="41" width="28" height="16" rx="6" fill="#F1F1F7" />
        <rect x="23" y="44" width="18" height="9" rx="3" fill="#090D16" />
        <circle cx="28" cy="48.5" r="1.5" fill="#D946EF" />
        <circle cx="32" cy="48.5" r="1.5" fill="#8B5CF6" />
        <circle cx="36" cy="48.5" r="1.5" fill="#22C55E" />
      </svg>
      {showThinking ? (
        <span className="absolute -top-1 -right-1 flex h-4 w-4">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-4 w-4 bg-yellow-500 border-2 border-white items-center justify-center text-[8px] font-bold text-black">
            ?
          </span>
        </span>
      ) : isOpen ? (
        <span className="absolute -top-1 -right-1 flex h-4 w-4 rounded-full bg-zinc-900 border-2 border-white items-center justify-center text-[8px] font-bold text-white">
          ×
        </span>
      ) : null}
    </button>
  )
}

export const CognitoPilotPanel = () => {
  const open = useCognitoPilotStore((state) => state.open)
  const openPanel = useCognitoPilotStore((state) => state.openPanel)
  const prompt = useCognitoPilotStore((state) => state.prompt)
  const promptVersion = useCognitoPilotStore((state) => state.promptVersion)
  const closePanel = useCognitoPilotStore((state) => state.closePanel)
  const location = useLocation()
  const navigate = useNavigate()
  const activeUserId = useSessionStore((state) => state.activeUserId)
  const user = DEMO_USERS.find((demoUser) => demoUser.id === activeUserId) ?? DEMO_USERS[0]
  const pages = useMetadataStore((state) => state.pages)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [undoTarget, setUndoTarget] = useState<UndoTarget | null>(null)
  const resetSignal = useCognitoPilotStore((state) => state.resetSignal)
  const [pageSuggestions, setPageSuggestions] = useState<string[]>([])
  const [undoError, setUndoError] = useState<string | null>(null)
  const [requestError, setRequestError] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string>(() => 'sess_' + Math.random().toString(36).substring(2, 10))
  const [finishedReveals, setFinishedReveals] = useState<Set<number>>(() => new Set())
  const [, setApplyingPlan] = useState<{ messageId: number; completedIndex: number } | null>(null)
  const nextMessageId = useRef(0)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const [speakerEnabled, setSpeakerEnabled] = useState<boolean>(() => {
    try {
      return localStorage.getItem('cognito_speaker_enabled') === 'true'
    } catch {
      return false
    }
  })
  const speakerEnabledRef = useRef(speakerEnabled)
  useEffect(() => {
    speakerEnabledRef.current = speakerEnabled
  }, [speakerEnabled])

  const [isSpeaking, setIsSpeaking] = useState(false)
  const isSpeakingRef = useRef(false)
  useEffect(() => {
    isSpeakingRef.current = isSpeaking
  }, [isSpeaking])

  const [isListening, setIsListening] = useState(false)
  const isListeningRef = useRef(false)
  useEffect(() => {
    isListeningRef.current = isListening
  }, [isListening])

  const [interimTranscript, setInterimTranscript] = useState('')
  const interimTranscriptRef = useRef('')
  const [speechError, setSpeechError] = useState<string | null>(null)
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)

  const hasSpeechRecognition = typeof window !== 'undefined' && Boolean(getSpeechRecognitionClass())

  const cancelSpeech = () => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel()
      } catch {
        // ignore
      }
    }
    setIsSpeaking(false)
    isSpeakingRef.current = false
  }

  const stopListening = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort()
      } catch {
        // ignore
      }
      recognitionRef.current = null
    }
    setIsListening(false)
    isListeningRef.current = false
    setInterimTranscript('')
    interimTranscriptRef.current = ''
  }

  const voicesRef = useRef<SpeechSynthesisVoice[]>([])
  useEffect(() => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
    const updateVoices = () => {
      const v = window.speechSynthesis.getVoices()
      if (v && v.length > 0) {
        voicesRef.current = v
        console.debug('[Voice] Voices loaded, count:', v.length)
      }
    }
    updateVoices()
    window.speechSynthesis.onvoiceschanged = updateVoices
  }, [])

  const toggleSpeaker = () => {
    setSpeakerEnabled((prev) => {
      const next = !prev
      console.debug('[Voice] Speaker toggled:', next)
      try {
        localStorage.setItem('cognito_speaker_enabled', String(next))
      } catch {
        // ignore
      }
      if (next) {
        if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
          try {
            console.debug('[Voice] Unlocking speech on toggle click with silent utterance')
            const unlock = new SpeechSynthesisUtterance(' ')
            unlock.volume = 0.01
            window.speechSynthesis.speak(unlock)
          } catch (e) {
            console.debug('[Voice] Silent unlock error:', e)
          }
        }
      } else {
        cancelSpeech()
      }
      return next
    })
  }

  const startListening = () => {
    const SpeechRecognitionClass = getSpeechRecognitionClass()
    if (!SpeechRecognitionClass) {
      console.debug('[Voice] No speech recognition class found')
      setSpeechError('Speech recognition is not supported in this browser.')
      return
    }

    console.debug('[Voice] Starting speech recognition...')
    cancelSpeech()
    setSpeechError(null)
    setInterimTranscript('')
    interimTranscriptRef.current = ''

    try {
      const recognition = new SpeechRecognitionClass()
      recognition.lang = 'en-IN'
      recognition.interimResults = true
      recognition.continuous = false

      recognition.onstart = () => {
        console.debug('[Voice] Mic onstart fired')
        setIsListening(true)
        isListeningRef.current = true
      }

      recognition.onresult = (event) => {
        let interim = ''
        let final = ''
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const res = event.results[i]
          if (res.isFinal) {
            final += res[0].transcript
          } else {
            interim += res[0].transcript
          }
        }
        if (interim) {
          console.debug('[Voice] Mic interim transcript:', interim)
          setInterimTranscript(interim)
          interimTranscriptRef.current = interim
        }
        if (final.trim()) {
          const finalText = final.trim()
          console.debug('[Voice] Mic final transcript received:', finalText)
          interimTranscriptRef.current = ''
          setInput(finalText)
          setInterimTranscript('')
          setIsListening(false)
          isListeningRef.current = false
          try {
            recognition.stop()
          } catch {
            // ignore
          }
          recognitionRef.current = null
          void submitMessage(finalText)
        }
      }

      recognition.onerror = (event) => {
        console.debug('[Voice] Mic onerror fired:', event.error)
        setIsListening(false)
        isListeningRef.current = false
        setInterimTranscript('')
        interimTranscriptRef.current = ''
        recognitionRef.current = null

        let msg = 'Microphone is not available. Please type instead.'
        if (event.error === 'not-allowed') {
          msg = 'Microphone permission was denied. Please allow microphone access or type.'
        } else if (event.error === 'no-speech') {
          msg = 'No speech was detected. Please try speaking again or type.'
        } else if (event.error === 'network') {
          msg = 'Speech recognition network error. Please type instead.'
        } else if (event.error === 'audio-capture') {
          msg = 'No microphone device found. Please type instead.'
        }
        setSpeechError(msg)
      }

      recognition.onend = () => {
        console.debug('[Voice] Mic onend fired')
        setIsListening(false)
        isListeningRef.current = false
        recognitionRef.current = null
        if (interimTranscriptRef.current.trim()) {
          const textToSend = interimTranscriptRef.current.trim()
          console.debug('[Voice] Mic sending trailing interim transcript on onend:', textToSend)
          interimTranscriptRef.current = ''
          setInput(textToSend)
          setInterimTranscript('')
          void submitMessage(textToSend)
        }
      }

      recognitionRef.current = recognition
      recognition.start()
    } catch (err) {
      console.debug('[Voice] Failed to start speech recognition:', err)
      setIsListening(false)
      isListeningRef.current = false
      setSpeechError('Microphone is not available. Please type instead.')
    }
  }

  const toggleListening = () => {
    console.debug('[Voice] Mic button clicked, currently listening:', isListening)
    if (isListening) {
      stopListening()
    } else {
      startListening()
    }
  }

  const speakAnswer = (msg: ChatMessage) => {
    console.debug('[Voice] speakAnswer called for message ID:', msg.id)
    if (isListeningRef.current) {
      console.debug('[Voice] Aborting speakAnswer because mic is active')
      return
    }
    const mainText = msg.result?.answer || msg.content || ''
    const isRefusal = msg.result?.outcome === 'refused'
    const cleaned = cleanSpokenText(mainText, isRefusal)
    console.debug('[Voice] Cleaned spoken text:', cleaned)
    if (!cleaned.trim()) {
      console.debug('[Voice] Cleaned text is empty, nothing to speak')
      return
    }

    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      console.debug('[Voice] window.speechSynthesis not supported')
      setSpeechError('Speech synthesis is not supported in this browser.')
      return
    }

    try {
      window.speechSynthesis.cancel()
      if (window.speechSynthesis.paused) {
        console.debug('[Voice] Resuming paused speech synthesis')
        window.speechSynthesis.resume()
      }
    } catch (e) {
      console.debug('[Voice] Cancel error:', e)
    }

    const doSpeak = () => {
      let voices = voicesRef.current
      if (!voices || voices.length === 0) {
        voices = window.speechSynthesis.getVoices()
        if (voices && voices.length > 0) voicesRef.current = voices
      }
      console.debug('[Voice] Available voices count:', voices.length)
      const voice = selectEnglishVoice(voices)
      console.debug('[Voice] Selected voice:', voice?.name, voice?.lang)

      const utterance = new SpeechSynthesisUtterance(cleaned)
      utterance.rate = 1.0

      if (voice) {
        utterance.voice = voice
        utterance.lang = voice.lang
      } else if (voices.length > 0) {
        utterance.voice = voices[0]
        utterance.lang = voices[0].lang || 'en-IN'
      } else {
        utterance.lang = 'en-IN'
      }

      utterance.onstart = () => {
        console.debug('[Voice] Speech utterance onstart')
        setIsSpeaking(true)
        isSpeakingRef.current = true
      }
      utterance.onend = () => {
        console.debug('[Voice] Speech utterance onend')
        setIsSpeaking(false)
        isSpeakingRef.current = false
      }
      utterance.onerror = (e) => {
        console.debug('[Voice] Speech utterance onerror:', e)
        setIsSpeaking(false)
        isSpeakingRef.current = false
        setSpeechError('Speech synthesis failed. Please check browser audio.')
      }

      try {
        console.debug('[Voice] Invoking window.speechSynthesis.speak')
        window.speechSynthesis.speak(utterance)
      } catch (err) {
        console.debug('[Voice] window.speechSynthesis.speak error:', err)
        setIsSpeaking(false)
        isSpeakingRef.current = false
        setSpeechError('Speech synthesis failed to start.')
      }
    }

    if (window.speechSynthesis.getVoices().length > 0) {
      voicesRef.current = window.speechSynthesis.getVoices()
      doSpeak()
    } else {
      console.debug('[Voice] getVoices() empty, waiting for voiceschanged...')
      let done = false
      const onVoices = () => {
        if (done) return
        done = true
        voicesRef.current = window.speechSynthesis.getVoices()
        console.debug('[Voice] voiceschanged fired with count:', voicesRef.current.length)
        doSpeak()
      }
      window.speechSynthesis.onvoiceschanged = onVoices
      setTimeout(() => {
        if (!done) {
          done = true
          voicesRef.current = window.speechSynthesis.getVoices()
          doSpeak()
        }
      }, 150)
    }
  }

  const handleRevealFinished = (msg: ChatMessage) => {
    setFinishedReveals((prev) => {
      if (prev.has(msg.id)) return prev
      const next = new Set(prev)
      next.add(msg.id)
      return next
    })

    if (speakerEnabledRef.current && msg.role === 'assistant') {
      speakAnswer(msg)
    }
  }

  useEffect(() => {
    if (!open) {
      cancelSpeech()
      stopListening()
    }
  }, [open])

  useEffect(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.getVoices()
      window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.getVoices()
      }
    }
    return () => {
      cancelSpeech()
      stopListening()
    }
  }, [])

  useEffect(() => {
    if (resetSignal > 0) {
      cancelSpeech()
      stopListening()
      setMessages([])
      setFinishedReveals(new Set())
      setUndoTarget(null)
      setRequestError(null)
      setUndoError(null)
      setSessionId('sess_' + Math.random().toString(36).substring(2, 10))
    }
  }, [resetSignal])

  useEffect(() => {
    const page = pages.find((item) => item.route === location.pathname)
    if (!page) {
      setPageSuggestions([])
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const res = await apiFetch(`/api/suggestions?page_id=${encodeURIComponent(page.id)}&role=${encodeURIComponent(user.role)}`)
        if (res.ok) {
          const data = await res.json()
          if (!cancelled && Array.isArray(data.suggestions)) {
            setPageSuggestions(data.suggestions)
          }
        }
      } catch {
        if (!cancelled) setPageSuggestions([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [location.pathname, pages, user.role])

  useEffect(() => {
    if (!open) return
    inputRef.current?.focus()
  }, [open])

  useEffect(() => {
    if (open && prompt && promptVersion > 0) {
      setInput(prompt)
      void submitMessage(prompt)
    }
  // Prompt versions represent explicit launch actions from other surfaces.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [promptVersion])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, loading])

  const appendMessage = (message: Omit<ChatMessage, 'id'>) => {
    const item = { ...message, id: nextMessageId.current++ }
    setMessages((current) => [...current, item])
  }

  const captureUndoTarget = (): UndoTarget => {
    const page = pages.find((item) => item.route === location.pathname)
    const state = page ? useUiStateStore.getState().pages[page.id] : undefined
    return {
      page_id: page?.id ?? null,
      path: location.pathname,
      filters: state?.filters ?? {},
      date_range: state?.dateRange ?? null,
      custom_start: state?.customStart ?? null,
      custom_end: state?.customEnd ?? null,
      sort: state?.sort ?? null,
      sort_direction: state?.sortDirection ?? 'asc',
      direction: state?.sortDirection ?? 'asc',
    }
  }

  const applySingleStep = (step: AgentPlanStep, activePageIdRef: { current: string | null }) => {
    const args = step.args
    if (step.tool === 'navigate') {
      const pageId = String(args.page_id ?? '')
      const page = pages.find((item) => item.id === pageId)
      if (!page) return
      activePageIdRef.current = page.id
      useUiStateStore.getState().initializePage(page)
      navigate(page.route)
    } else if (step.tool === 'set_filter') {
      const pageId = String(args.page_id ?? activePageIdRef.current ?? '')
      const field = String(args.field ?? '')
      if (!pageId || !field) return
      const value = args.value
      useUiStateStore.getState().applyUiState(pageId, { filters: { [field]: value as string | string[] | null } }, 'agent')
    } else if (step.tool === 'set_date_range') {
      const pageId = String(args.page_id ?? activePageIdRef.current ?? '')
      if (!pageId) return
      const period = String(args.period ?? 'custom')
      const patch = {
        dateRange: period,
        customStart: period === 'custom' ? String(args.start ?? '') : null,
        customEnd: period === 'custom' ? String(args.end ?? '') : null,
      }
      useUiStateStore.getState().applyUiState(pageId, patch, 'agent')
    } else if (step.tool === 'sort') {
      const pageId = String(args.page_id ?? activePageIdRef.current ?? '')
      if (!pageId) return
      const sortField = String(args.field ?? '')
      const sortDirection = String(args.direction ?? args.order ?? 'asc')
      useUiStateStore.getState().applyUiState(pageId, { sort: sortField, sortDirection }, 'agent')
    }
  }

  const applyPlan = (steps: AgentPlanStep[]) => {
    const activePageIdRef = { current: null as string | null }
    for (const step of steps) {
      applySingleStep(step, activePageIdRef)
    }
  }

  const runVerification = async (steps: AgentPlanStep[], currentSessionId?: string | null) => {
    if (!steps || steps.length === 0) return null

    await new Promise((resolve) => setTimeout(resolve, 80))

    const getActualState = () => {
      const curPath = window.location.pathname
      const page = pages.find((item) => item.route === curPath)
      const state = page ? useUiStateStore.getState().pages[page.id] : undefined
      return {
        page_id: page?.id ?? null,
        route: curPath,
        filters: state?.filters ?? {},
        date_range: state?.dateRange ?? null,
        sort: state?.sort ?? null,
      }
    }

    let expectedPageId: string | null = null
    let expectedRoute: string | null = null
    const expectedFilters: Record<string, unknown> = {}
    let expectedDateRange: string | null = null
    let expectedSort: string | null = null

    for (const step of steps) {
      const args = step.args
      if (step.tool === 'navigate') {
        const pid = String(args.page_id ?? '')
        const targetPage = pages.find((p) => p.id === pid)
        if (targetPage) {
          expectedPageId = targetPage.id
          expectedRoute = targetPage.route
        }
      } else if (step.tool === 'set_filter') {
        const field = String(args.field ?? '')
        if (field) {
          expectedFilters[field] = args.value
        }
      } else if (step.tool === 'set_date_range') {
        expectedDateRange = String(args.period ?? 'custom')
      } else if (step.tool === 'sort') {
        expectedSort = String(args.field ?? '')
      }
    }

    const expected: Record<string, unknown> = {}
    if (expectedPageId) expected.page_id = expectedPageId
    if (expectedRoute) expected.route = expectedRoute
    if (Object.keys(expectedFilters).length > 0) expected.filters = expectedFilters
    if (expectedDateRange) expected.date_range = expectedDateRange
    if (expectedSort) expected.sort = expectedSort

    let actual = getActualState()

    const hasMismatch = () => {
      if (expected.page_id && actual.page_id !== expected.page_id) return true
      if (expected.route && actual.route !== expected.route) return true
      if (expected.date_range && actual.date_range !== expected.date_range) return true
      if (expected.sort && actual.sort !== expected.sort) return true
      if (expected.filters && typeof expected.filters === 'object') {
        const actFilters = (actual.filters as Record<string, unknown>) || {}
        for (const [k, v] of Object.entries(expected.filters as Record<string, unknown>)) {
          const actVal = actFilters[k]
          if (Array.isArray(v) && Array.isArray(actVal)) {
            if (v.join(',') !== actVal.join(',')) return true
          } else if (Array.isArray(v) && !Array.isArray(actVal)) {
            if (v.length !== 1 || v[0] !== actVal) return true
          } else if (!Array.isArray(v) && Array.isArray(actVal)) {
            if (actVal.length !== 1 || actVal[0] !== v) return true
          } else if (v !== actVal) {
            return true
          }
        }
      }
      return false
    }

    if (hasMismatch()) {
      applyPlan(steps)
      await new Promise((resolve) => setTimeout(resolve, 80))
      actual = getActualState()
    }

    try {
      const res = await apiFetch('/api/agent/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: currentSessionId,
          expected,
          actual,
        }),
      })
      const data = await res.json()
      return (data.status as 'Verified' | 'Mismatch') || (hasMismatch() ? 'Mismatch' : 'Verified')
    } catch {
      return hasMismatch() ? 'Mismatch' : 'Verified'
    }
  }

  const handleApplyConfirmed = async (messageId: number, plan: AgentPlanStep[], before?: UndoTarget | null) => {
    if (before) setUndoTarget(before)
    const activePageIdRef = { current: null as string | null }
    for (let i = 0; i < plan.length; i++) {
      setApplyingPlan({ messageId, completedIndex: i - 1 })
      await new Promise((resolve) => setTimeout(resolve, 150))
      applySingleStep(plan[i], activePageIdRef)
      setApplyingPlan({ messageId, completedIndex: i })
    }
    await new Promise((resolve) => setTimeout(resolve, 120))
    setApplyingPlan(null)
    setMessages((curr) =>
      curr.map((m) => (m.id === messageId ? { ...m, confirmationStatus: 'applied' } : m))
    )
    const vStatus = await runVerification(plan, sessionId)
    setMessages((curr) =>
      curr.map((m) => (m.id === messageId ? { ...m, verificationStatus: vStatus } : m))
    )
  }

  const handleCancelConfirmed = (messageId: number) => {
    setMessages((curr) =>
      curr.map((m) => (m.id === messageId ? { ...m, confirmationStatus: 'cancelled' } : m))
    )
  }

  const openReceiptView = (receipt: AgentReceipt) => {
    const before = captureUndoTarget()
    setUndoTarget(before)

    const targetPage = pages.find((p) => p.id === receipt.page_id || p.route === receipt.route)
    if (targetPage) {
      useUiStateStore.getState().initializePage(targetPage)
      if (receipt.filters && Object.keys(receipt.filters).length > 0) {
        useUiStateStore.getState().applyUiState(targetPage.id, {
          filters: receipt.filters as Record<string, string | string[] | null>,
        }, 'agent')
      }
      if (receipt.date_range) {
        let targetDateRange: string | undefined = undefined
        const dr = receipt.date_range as any
        if (dr && typeof dr === 'object') {
          if (dr.start === '2026-07-01' && dr.end === '2026-09-30') {
            targetDateRange = 'this_quarter'
          } else if (dr.start === '2026-04-01' && dr.end === '2026-06-30') {
            targetDateRange = 'last_quarter'
          }
        } else if (typeof dr === 'string') {
          if (dr.includes('2026-07-01') && dr.includes('2026-09-30')) {
            targetDateRange = 'this_quarter'
          } else if (dr.includes('2026-04-01') && dr.includes('2026-06-30')) {
            targetDateRange = 'last_quarter'
          } else if (!dr.startsWith('{')) {
            targetDateRange = dr
          }
        }
        if (targetDateRange) {
          useUiStateStore.getState().applyUiState(targetPage.id, {
            dateRange: targetDateRange,
          }, 'agent')
        }
      }
      if (receipt.sort) {
        useUiStateStore.getState().applyUiState(targetPage.id, {
          sort: receipt.sort,
        }, 'agent')
      }
      navigate(targetPage.route)
    } else if (receipt.route) {
      navigate(receipt.route)
    }
  }

  async function submitMessage(message = input) {
    cancelSpeech()
    stopListening()
    const trimmed = message.trim()
    if (!trimmed || loading) return
    const before = captureUndoTarget()
    appendMessage({ role: 'user', content: trimmed })
    setInput('')
    setLoading(true)
    setRequestError(null)
    setUndoError(null)

    try {
      const page = pages.find((item) => item.route === location.pathname)
      const pageState = page ? useUiStateStore.getState().pages[page.id] : undefined
      const preset = pageState?.dateRange ?? page?.default_date_range ?? ''
      const uiContext = {
        page_id: page?.id ?? '',
        route: location.pathname,
        filters: pageState?.filters ?? {},
        date_range: {
          preset: preset,
          start: pageState?.customStart ?? '',
          end: pageState?.customEnd ?? '',
        },
        sort: pageState?.sort ?? null,
        sort_direction: pageState?.sortDirection ?? 'asc',
        direction: pageState?.sortDirection ?? 'asc',
        role: user.role,
      }

      const response = await apiFetch('/api/agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: trimmed, role: user.role, ui_context: uiContext, session_id: sessionId }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.detail ?? `Agent request failed (${response.status})`)
      }
      const result = await response.json() as AgentResponse
      if (result.session_id) setSessionId(result.session_id)
      
      const requiresConfirmation = Boolean(result.requires_confirmation)
      let vStatus: 'Verified' | 'Mismatch' | null = null

      if (!requiresConfirmation) {
        applyPlan(result.plan ?? [])
        if (result.plan?.length && !result.error && result.outcome !== 'refused' && result.outcome !== 'clarify') {
          setUndoTarget(before)
          vStatus = await runVerification(result.plan, result.session_id || sessionId)
        }
      }

      appendMessage({
        role: 'assistant',
        content: result.answer,
        result,
        confirmationStatus: requiresConfirmation ? 'pending' : undefined,
        verificationStatus: vStatus,
        undoBefore: before,
      })
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'The agent request failed.'
      setRequestError(detail)
      appendMessage({ role: 'assistant', content: 'I could not complete that request.' })
    } finally {
      setLoading(false)
    }
  }

  const undo = async () => {
    if (!undoTarget || loading) return
    setUndoError(null)
    try {
      const response = await apiFetch('/api/undo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: user.role, state: undoTarget }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body?.detail ?? `Undo failed (${response.status})`)
      const restored = body.restored as UndoTarget
      if (restored.page_id) {
        const page = pages.find((item) => item.id === restored.page_id)
        if (!page) throw new Error('The previous page is no longer available for this role.')
        useUiStateStore.getState().initializePage(page)
        const sortDirection = restored.sort_direction || restored.direction || 'asc'
        useUiStateStore.getState().applyUiState(page.id, {
          filters: restored.filters as Record<string, string | string[] | null>,
          dateRange: restored.date_range,
          customStart: restored.custom_start ?? null,
          customEnd: restored.custom_end ?? null,
          sort: restored.sort,
          sortDirection,
        }, 'user')
      }
      navigate(restored.path || '/')
      setUndoTarget(null)
    } catch (error) {
      setUndoError(error instanceof Error ? error.message : 'Undo failed.')
    }
  }

  const handleNewChat = () => {
    cancelSpeech()
    stopListening()
    setMessages([])
    setFinishedReveals(new Set())
    setApplyingPlan(null)
    setUndoTarget(null)
    setRequestError(null)
    setUndoError(null)
    setSessionId('sess_' + Math.random().toString(36).substring(2, 10))
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    void submitMessage()
  }

  return (
    <>
      <RobotMascotButton
        isOpen={open}
        isLoading={loading}
        isSpeaking={isSpeaking}
        onClick={open ? closePanel : () => openPanel()}
      />
      {open && (
        <aside
          aria-label="Cognito Pilot chat"
          className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[440px] flex-col border-l border-[var(--border)] bg-[var(--color-card)] shadow-2xl"
        >
          <header className="flex h-16 shrink-0 items-center justify-between border-b border-[var(--border)] px-5">
            <div className="flex items-center gap-3">
              <RobotMascot size={34} isLoading={loading} isSpeaking={isSpeaking} />
              <div>
                <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Cognito Pilot</h2>
                <p className="text-[10px] text-[var(--color-text-muted)]">Metadata-grounded assistant</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {isSpeaking && (
                <button
                  type="button"
                  onClick={cancelSpeech}
                  aria-label="Stop reading aloud"
                  title="Stop reading aloud"
                  className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-rose-500/40 bg-rose-500/15 px-2.5 text-xs font-medium text-rose-300 hover:bg-rose-500/25 transition-colors cursor-pointer"
                >
                  <Square className="h-3 w-3 fill-current" /> Stop
                </button>
              )}
              <button
                type="button"
                onClick={toggleSpeaker}
                aria-label={speakerEnabled ? 'Read answers aloud (On)' : 'Read answers aloud (Off)'}
                title={speakerEnabled ? 'Read answers aloud (On)' : 'Read answers aloud (Off)'}
                aria-pressed={speakerEnabled}
                className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition-colors cursor-pointer ${
                  speakerEnabled
                    ? 'bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-500/40 shadow-xs'
                    : 'bg-[var(--color-card-raised)] text-[var(--color-text-secondary)] border-[var(--border)] hover:text-[var(--color-text-primary)]'
                }`}
              >
                {speakerEnabled ? <Volume2 className="h-4 w-4 text-fuchsia-400" /> : <VolumeX className="h-4 w-4" />}
              </button>
              <button
                type="button"
                onClick={handleNewChat}
                disabled={loading}
                className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)] px-2.5 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] disabled:cursor-not-allowed disabled:opacity-40"
                title="Start new conversation"
              >
                <Sparkles className="h-3.5 w-3.5 text-fuchsia-400" /> New chat
              </button>
              <button
                type="button"
                onClick={() => void undo()}
                disabled={!undoTarget || loading}
                className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)] px-2.5 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <RotateCcw className="h-3.5 w-3.5" /> Undo
              </button>
              <button
                type="button"
                aria-label="Close Cognito Pilot"
                onClick={closePanel}
                className="rounded-lg p-2 text-[var(--color-text-secondary)] hover:bg-white/[0.06] hover:text-[var(--color-text-primary)]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </header>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="mt-8 rounded-2xl border border-[var(--border)] bg-[var(--color-card-raised)] p-5 text-center space-y-3">
            <Bot className="mx-auto mb-2 h-7 w-7 text-fuchsia-300" />
            <p className="text-sm font-medium text-[var(--color-text-primary)]">What would you like to explore?</p>
            <p className="text-xs text-[var(--color-text-secondary)]">Try one of these suggestions or ask a question:</p>
            {pageSuggestions.length > 0 && (
              <div className="flex flex-col gap-2 pt-2 text-left">
                {pageSuggestions.map((chip, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => void submitMessage(chip)}
                    className="w-full text-left rounded-xl border border-[var(--border)] bg-black/10 hover:bg-fuchsia-500/10 hover:border-fuchsia-400/40 px-3 py-2 text-xs text-[var(--color-text-primary)] transition-all cursor-pointer flex items-center gap-2 group"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-fuchsia-400 shrink-0 group-hover:scale-110 transition-transform" />
                    <span>{chip}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((message) => {
          const isRefused = message.result?.outcome === 'refused'
          const isClarify = message.result?.outcome === 'clarify'
          const rawSuggestions = message.result?.suggestions?.length
            ? message.result.suggestions
            : message.result?.error?.suggestions?.length
            ? message.result.error.suggestions
            : []

          return (
            <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`w-full max-w-[95%] space-y-3 ${
                  message.role === 'user'
                    ? 'rounded-2xl rounded-br-md bg-fuchsia-500/15 p-3 text-[var(--color-text-primary)]'
                    : isRefused
                    ? 'rounded-2xl border border-amber-500/25 bg-amber-500/10 p-3 text-[var(--color-text-primary)]'
                    : isClarify
                    ? 'rounded-2xl border border-sky-500/25 bg-sky-500/10 p-3 text-[var(--color-text-primary)]'
                    : 'text-[var(--color-text-primary)]'
                }`}
              >
                {isRefused && (
                  <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-amber-400">
                    <span>Request refused {message.result?.refusal_reason ? `· ${message.result.refusal_reason.replace(/_/g, ' ')}` : ''}</span>
                  </div>
                )}
                {isClarify && (
                  <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-sky-400">
                    <span>Clarification needed</span>
                  </div>
                )}

                <div className="flex items-start gap-2">
                  {message.role === 'assistant' && (
                    <Bot
                      className={`mt-0.5 h-4 w-4 shrink-0 ${
                        isRefused ? 'text-amber-400' : isClarify ? 'text-sky-400' : 'text-fuchsia-300'
                      }`}
                    />
                  )}
                  {message.role === 'assistant' ? (
                    <StreamingAnswerText
                      fullText={message.content || message.result?.clarify || ''}
                      isFinished={finishedReveals.has(message.id)}
                      onFinish={() => handleRevealFinished(message)}
                    />
                  ) : (
                    <div className="flex-1 text-sm leading-relaxed">
                      {formatMessageText(message.content)}
                    </div>
                  )}
                </div>

                {/* Suggestions rendered as small clickable chips */}
                {!!rawSuggestions.length && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {rawSuggestions.map((item, idx) => {
                      const label = typeof item === 'string' ? item : item.title || item.id
                      return (
                        <button
                          type="button"
                          key={idx}
                          onClick={() => void submitMessage(label)}
                          className="inline-flex items-center rounded-lg border border-[var(--border)] bg-[var(--color-card-raised)] px-2.5 py-1 text-xs text-[var(--color-text-secondary)] hover:border-fuchsia-400/40 hover:bg-fuchsia-500/10 hover:text-[var(--color-text-primary)] transition-colors"
                        >
                          {label}
                        </button>
                      )
                    })}
                  </div>
                )}

                {message.result?.plan?.length ? (
                  <section className="rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)] p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <h3 className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">Plan</h3>
                      {message.verificationStatus && (
                        <span
                          className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${
                            message.verificationStatus === 'Verified'
                              ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                              : 'bg-rose-500/15 text-rose-300 border border-rose-500/30'
                          }`}
                        >
                          {message.verificationStatus === 'Verified' ? (
                            <>
                              <Check className="h-3 w-3 text-emerald-300" /> Verified
                            </>
                          ) : (
                            <>
                              <AlertTriangle className="h-3 w-3 text-rose-300" /> State Mismatch
                            </>
                          )}
                        </span>
                      )}
                    </div>
                    <ol className="space-y-1.5">
                      {message.result.plan.map((step, index) => (
                        <li key={`${message.id}-${index}`} className="flex items-center gap-2 text-xs">
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-fuchsia-500/15 text-[10px] text-fuchsia-200">{index + 1}</span>
                          <span className="font-medium text-[var(--color-text-primary)]">{planLabel[step.tool] ?? step.tool}</span>
                          <span className="truncate text-[var(--color-text-muted)]">{prettyArgs(step)}</span>
                        </li>
                      ))}
                    </ol>
                  </section>
                ) : null}

                {/* Confirmation prompt */}
                {message.confirmationStatus === 'pending' && (
                  <section className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-300">
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                      Confirmation Required
                    </div>
                    <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
                      {message.result?.confirmation_reason || 'This plan modifies active filters or has multiple steps. Do you want to proceed?'}
                    </p>
                    <div className="mt-2.5 flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void handleApplyConfirmed(message.id, message.result?.plan ?? [], message.undoBefore)}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-fuchsia-600 to-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 shadow-sm transition-opacity"
                      >
                        <Check className="h-3.5 w-3.5" /> Apply
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCancelConfirmed(message.id)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--color-card-raised)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
                      >
                        <X className="h-3.5 w-3.5" /> Cancel
                      </button>
                    </div>
                  </section>
                )}
                {message.confirmationStatus === 'applied' && (
                  <div className="flex items-center gap-1 text-[11px] font-medium text-emerald-400">
                    <Check className="h-3 w-3" /> Changes applied
                  </div>
                )}
                {message.confirmationStatus === 'cancelled' && (
                  <div className="flex items-center gap-1 text-[11px] font-medium text-zinc-400">
                    <X className="h-3 w-3" /> Changes cancelled (nothing applied)
                  </div>
                )}

                {message.result?.analysis && (
                  <AnalysisCard analysis={message.result.analysis} faithfulness={message.result.faithfulness} />
                )}

                {message.result?.evidence ? (
                  <section className="rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)] p-3">
                    <h3 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]"><Check className="h-3 w-3 text-emerald-300" /> Evidence</h3>
                    {message.result.evidence.page?.title && (
                      <p className="mb-1.5 text-xs"><span className="text-[var(--color-text-muted)]">Page</span> · {message.result.evidence.page.title}</p>
                    )}
                    <div className="space-y-1">
                      {buildEvidenceLines(message.result.evidence).map((line, lIdx) => (
                        <div key={lIdx} className="flex items-center gap-1.5 text-xs text-[var(--color-text-primary)]">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shrink-0" />
                          <span className="font-medium">{line}</span>
                        </div>
                      ))}
                    </div>
                    {message.result.evidence.query && (
                      <details className="mt-2.5">
                        <summary className="cursor-pointer text-[10px] text-[var(--color-text-secondary)]">Query used</summary>
                        <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap break-all rounded-lg border border-[var(--border)] bg-black/20 p-2 text-[9px] text-[var(--color-text-muted)]">{message.result.evidence.query}</pre>
                      </details>
                    )}
                  </section>
                ) : null}

                {message.result?.chart?.rows?.length ? (
                  <section className="rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)] p-3">
                    <h3 className="mb-2 text-xs font-semibold text-[var(--color-text-primary)]">{message.result.chart.title}</h3>
                    <div className="h-40 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        {message.result.chart.chart_type === 'line' ? (
                          <LineChart data={message.result.chart.rows}>
                            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                            <XAxis dataKey="period" tick={{ fill: '#9CA3AF', fontSize: 10 }} />
                            <YAxis tick={{ fill: '#9CA3AF', fontSize: 10 }} />
                            <Tooltip />
                            <Line type="monotone" dataKey="value" stroke={chartColors[0]} strokeWidth={2} />
                          </LineChart>
                        ) : message.result.chart.chart_type === 'pie' ? (
                          <PieChart>
                            <Pie data={message.result.chart.rows} dataKey="value" nameKey="label" outerRadius={56}>
                              {message.result.chart.rows.map((row, index) => <Cell key={`${String(row.label)}-${index}`} fill={chartColors[index % chartColors.length]} />)}
                            </Pie>
                            <Tooltip />
                          </PieChart>
                        ) : (
                          <BarChart data={message.result.chart.rows}>
                            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                            <XAxis dataKey="label" tick={{ fill: '#9CA3AF', fontSize: 10 }} />
                            <YAxis tick={{ fill: '#9CA3AF', fontSize: 10 }} />
                            <Tooltip />
                            <Bar dataKey="value" fill={chartColors[0]} radius={[5, 5, 0, 0]} />
                          </BarChart>
                        )}
                      </ResponsiveContainer>
                    </div>
                  </section>
                ) : null}

                {/* Sources & Receipts Section */}
                {message.result?.receipts && message.result.receipts.length > 0 && (() => {
                  const grouped = groupReceipts(message.result.receipts)
                  return (
                    <details className="rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)] p-2.5">
                      <summary className="cursor-pointer text-xs font-semibold text-[var(--color-text-primary)] hover:text-fuchsia-300 transition-colors flex items-center justify-between">
                        <span className="flex items-center gap-1.5">
                          <Receipt className="h-3.5 w-3.5 text-fuchsia-400" />
                          Sources ({grouped.length})
                        </span>
                        <span className="text-[10px] text-[var(--color-text-muted)] font-normal">Click to expand</span>
                      </summary>
                      <div className="mt-2.5 space-y-2 border-t border-[var(--border)] pt-2">
                        {grouped.map((group, idx) => (
                          <div key={idx} className="flex items-center justify-between gap-3 rounded-lg bg-black/20 p-2 text-xs">
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                <span className="font-semibold text-[var(--color-text-primary)]">{group.item}:</span>
                                {group.facts.map((fact, fIdx) => (
                                  <span key={fIdx} className="inline-flex items-center gap-1 text-[11px]">
                                    <span className="text-[var(--color-text-muted)]">{fact.label}:</span>
                                    <span className="font-mono font-medium text-fuchsia-300">{fact.value}</span>
                                    {fIdx < group.facts.length - 1 && <span className="text-zinc-600">·</span>}
                                  </span>
                                ))}
                              </div>
                              {group.pageInfo && (
                                <p className="mt-0.5 text-[10px] text-[var(--color-text-muted)] truncate">
                                  Page: {group.pageInfo}
                                </p>
                              )}
                            </div>
                            {(group.representativeReceipt.route || group.representativeReceipt.page_id) && (
                              <button
                                type="button"
                                onClick={() => openReceiptView(group.representativeReceipt)}
                                className="shrink-0 rounded-lg border border-fuchsia-500/30 bg-fuchsia-500/10 px-2 py-1 text-[11px] font-medium text-fuchsia-300 hover:bg-fuchsia-500/20 transition-colors cursor-pointer"
                              >
                                Open view
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    </details>
                  )
                })()}

                {/* Unverified Numbers Warning */}
                {message.result?.faithfulness?.unverified && message.result.faithfulness.unverified.length > 0 && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-2.5 text-xs text-amber-200">
                    <div className="flex items-center gap-1.5 font-semibold text-amber-300">
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                      Unverified figures detected
                    </div>
                    <p className="mt-1 text-[11px] text-amber-200/90">
                      {message.result.faithfulness.unverified.map((u: any) => typeof u === 'object' ? (u.value || JSON.stringify(u)) : String(u)).join(', ')}
                    </p>
                    <p className="mt-0.5 text-[10px] text-amber-300/70">
                      These figures in the answer could not be verified against executed query results.
                    </p>
                  </div>
                )}

                {/* Proactive suggestions chips after assistant answer */}
                {message.role === 'assistant' && pageSuggestions.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-2 border-t border-white/[0.06]">
                    {pageSuggestions.map((chip, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => void submitMessage(chip)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-fuchsia-500/20 bg-fuchsia-500/5 px-2.5 py-1 text-xs text-fuchsia-200 hover:border-fuchsia-400/40 hover:bg-fuchsia-500/15 transition-all cursor-pointer"
                      >
                        <Sparkles className="w-3 h-3 text-fuchsia-400 shrink-0" />
                        <span>{chip}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {loading && (
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
            <LoaderCircle className="h-4 w-4 animate-spin text-fuchsia-300" />
            Cognito Pilot is checking the data…
          </div>
        )}
        {requestError && <p role="alert" className="rounded-lg border border-rose-400/25 bg-rose-400/10 p-2 text-xs text-rose-200">{requestError}</p>}
        {undoError && <p role="alert" className="rounded-lg border border-amber-400/25 bg-amber-400/10 p-2 text-xs text-amber-100">{undoError}</p>}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={onSubmit} className="shrink-0 border-t border-[var(--border)] p-4">
        <label htmlFor="cognito-pilot-input" className="sr-only">Message Cognito Pilot</label>
        <div className="flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--color-card-raised)] p-1.5 focus-within:ring-2 focus-within:ring-fuchsia-500/40">
          <input
            id="cognito-pilot-input"
            ref={inputRef}
            value={isListening ? (interimTranscript || '') : input}
            onChange={(event) => {
              setInput(event.target.value)
              if (speechError) setSpeechError(null)
            }}
            disabled={loading || isListening}
            placeholder={isListening ? 'Listening…' : 'Ask about your data…'}
            className={`min-w-0 flex-1 bg-transparent px-2 py-2 text-sm outline-none placeholder:text-[var(--color-text-muted)] disabled:opacity-60 ${
              isListening
                ? 'text-[var(--color-text-muted)] italic'
                : 'text-[var(--color-text-primary)]'
            }`}
          />
          {hasSpeechRecognition && (
            <button
              type="button"
              onClick={toggleListening}
              disabled={loading}
              aria-label="Speak your question"
              title="Speak your question"
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-all cursor-pointer ${
                isListening
                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/50 animate-pulse'
                  : 'text-[var(--color-text-secondary)] hover:bg-white/[0.06] hover:text-[var(--color-text-primary)]'
              }`}
            >
              {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            </button>
          )}
          <button
            type="submit"
            disabled={!input.trim() || loading || isListening}
            aria-label="Send message"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-r from-[#D946EF] to-[#8B5CF6] text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>
        {speechError && (
          <p role="alert" className="mt-1.5 text-center text-xs text-rose-400">
            {speechError}
          </p>
        )}
        <p className="mt-2 text-center text-[9px] text-[var(--color-text-muted)]">Only metadata-validated pages and filters are applied.</p>
      </form>
    </aside>
  )}
</>
  )
}
