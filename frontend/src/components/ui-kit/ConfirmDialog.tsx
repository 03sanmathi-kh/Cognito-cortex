import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { GlowCard } from './GlowCard'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: string
  consequences: string[]
  confirmLabel?: string
  onCancel: () => void
  onConfirm: () => void
}

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  title,
  description,
  consequences,
  confirmLabel = 'Confirm',
  onCancel,
  onConfirm,
}) => {
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const dialog = dialogRef.current
    const focusable = () => dialog?.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
    )
    focusable()?.[0]?.focus()

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCancel()
        return
      }
      if (event.key !== 'Tab') return
      const items = focusable()
      if (!items?.length) return
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      previousFocus?.focus()
    }
  }, [open, onCancel])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" onMouseDown={(event) => event.target === event.currentTarget && onCancel()}>
      <GlowCard
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
        className="w-full max-w-md space-y-5 border-white/15 bg-[var(--color-card)]/95 p-6 shadow-2xl backdrop-blur-xl"
      >
        <div>
          <h2 id="confirm-dialog-title" className="text-lg font-semibold text-[var(--color-text-primary)]">{title}</h2>
          <p id="confirm-dialog-description" className="mt-2 text-sm text-[var(--color-text-secondary)]">{description}</p>
        </div>
        <ul className="space-y-2 text-sm text-[var(--color-text-secondary)]">
          {consequences.map((item) => <li key={item} className="flex gap-2"><span aria-hidden="true">•</span><span>{item}</span></li>)}
        </ul>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
          <Button type="button" variant="gradient" onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </GlowCard>
    </div>
  )
}
