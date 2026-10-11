import React from 'react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'
import { cn } from '@/lib/utils'

export interface ChartSeries {
  key: string
  name: string
  color: string
}

export interface GlowAreaChartProps {
  data: Record<string, unknown>[]
  series: ChartSeries[]
  xAxisKey?: string
  height?: number
  className?: string
  showGrid?: boolean
  showXAxis?: boolean
  showYAxis?: boolean
}

interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{
    name: string
    value: number | string
    color: string
    dataKey: string
  }>
  label?: string
}

const CustomTooltip: React.FC<CustomTooltipProps> = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-xl bg-[var(--color-card)]/95 border border-[var(--border)] backdrop-blur-md p-3 shadow-2xl space-y-2 min-w-[130px]">
        {label && (
          <p className="text-[11px] font-semibold text-[var(--color-text-secondary)] border-b border-[var(--border)] pb-1">
            {label}
          </p>
        )}
        <div className="space-y-1.5 pt-0.5">
          {payload.map((item, idx) => (
            <div key={idx} className="flex items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-1.5">
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0 shadow-[0_0_8px_currentColor]"
                  style={{ backgroundColor: item.color, color: item.color }}
                />
                <span className="text-[var(--color-text-secondary)] text-[11px] font-medium">
                  {item.name}
                </span>
              </div>
              <span className="font-semibold text-[var(--color-text-primary)] tabular-nums text-xs font-mono">
                {typeof item.value === 'number' ? item.value.toLocaleString() : item.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    )
  }
  return null
}

export const GlowAreaChart: React.FC<GlowAreaChartProps> = ({
  data,
  series,
  xAxisKey = 'name',
  height = 240,
  className,
  showGrid = true,
  showXAxis = true,
  showYAxis = true,
}) => {
  return (
    <div className={cn("w-full h-full relative", className)} style={{ minHeight: height }}>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <defs>
            {/* SVG Filter for Glowing Lines (Rich atmospheric glow in dark mode) */}
            <filter id="line-glow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="4" result="blur1" />
              <feGaussianBlur stdDeviation="1.5" result="blur2" />
              <feMerge>
                <feMergeNode in="blur1" />
                <feMergeNode in="blur2" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Dynamic Gradients for each series */}
            {series.map((s) => (
              <linearGradient
                key={s.key}
                id={`gradient-${s.key}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="5%" stopColor={s.color} stopOpacity={0.28} />
                <stop offset="95%" stopColor={s.color} stopOpacity={0.0} />
              </linearGradient>
            ))}
          </defs>

          {showGrid && (
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--border)"
              vertical={false}
              opacity={0.6}
            />
          )}

          {showXAxis && (
            <XAxis
              dataKey={xAxisKey}
              stroke="var(--color-text-muted)"
              fontSize={11}
              tickLine={false}
              axisLine={{ stroke: 'var(--border)' }}
              dy={6}
            />
          )}

          {showYAxis && (
            <YAxis
              stroke="var(--color-text-muted)"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              dx={-4}
            />
          )}

          <Tooltip
            content={<CustomTooltip />}
            cursor={{
              stroke: 'var(--color-accent-purple)',
              strokeWidth: 1,
              strokeDasharray: '3 3',
              strokeOpacity: 0.5,
            }}
          />

          {series.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.name}
              stroke={s.color}
              strokeWidth={2.75}
              fillOpacity={1}
              fill={`url(#gradient-${s.key})`}
              filter="url(#line-glow)"
              activeDot={{
                r: 5,
                fill: s.color,
                stroke: '#FFFFFF',
                strokeWidth: 2,
                className: "shadow-[0_0_12px_currentColor]",
              }}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
