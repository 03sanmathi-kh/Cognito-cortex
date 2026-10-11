import { useEffect, useState } from 'react'
import { GlowCard } from './GlowCard'
import { TrendChip, type TrendChipProps } from './TrendChip'
import { cn } from '@/lib/utils'

export interface KpiCardProps {
  label: string
  value: number | string
  prefix?: string
  suffix?: string
  trend?: {
    value: number | string
    isPositive?: boolean
    variant?: TrendChipProps['variant']
  }
  caption?: string
  icon?: React.ReactNode
  iconColor?: 'magenta' | 'purple' | 'green' | 'blue' | 'amber'
  className?: string
  glow?: boolean
}

export const KpiCard: React.FC<KpiCardProps> = ({
  label,
  value,
  prefix = '',
  suffix = '',
  trend,
  caption,
  icon,
  iconColor = 'purple',
  className,
  glow = true,
}) => {
  // Count-up animation for numeric values
  const [displayValue, setDisplayValue] = useState<number | string>(() => {
    return typeof value === 'number' ? 0 : value
  })

  useEffect(() => {
    if (typeof value !== 'number') {
      setDisplayValue(value)
      return
    }

    const duration = 900 // ms
    const start = 0
    const end = value
    const startTime = performance.now()

    let animationFrameId: number

    const updateCounter = (currentTime: number) => {
      const elapsed = currentTime - startTime
      const progress = Math.min(elapsed / duration, 1)
      // Ease out cubic
      const easeOut = 1 - Math.pow(1 - progress, 3)
      const current = Math.floor(start + (end - start) * easeOut)

      setDisplayValue(current)

      if (progress < 1) {
        animationFrameId = requestAnimationFrame(updateCounter)
      } else {
        setDisplayValue(end)
      }
    }

    animationFrameId = requestAnimationFrame(updateCounter)

    return () => cancelAnimationFrame(animationFrameId)
  }, [value])

  const iconStyles = {
    magenta: "bg-fuchsia-500/15 text-[#D946EF] border-fuchsia-500/30",
    purple: "bg-purple-500/15 text-[#A855F7] border-purple-500/30",
    green: "bg-emerald-500/15 text-[#22C55E] border-emerald-500/30",
    blue: "bg-blue-500/15 text-[#38BDF8] border-blue-500/30",
    amber: "bg-amber-500/15 text-[#F59E0B] border-amber-500/30",
  }[iconColor]

  const formattedValue = typeof displayValue === 'number' 
    ? displayValue.toLocaleString() 
    : displayValue

  return (
    <GlowCard glow={glow} className={cn("p-5 flex flex-col justify-between min-h-[140px]", className)}>
      {/* Top Header: Label & Tinted Icon */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <span className="text-sm font-normal text-[var(--color-text-secondary)] tracking-tight">
          {label}
        </span>
        {icon && (
          <div className={cn("w-9 h-9 rounded-xl flex items-center justify-center border shrink-0 transition-transform duration-200 group-hover:scale-105", iconStyles)}>
            {icon}
          </div>
        )}
      </div>

      {/* Middle Row: Large Value + TrendChip */}
      <div className="flex items-baseline gap-2.5 flex-wrap">
        <h3 className="text-2xl md:text-3xl font-bold tracking-tight text-[var(--color-text-primary)] tabular-nums font-sans">
          {prefix}{formattedValue}{suffix}
        </h3>
        {trend && (
          <TrendChip
            value={trend.value}
            isPositive={trend.isPositive}
            variant={trend.variant}
          />
        )}
      </div>

      {/* Bottom Row: Caption */}
      {caption && (
        <p className="mt-2 text-xs text-[var(--color-text-muted)] font-normal tracking-tight">
          {caption}
        </p>
      )}
    </GlowCard>
  )
}
