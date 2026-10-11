import React from 'react'
import { cn } from '@/lib/utils'

export type StatusVariant = 'draft' | 'published' | 'warning' | 'success' | 'danger'

export interface StatusBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: StatusVariant
  children?: React.ReactNode
  showDot?: boolean
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  variant = 'draft',
  children,
  showDot = false,
  className,
  ...props
}) => {
  const variantStyles: Record<StatusVariant, { badge: string; dot: string; defaultLabel: string }> = {
    draft: {
      badge: "bg-amber-500/15 text-[#F59E0B] border-amber-500/25",
      dot: "bg-[#F59E0B]",
      defaultLabel: "Draft",
    },
    published: {
      badge: "bg-emerald-500/15 text-[#22C55E] border-emerald-500/25",
      dot: "bg-[#22C55E]",
      defaultLabel: "Published",
    },
    warning: {
      badge: "bg-amber-500/15 text-[#F59E0B] border-amber-500/25",
      dot: "bg-[#F59E0B]",
      defaultLabel: "Warning",
    },
    success: {
      badge: "bg-emerald-500/15 text-[#22C55E] border-emerald-500/25",
      dot: "bg-[#22C55E]",
      defaultLabel: "Success",
    },
    danger: {
      badge: "bg-rose-500/15 text-[#F43F5E] border-rose-500/25",
      dot: "bg-[#F43F5E]",
      defaultLabel: "Danger",
    },
  }

  const { badge, dot, defaultLabel } = variantStyles[variant]

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium border tracking-wide",
        badge,
        className
      )}
      {...props}
    >
      {showDot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", dot)} />}
      <span>{children || defaultLabel}</span>
    </span>
  )
}
