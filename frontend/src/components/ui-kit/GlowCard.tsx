import React from 'react'
import { cn } from '@/lib/utils'

export interface GlowCardProps extends React.HTMLAttributes<HTMLDivElement> {
  glow?: boolean
  hoverable?: boolean
  children?: React.ReactNode
}

export const GlowCard = React.forwardRef<HTMLDivElement, GlowCardProps>(
  ({ className, glow = false, hoverable = true, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "relative rounded-2xl bg-[var(--color-card)] text-[var(--color-text-primary)]",
          "border border-[var(--border)] overflow-hidden shadow-sm",
          // 1px top-edge luminous highlight
          "before:absolute before:inset-x-0 before:top-0 before:h-[1px] before:bg-gradient-to-r before:from-transparent before:via-white/[0.18] before:to-transparent before:z-10",
          // Hover lift, active press, and focus ring
          hoverable && "transition-all duration-200 hover:-translate-y-0.5 hover:border-white/[0.18] hover:shadow-[0_12px_32px_-8px_rgba(0,0,0,0.5),0_0_22px_-2px_rgba(217,70,239,0.18)]",
          "focus-within:border-[#D946EF]/50",
          className
        )}
        {...props}
      >
        {/* Soft radial purple glow in the top-right corner (strengthened in dark mode, subtle in light mode) */}
        {glow && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-10 -right-10 w-44 h-44 rounded-full bg-gradient-to-bl from-[#8B5CF6]/35 via-[#D946EF]/22 to-transparent blur-2xl z-0 transition-opacity dark:opacity-100 opacity-40"
          />
        )}
        <div className="relative z-10 w-full h-full">
          {children}
        </div>
      </div>
    )
  }
)

GlowCard.displayName = "GlowCard"
