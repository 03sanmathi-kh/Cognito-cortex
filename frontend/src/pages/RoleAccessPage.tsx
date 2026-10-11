import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { GlowCard } from '@/components/ui-kit/GlowCard'
import { Skeleton } from '@/components/ui-kit/Skeleton'
import { PlaceholderPage } from '@/pages/PlaceholderPage'
import { apiFetch } from '@/lib/api'
import { useSessionStore } from '@/store/sessionStore'

type PageAccess = {
  exists: boolean
  accessible: boolean
  role: string
  reason: string | null
}

export const RoleAccessPage: React.FC = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const activeUserId = useSessionStore((state) => state.activeUserId)
  const [access, setAccess] = useState<PageAccess | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setAccess(null)
    setFailed(false)
    apiFetch(`/api/page-access?path=${encodeURIComponent(location.pathname)}`)
      .then(async (response) => {
        if (!response.ok) throw new Error('Unable to check page access')
        return response.json() as Promise<PageAccess>
      })
      .then((result) => {
        if (!cancelled) setAccess(result)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => { cancelled = true }
  }, [activeUserId, location.pathname])

  if (!access && !failed) {
    return (
      <div className="mx-auto mt-10 max-w-xl space-y-3">
        <Skeleton className="h-10 w-56 rounded-xl" />
        <Skeleton className="h-24 w-full rounded-2xl" />
      </div>
    )
  }

  if (failed || !access?.exists) {
    return <PlaceholderPage title="Page Not Found" section="404" is404={true} />
  }

  if (access.accessible) {
    return <PlaceholderPage title="Page Not Found" section="404" is404={true} />
  }

  return (
    <div className="mx-auto mt-10 max-w-xl">
      <GlowCard className="space-y-5 p-7 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl border border-amber-400/30 bg-amber-400/10 text-amber-200">
          <ShieldAlert className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">Access restricted</h1>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">{access.reason}</p>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">Current role: {access.role}</p>
        </div>
        <Button type="button" variant="outline" onClick={() => navigate('/')}>Back to Overview</Button>
      </GlowCard>
    </div>
  )
}
