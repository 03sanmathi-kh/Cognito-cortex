import React from 'react'
import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface TrendChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  value: number | string
  isPositive?: boolean
  variant?: 'auto' | 'green' | 'red' | 'purple' | 'neutral'
  showIcon?: boolean
}

export const TrendChip: React.FC<TrendChipProps> = ({
  value,
  isPositive,
  variant = 'auto',
  showIcon = true,
  className,
  ...props
}) => {
  // Determine sign if value is a number or parseable string
  const num = typeof value === 'number' ? value : parseFloat(String(value).replace(/[^0-9.-]/g, ''))
  const positive = isPositive !== undefined ? isPositive : !isNaN(num) ? num >= 0 : true
  const isZero = !isNaN(num) && num === 0

  let colorClasses = ""

  if (variant === 'purple') {
    colorClasses = "bg-fuchsia-500/15 text-[#D946EF] border border-fuchsia-500/25"
  } else if (variant === 'green' || (variant === 'auto' && positive && !isZero)) {
    colorClasses = "bg-emerald-500/15 text-[#22C55E] border border-emerald-500/25"
  } else if (variant === 'red' || (variant === 'auto' && !positive)) {
    colorClasses = "bg-rose-500/15 text-[#F43F5E] border border-rose-500/25"
  } else {
    colorClasses = "bg-white/[0.08] text-[var(--color-text-secondary)] border border-white/[0.1]"
  }

  // Format string display
  const displayValue = typeof value === 'number' 
    ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%` 
    : String(value)

  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-xs font-semibold tracking-tight tabular-nums",
        colorClasses,
        className
      )}
      {...props}
    >
      {showIcon && (
        isZero ? (
          <Minus className="w-3 h-3 shrink-0" />
        ) : positive ? (
          <ArrowUpRight className="w-3 h-3 shrink-0 stroke-[2.5]" />
        ) : (
          <ArrowDownRight className="w-3 h-3 shrink-0 stroke-[2.5]" />
        )
      )}
      <span>{displayValue}</span>
    </span>
  )
}
