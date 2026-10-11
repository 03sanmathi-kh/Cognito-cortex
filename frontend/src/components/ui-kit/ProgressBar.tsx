import React from 'react'
import { cn } from '@/lib/utils'

export interface ProgressBarProps extends React.HTMLAttributes<HTMLDivElement> {
  value: number
  label?: string
  showPercentage?: boolean
  variant?: 'magenta' | 'purple' | 'green' | 'blue' | 'gradient'
  size?: 'sm' | 'md' | 'lg'
  segmented?: boolean
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  value,
  label,
  showPercentage = true,
  variant = 'gradient',
  size = 'md',
  segmented = false,
  className,
  ...props
}) => {
  const clampedValue = Math.min(Math.max(value, 0), 100)

  const variantGradients = {
    gradient: "bg-gradient-to-r from-[#D946EF] via-[#A855F7] to-[#8B5CF6]",
    purple: "bg-gradient-to-r from-[#8B5CF6] to-[#A855F7]",
    magenta: "bg-gradient-to-r from-[#D946EF] to-[#F43F5E]",
    green: "bg-gradient-to-r from-[#22C55E] to-[#10B981]",
    blue: "bg-gradient-to-r from-[#38BDF8] to-[#6366F1]",
  }[variant]

  const textColors = {
    gradient: "text-[#D946EF]",
    purple: "text-[#8B5CF6]",
    magenta: "text-[#D946EF]",
    green: "text-[#22C55E]",
    blue: "text-[#38BDF8]",
  }[variant]

  const heightClasses = {
    sm: "h-1.5",
    md: "h-2",
    lg: "h-3",
  }[size]

  return (
    <div className={cn("w-full space-y-1.5", className)} {...props}>
      {(label || showPercentage) && (
        <div className="flex items-center justify-between text-xs font-medium">
          {label && (
            <span className="text-[var(--color-text-secondary)] tracking-tight">
              {label}
            </span>
          )}
          {showPercentage && (
            <span className={cn("tabular-nums font-semibold tracking-tight", textColors)}>
              {Math.round(clampedValue)}%
            </span>
          )}
        </div>
      )}

      {segmented ? (
        // Segmented look (3 blocks) as featured in the reference screenshot
        <div className="grid grid-cols-3 gap-1.5 w-full">
          {[0, 1, 2].map((idx) => {
            const segmentCapacity = 100 / 3
            const segmentFill = Math.min(Math.max((clampedValue - idx * segmentCapacity) / segmentCapacity, 0), 1) * 100

            return (
              <div 
                key={idx} 
                className={cn("w-full rounded-full bg-white/[0.06] overflow-hidden border border-white/[0.04]", heightClasses)}
              >
                <div
                  className={cn("h-full transition-all duration-500 ease-out", variantGradients)}
                  style={{ width: `${segmentFill}%` }}
                />
              </div>
            )
          })}
        </div>
      ) : (
        // Smooth continuous bar
        <div className={cn("w-full rounded-full bg-white/[0.08] overflow-hidden border border-white/[0.05]", heightClasses)}>
          <div
            className={cn("h-full rounded-full transition-all duration-500 ease-out shadow-sm", variantGradients)}
            style={{ width: `${clampedValue}%` }}
          />
        </div>
      )}
    </div>
  )
}
