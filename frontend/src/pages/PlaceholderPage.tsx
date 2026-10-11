import React from 'react'
import { useLocation, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { 
  ChevronRight, 
  Layers, 
  ArrowLeft,
  FileQuestion,
  Sparkles
} from 'lucide-react'
import navConfig from '@/data/navigation.json'
import { DynamicIcon } from '@/components/DynamicIcon'
import { EmptyState } from '@/components/ui-kit/EmptyState'
import { useCognitoPilotStore } from '@/store/cognitoPilotStore'

interface PlaceholderPageProps {
  title?: string
  section?: string
  is404?: boolean
}

export const PlaceholderPage: React.FC<PlaceholderPageProps> = ({ title, section, is404 = false }) => {
  const location = useLocation()
  const openCognitoPilot = useCognitoPilotStore((state) => state.openPanel)

  // Find corresponding metadata from navigation.json if not passed directly
  let currentSection = section
  let currentTitle = title
  let currentIcon = "Compass"

  for (const s of navConfig.sections) {
    const foundItem = s.items.find(i => i.path === location.pathname)
    if (foundItem) {
      currentSection = s.title
      currentTitle = foundItem.title
      currentIcon = foundItem.icon
      break
    }
  }

  if (is404 || currentSection === "404") {
    currentSection = "Navigation"
    currentTitle = "404 - Page Not Found"
    currentIcon = "FileQuestion"
  } else if (!currentTitle) {
    const parts = location.pathname.split('/').filter(Boolean)
    currentSection = parts[0] ? parts[0].charAt(0).toUpperCase() + parts[0].slice(1) : "Section"
    currentTitle = parts[1] ? parts[1].charAt(0).toUpperCase() + parts[1].slice(1) : "Page"
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
      className="space-y-6 max-w-7xl mx-auto"
    >
      {/* PageHeader */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-[var(--border)]">
        <div>
          {/* Breadcrumb */}
          <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)] mb-1.5 font-medium">
            <Link 
              to="/" 
              className="hover:text-[var(--color-text-primary)] transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#D946EF] rounded"
            >
              Meridian
            </Link>
            <ChevronRight className="w-3 h-3 text-[var(--color-text-muted)]/60" />
            <span className="text-[var(--color-text-secondary)]">{currentSection}</span>
            <ChevronRight className="w-3 h-3 text-[var(--color-text-muted)]/60" />
            <span className="text-[#D946EF] font-medium">{currentTitle}</span>
          </div>

          <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)] flex items-center gap-3 font-sans">
            <span className="p-1.5 rounded-xl bg-gradient-to-tr from-[#D946EF]/20 to-[#8B5CF6]/20 border border-fuchsia-500/20 text-[#D946EF] shrink-0">
              {is404 ? <FileQuestion className="w-5 h-5" /> : <DynamicIcon name={currentIcon} className="w-5 h-5" />}
            </span>
            <span>{currentTitle}</span>
          </h1>
          <p className="text-xs sm:text-sm text-[var(--color-text-secondary)] mt-1 font-normal">
            {is404 
              ? "The requested route does not exist in Meridian Distribution."
              : `Operational view for ${currentTitle} within ${currentSection}.`}
          </p>
        </div>

        {/* Header Action */}
        <div className="flex items-center gap-3 self-start sm:self-center">
          <Link
            to="/"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-medium text-[var(--color-text-secondary)] bg-[var(--color-card-raised)] border border-[var(--border)] hover:text-[var(--color-text-primary)] hover:border-white/[0.15] active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)] transition-all cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Overview</span>
          </Link>
          <button
            type="button"
            onClick={() => openCognitoPilot()}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-[#D946EF] to-[#8B5CF6] hover:from-[#E879F9] hover:to-[#A78BFA] shadow-[0_0_16px_rgba(217,70,239,0.3)] active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D946EF] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)] transition-all cursor-pointer"
          >
            <Sparkles className="w-3.5 h-3.5 animate-pulse" />
            <span>Ask Cognito Pilot</span>
          </button>
        </div>
      </div>

      {/* EmptyState Component */}
      <div className="pt-2">
        <EmptyState
          icon={is404 ? <FileQuestion className="w-7 h-7 text-[#F43F5E]" /> : <Layers className="w-7 h-7 text-[#D946EF]" />}
          title={is404 ? "Route Not Found" : `${currentTitle} View`}
          hint={
            is404 
              ? `The route "${location.pathname}" could not be located in this tenant.` 
              : "This page is built from app metadata in a later step"
          }
          actionLabel="Back to Overview"
          onAction={() => window.location.href = '/'}
        />
        <div className="mt-3 flex justify-center">
          <span className="text-[11px] font-mono text-[var(--color-text-muted)] px-2.5 py-1 rounded-lg bg-[var(--color-card-raised)] border border-[var(--border)]">
            Route: {location.pathname}
          </span>
        </div>
      </div>
    </motion.div>
  )
}
