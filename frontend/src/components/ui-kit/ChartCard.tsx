import React from 'react'
import { Filter } from 'lucide-react'
import { GlowCard } from './GlowCard'
import { CardMenu, type CardMenuItem } from './CardMenu'
import { cn } from '@/lib/utils'

export interface LegendItem {
  label: string
  color: string
}

export interface ChartCardProps {
  title: string
  subtitle?: string
  filterLabel?: string
  onFilterClick?: () => void
  menuItems?: CardMenuItem[]
  legends?: LegendItem[]
  children?: React.ReactNode
  className?: string
  glow?: boolean
}

export const ChartCard: React.FC<ChartCardProps> = ({
  title,
  subtitle,
  filterLabel = "Filter",
  onFilterClick,
  menuItems,
  legends,
  children,
  className,
  glow = true,
}) => {
  return (
    <GlowCard glow={glow} className={cn("p-6 flex flex-col justify-between space-y-4", className)}>
      {/* Header Row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-base md:text-lg font-bold tracking-tight text-[var(--color-text-primary)]">
            {title}
          </h3>
          {subtitle && (
            <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
              {subtitle}
            </p>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 self-start sm:self-center">
          <button
            type="button"
            onClick={onFilterClick}
            className={cn(
              "px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5",
              "bg-[var(--color-card-raised)] border border-[var(--border)] text-[var(--color-text-secondary)]",
              "hover:text-[var(--color-text-primary)] hover:border-white/[0.15] transition-all cursor-pointer"
            )}
          >
            <Filter className="w-3.5 h-3.5" />
            <span>{filterLabel}</span>
          </button>

          <CardMenu items={menuItems} />
        </div>
      </div>

      {/* Legend Row */}
      {legends && legends.length > 0 && (
        <div className="flex items-center gap-4 flex-wrap text-xs pt-1 border-b border-[var(--border)]/50 pb-2">
          {legends.map((legend, idx) => (
            <div key={idx} className="flex items-center gap-1.5">
              <span
                className="w-2 h-2 rounded-full shrink-0 shadow-[0_0_6px_currentColor]"
                style={{ backgroundColor: legend.color, color: legend.color }}
              />
              <span className="text-[var(--color-text-secondary)] text-[11px] font-medium">
                {legend.label}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Chart Slot */}
      <div className="w-full flex-1 min-h-[220px]">
        {children}
      </div>
    </GlowCard>
  )
}
