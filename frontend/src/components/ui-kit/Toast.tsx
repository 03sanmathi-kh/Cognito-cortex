import { Check, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface ToastProps {
  message: string | null
  onDismiss: () => void
  tone?: 'success' | 'error'
}

export const Toast: React.FC<ToastProps> = ({ message, onDismiss, tone = 'success' }) => {
  if (!message) return null

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-5 right-5 z-[60] flex max-w-sm items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--color-card)]/95 px-4 py-3 text-sm text-[var(--color-text-primary)] shadow-2xl backdrop-blur-xl"
    >
      <Check className={cn('h-4 w-4 shrink-0', tone === 'success' ? 'text-emerald-300' : 'text-rose-300')} />
      <span className="flex-1">{message}</span>
      <Button type="button" variant="ghost" size="icon" aria-label="Dismiss notification" onClick={onDismiss}>
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}
