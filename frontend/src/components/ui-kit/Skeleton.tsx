import React from 'react'
import { GlowCard } from './GlowCard'
import { cn } from '@/lib/utils'

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string
}

export const Skeleton: React.FC<SkeletonProps> = ({ className, ...props }) => {
  return (
    <div
      className={cn(
        "animate-pulse rounded-xl bg-white/[0.06] relative overflow-hidden",
        "before:absolute before:inset-0 before:-translate-x-full before:animate-[shimmer_2s_infinite] before:bg-gradient-to-r before:from-transparent before:via-white/[0.05] before:to-transparent",
        className
      )}
      {...props}
    />
  )
}

export const SkeletonCard: React.FC<{ className?: string }> = ({ className }) => {
  return (
    <GlowCard hoverable={false} className={cn("p-6 space-y-4", className)}>
      <div className="flex items-center justify-between">
        <Skeleton className="h-5 w-32 rounded-lg" />
        <Skeleton className="h-8 w-8 rounded-xl" />
      </div>
      <Skeleton className="h-4 w-48 rounded" />
      <Skeleton className="h-32 w-full rounded-xl mt-4" />
    </GlowCard>
  )
}

export const SkeletonKpi: React.FC<{ className?: string }> = ({ className }) => {
  return (
    <GlowCard hoverable={false} className={cn("p-5 flex flex-col justify-between min-h-[140px]", className)}>
      <div className="flex items-center justify-between mb-3">
        <Skeleton className="h-4 w-24 rounded" />
        <Skeleton className="h-9 w-9 rounded-xl" />
      </div>
      <div className="flex items-baseline gap-2">
        <Skeleton className="h-8 w-28 rounded-lg" />
        <Skeleton className="h-5 w-14 rounded-full" />
      </div>
      <Skeleton className="h-3 w-36 rounded mt-2" />
    </GlowCard>
  )
}

export const SkeletonChart: React.FC<{ className?: string }> = ({ className }) => {
  return (
    <GlowCard hoverable={false} className={cn("p-6 space-y-4", className)}>
      <div className="flex items-center justify-between">
        <div className="space-y-1.5">
          <Skeleton className="h-5 w-40 rounded" />
          <Skeleton className="h-3 w-56 rounded" />
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-8 w-16 rounded-xl" />
          <Skeleton className="h-8 w-8 rounded-lg" />
        </div>
      </div>
      <div className="h-[220px] flex items-end gap-3 pt-6">
        {[40, 65, 30, 80, 55, 90, 75, 45, 85, 60, 70, 95].map((height, i) => (
          <div key={i} className="flex-1 flex flex-col justify-end h-full">
            <Skeleton
              className="w-full rounded-t-md"
              style={{ height: `${height}%` }}
            />
          </div>
        ))}
      </div>
    </GlowCard>
  )
}
