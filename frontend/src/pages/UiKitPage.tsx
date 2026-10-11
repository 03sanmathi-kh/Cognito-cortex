import React, { useState } from 'react'
import { motion } from 'framer-motion'
import {
  FileText,
  Sparkles,
  TrendingUp,
  Clock,
  PenTool,
  Share2,
  Cpu,
  Scissors,
  ChevronRight,
  Database,
  Sun,
  Moon,
} from 'lucide-react'
import {
  GlowCard,
  KpiCard,
  TrendChip,
  StatusBadge,
  ProgressBar,
  CardMenu,
  ChartCard,
  GlowAreaChart,
  SkeletonKpi,
  SkeletonChart,
  EmptyState,
} from '@/components/ui-kit'
import { useUIStore } from '@/store/themeStore'

export const UiKitPage: React.FC = () => {
  const { theme, toggleTheme } = useUIStore()
  const [showSkeletons, setShowSkeletons] = useState(false)

  // Sample chart data replicating the reference screenshot curve
  const chartData = [
    { name: 'Jan', thisMonth: 220, lastMonth: 120 },
    { name: 'Feb', thisMonth: 290, lastMonth: 140 },
    { name: 'Mar', thisMonth: 200, lastMonth: 210 },
    { name: 'Apr', thisMonth: 340, lastMonth: 120 },
    { name: 'May', thisMonth: 240, lastMonth: 190 },
    { name: 'Jun', thisMonth: 400, lastMonth: 150 },
    { name: 'Jul', thisMonth: 380, lastMonth: 230 },
  ]

  const chartSeries = [
    { key: 'thisMonth', name: 'This Month', color: '#8B5CF6' },
    { key: 'lastMonth', name: 'Last Month', color: '#22C55E' },
  ]

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2 }}
      className="space-y-8 max-w-7xl mx-auto pb-16"
    >
      {/* Kit Showcase Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-[var(--color-card-raised)] border border-[var(--border)] glow-card">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-fuchsia-500/20 text-[#D946EF] border border-fuchsia-500/30">
              Design System
            </span>
            <h1 className="text-xl font-bold text-[var(--color-text-primary)]">
              UI Kit & Component Playground
            </h1>
          </div>
          <p className="text-xs text-[var(--color-text-secondary)] mt-1">
            Replicating reference styling, glow effects, hover states, and dark/light tokens.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setShowSkeletons(!showSkeletons)}
            className="px-3 py-1.5 rounded-xl text-xs font-medium border border-[var(--border)] bg-[var(--color-card)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors cursor-pointer"
          >
            {showSkeletons ? 'Show Live Components' : 'Preview Skeletons'}
          </button>

          <button
            type="button"
            onClick={toggleTheme}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-gradient-to-r from-[#D946EF] to-[#8B5CF6] text-white shadow-md shadow-fuchsia-500/20 cursor-pointer"
          >
            {theme === 'dark' ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
            <span>Theme: {theme}</span>
          </button>
        </div>
      </div>

      {showSkeletons ? (
        /* Skeleton Previews */
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <SkeletonKpi />
            <SkeletonKpi />
            <SkeletonKpi />
            <SkeletonKpi />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <div className="lg:col-span-2">
              <SkeletonChart />
            </div>
            <SkeletonChart />
          </div>
        </div>
      ) : (
        <>
          {/* Section 1: KPI Cards Row (matching reference screenshot) */}
          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
              1. Top Metrics (KpiCard)
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <KpiCard
                label="Total Content"
                value={1324}
                trend={{ value: 8.73, isPositive: true, variant: 'purple' }}
                caption="All-time complete content"
                icon={<FileText className="w-4 h-4" />}
                iconColor="magenta"
              />
              <KpiCard
                label="AI Credits Used"
                value={2450}
                trend={{ value: 5.32, isPositive: true, variant: 'green' }}
                caption="All-time AI credits Used"
                icon={<Sparkles className="w-4 h-4" />}
                iconColor="purple"
              />
              <KpiCard
                label="Avg. Engagement"
                value={1324}
                trend={{ value: 6.89, isPositive: true, variant: 'purple' }}
                caption="All-time Avg. engagement"
                icon={<TrendingUp className="w-4 h-4" />}
                iconColor="purple"
              />
              <KpiCard
                label="Time Saved"
                value="42h"
                trend={{ value: '+15h', isPositive: true, variant: 'green' }}
                caption="All-time total time saved"
                icon={<Clock className="w-4 h-4" />}
                iconColor="purple"
              />
            </div>
          </section>

          {/* Section 2: Trends Chart + Quick Actions (matching reference screenshot) */}
          <section className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Chart Card */}
            <div className="lg:col-span-2">
              <ChartCard
                title="Grammar Score Trends"
                subtitle="Track and analyze grammar performance."
                filterLabel="Filter"
                legends={[
                  { label: "This Month", color: "#8B5CF6" },
                  { label: "Last Month", color: "#22C55E" },
                ]}
              >
                <GlowAreaChart
                  data={chartData}
                  series={chartSeries}
                  height={240}
                />
              </ChartCard>
            </div>

            {/* Quick Actions Card */}
            <GlowCard glow className="p-6 flex flex-col justify-between space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-[var(--color-text-primary)]">
                    Quick Actions
                  </h3>
                  <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                    Start Generating & Creating
                  </p>
                </div>
                <CardMenu />
              </div>

              {/* Action Tiles */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                {/* Tile 1: Blog Post */}
                <div className="p-4 rounded-xl bg-[var(--color-card-raised)] border border-[var(--border)] space-y-3 group hover:border-[#D946EF]/30 transition-all cursor-pointer">
                  <div className="w-8 h-8 rounded-lg bg-fuchsia-500/15 text-[#D946EF] flex items-center justify-center border border-fuchsia-500/25">
                    <PenTool className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold text-[var(--color-text-primary)]">
                      Blog Post
                    </h4>
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-[11px] text-[var(--color-text-muted)]">Grammar score</span>
                      <span className="text-xs font-bold text-[#D946EF] tabular-nums">88</span>
                    </div>
                  </div>
                  <p className="text-[10px] text-[var(--color-text-secondary)] line-clamp-2">
                    AI checks grammar and gives a quality score.
                  </p>
                  <p className="text-[9px] text-[var(--color-text-muted)] pt-1 border-t border-white/[0.05]">
                    Last update: 12 Mar 04:16 pm
                  </p>
                </div>

                {/* Tile 2: Social Post */}
                <div className="p-4 rounded-xl bg-[var(--color-card-raised)] border border-[var(--border)] space-y-3 group hover:border-[#22C55E]/30 transition-all cursor-pointer">
                  <div className="w-8 h-8 rounded-lg bg-emerald-500/15 text-[#22C55E] flex items-center justify-center border border-emerald-500/25">
                    <Share2 className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold text-[var(--color-text-primary)]">
                      Social Post
                    </h4>
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-[11px] text-[var(--color-text-muted)]">Grammar score</span>
                      <span className="text-xs font-bold text-[#22C55E] tabular-nums">75</span>
                    </div>
                  </div>
                  <p className="text-[10px] text-[var(--color-text-secondary)] line-clamp-2">
                    AI checks grammar score to improve writing quality.
                  </p>
                  <p className="text-[9px] text-[var(--color-text-muted)] pt-1 border-t border-white/[0.05]">
                    Last update: 15 Apr 05:22 pm
                  </p>
                </div>
              </div>
            </GlowCard>
          </section>

          {/* Section 3: Recent Documents & Tools (matching reference screenshot) */}
          <section className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Recent Documents Card */}
            <GlowCard className="lg:col-span-2 p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-[var(--color-text-primary)]">
                    Recent Documents
                  </h3>
                  <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                    View and open your latest files quickly.
                  </p>
                </div>
                <CardMenu />
              </div>

              <div className="space-y-3 pt-1">
                {/* Doc 1 */}
                <div className="p-3 rounded-xl bg-[var(--color-card-raised)] border border-[var(--border)] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-fuchsia-500/15 text-[#D946EF] flex items-center justify-center border border-fuchsia-500/25 shrink-0">
                      <PenTool className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-[var(--color-text-primary)]">
                          Blog Post
                        </span>
                        <StatusBadge variant="draft" />
                      </div>
                      <p className="text-[11px] text-[var(--color-text-muted)] mt-0.5">
                        Last modified on: 25/03/2026
                      </p>
                    </div>
                  </div>

                  <div className="w-full sm:w-48">
                    <ProgressBar
                      value={100}
                      variant="purple"
                      segmented
                      size="sm"
                    />
                  </div>
                </div>

                {/* Doc 2 */}
                <div className="p-3 rounded-xl bg-[var(--color-card-raised)] border border-[var(--border)] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/15 text-[#22C55E] flex items-center justify-center border border-emerald-500/25 shrink-0">
                      <Share2 className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-[var(--color-text-primary)]">
                          Social Media
                        </span>
                        <StatusBadge variant="published" />
                      </div>
                      <p className="text-[11px] text-[var(--color-text-muted)] mt-0.5">
                        Last modified on: 28/03/2026
                      </p>
                    </div>
                  </div>

                  <div className="w-full sm:w-48">
                    <ProgressBar
                      value={55}
                      variant="green"
                      segmented
                      size="sm"
                    />
                  </div>
                </div>
              </div>
            </GlowCard>

            {/* Tools Card */}
            <GlowCard className="p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-[var(--color-text-primary)]">
                    Tools
                  </h3>
                  <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                    AI writing tools to improve content.
                  </p>
                </div>
                <CardMenu />
              </div>

              <div className="space-y-3 pt-1">
                {/* Tool 1 */}
                <div className="p-3 rounded-xl bg-[var(--color-card-raised)] border border-[var(--border)] flex items-center justify-between hover:border-purple-500/30 transition-all cursor-pointer group">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full border border-purple-500/30 flex items-center justify-center text-[#D946EF]">
                      <Cpu className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-[var(--color-text-primary)]">
                        AI Writing Tools
                      </p>
                      <p className="text-[10px] text-[#A855F7] font-medium">
                        +20% From last month
                      </p>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-[var(--color-text-muted)] group-hover:text-[var(--color-text-primary)] transition-colors" />
                </div>

                {/* Tool 2 */}
                <div className="p-3 rounded-xl bg-[var(--color-card-raised)] border border-[var(--border)] flex items-center justify-between hover:border-emerald-500/30 transition-all cursor-pointer group">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full border border-emerald-500/30 flex items-center justify-center text-[#22C55E]">
                      <Scissors className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-[var(--color-text-primary)]">
                        Shorten Text
                      </p>
                      <p className="text-[10px] text-[#22C55E] font-medium">
                        +15% Summarize your writing
                      </p>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-[var(--color-text-muted)] group-hover:text-[var(--color-text-primary)] transition-colors" />
                </div>
              </div>
            </GlowCard>
          </section>

          {/* Section 4: StatusBadges & TrendChips Gallery */}
          <section className="p-6 rounded-2xl bg-[var(--color-card)] border border-[var(--border)] glow-card space-y-5">
            <h3 className="text-sm font-bold text-[var(--color-text-primary)]">
              4. Badges, Chips & Progress Variants
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Badges */}
              <div className="space-y-2">
                <p className="text-xs text-[var(--color-text-secondary)] font-medium">StatusBadge Variants</p>
                <div className="flex flex-wrap gap-2">
                  <StatusBadge variant="draft" showDot />
                  <StatusBadge variant="published" showDot />
                  <StatusBadge variant="warning" showDot />
                  <StatusBadge variant="success" showDot />
                  <StatusBadge variant="danger" showDot />
                </div>
              </div>

              {/* TrendChips */}
              <div className="space-y-2">
                <p className="text-xs text-[var(--color-text-secondary)] font-medium">TrendChip Variants</p>
                <div className="flex flex-wrap gap-2">
                  <TrendChip value={12.4} />
                  <TrendChip value={-4.8} />
                  <TrendChip value={0} />
                  <TrendChip value={8.5} variant="purple" />
                  <TrendChip value="Active" variant="neutral" showIcon={false} />
                </div>
              </div>

              {/* Progress Bars */}
              <div className="space-y-2">
                <p className="text-xs text-[var(--color-text-secondary)] font-medium">Progress Bar Fill</p>
                <ProgressBar value={72} label="Continuous Gradient" variant="gradient" />
                <ProgressBar value={40} label="Segmented Green" variant="green" segmented />
              </div>
            </div>
          </section>

          {/* Section 5: EmptyState Preview */}
          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
              5. Empty State (EmptyState)
            </h2>
            <EmptyState
              icon={<Database className="w-7 h-7" />}
              title="No transactions found for this region"
              hint="Try adjusting your date range, clearing filters, or asking Cognito Cortex to broaden your query."
              actionLabel="Reset Active Filters"
              onAction={() => alert('Filters reset!')}
            />
          </section>
        </>
      )}
    </motion.div>
  )
}
