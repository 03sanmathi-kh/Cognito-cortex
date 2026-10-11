import React, { useState, useRef, useEffect } from 'react'
import { MoreVertical, RefreshCw, Download, Settings, Trash2 } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'

export interface CardMenuItem {
  label: string
  icon?: React.ReactNode
  onClick?: () => void
  danger?: boolean
}

export interface CardMenuProps {
  items?: CardMenuItem[]
  className?: string
  align?: 'left' | 'right'
}

export const CardMenu: React.FC<CardMenuProps> = ({
  items,
  className,
  align = 'right',
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  const defaultItems: CardMenuItem[] = [
    { label: "Refresh data", icon: <RefreshCw className="w-3.5 h-3.5" />, onClick: () => {} },
    { label: "Export CSV", icon: <Download className="w-3.5 h-3.5" />, onClick: () => {} },
    { label: "Settings", icon: <Settings className="w-3.5 h-3.5" />, onClick: () => {} },
    { label: "Clear card", icon: <Trash2 className="w-3.5 h-3.5" />, danger: true, onClick: () => {} },
  ]

  const menuItems = items || defaultItems

  // Close when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen])

  return (
    <div className={cn("relative inline-block text-left", className)} ref={menuRef}>
      <button
        type="button"
        aria-label="Card options"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
          "hover:bg-white/[0.08] transition-colors focus:outline-none cursor-pointer",
          isOpen && "bg-white/[0.08] text-[var(--color-text-primary)]"
        )}
      >
        <MoreVertical className="w-4 h-4" />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -4 }}
            transition={{ duration: 0.15 }}
            className={cn(
              "absolute top-full mt-1.5 w-44 z-50",
              align === 'right' ? "right-0" : "left-0",
              "rounded-xl bg-[var(--color-card-raised)] border border-[var(--border)]",
              "shadow-[0_10px_25px_-5px_rgba(0,0,0,0.5),0_0_15px_rgba(0,0,0,0.3)]",
              "p-1 backdrop-blur-md"
            )}
          >
            {menuItems.map((item, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  setIsOpen(false)
                  item.onClick?.()
                }}
                className={cn(
                  "w-full px-2.5 py-1.5 rounded-lg text-xs font-medium flex items-center gap-2",
                  "transition-colors text-left cursor-pointer",
                  item.danger
                    ? "text-[#F43F5E] hover:bg-rose-500/10"
                    : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-white/[0.06]"
                )}
              >
                {item.icon && <span className="shrink-0">{item.icon}</span>}
                <span className="truncate">{item.label}</span>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
