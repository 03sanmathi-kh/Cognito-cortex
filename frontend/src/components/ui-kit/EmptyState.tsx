import React from 'react'
import { FolderSearch } from 'lucide-react'
import { GlowCard } from './GlowCard'
import { cn } from '@/lib/utils'

export interface EmptyStateProps extends React.HTMLAttributes<HTMLDivElement> {
  icon?: React.ReactNode
  title: string
  hint: string
  actionLabel?: string
  onAction?: () => void
  inCard?: boolean
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  hint,
  actionLabel,
  onAction,
  inCard = true,
  className,
  ...props
}) => {
  const content = (
    <div className={cn("flex flex-col items-center justify-center text-center p-8 space-y-4", className)} {...props}>
      <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-[#D946EF]/15 to-[#8B5CF6]/15 border border-fuchsia-500/25 text-[#D946EF] flex items-center justify-center shadow-md shadow-fuchsia-500/15">
        {icon || <FolderSearch className="w-7 h-7" />}
      </div>

      <div className="space-y-1 max-w-md">
        <h4 className="text-base font-semibold text-[var(--color-text-primary)] tracking-tight">
          {title}
        </h4>
        <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
          {hint}
        </p>
      </div>

      {actionLabel && (
        <button
          type="button"
          onClick={onAction}
          className={cn(
            "px-4 py-2 rounded-xl text-xs font-semibold text-white tracking-wide cursor-pointer",
            "bg-gradient-to-r from-[#D946EF] to-[#8B5CF6] hover:from-[#E879F9] hover:to-[#A78BFA]",
            "shadow-[0_0_20px_rgba(217,70,239,0.3)] hover:shadow-[0_0_25px_rgba(217,70,239,0.5)]",
            "transition-all duration-200"
          )}
        >
          {actionLabel}
        </button>
      )}
    </div>
  )

  if (inCard) {
    return (
      <GlowCard hoverable={false} className="w-full">
        {content}
      </GlowCard>
    )
  }

  return content
}
