import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { AppLayout } from '@/components/layout/AppLayout'
import { CognitoPilotPanel } from '@/components/CognitoPilotPanel'
import { DashboardOverview } from '@/pages/DashboardOverview'
import { UiKitPage } from '@/pages/UiKitPage'
import { DynamicPage } from '@/pages/DynamicPage'
import { RoleAccessPage } from '@/pages/RoleAccessPage'
import { useMetadataStore } from '@/store/metadataStore'

function AnimatedRoutes() {
  const location = useLocation()
  const pages = useMetadataStore((state) => state.pages)

  return (
    <>
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          <Route element={<AppLayout />}>
            <Route path="/" element={<DashboardOverview />} />
            <Route path="/dashboard/overview" element={<DashboardOverview />} />
            <Route path="/kit" element={<UiKitPage />} />

            {pages
              .filter((page) => page.route && page.route !== '/' && page.route !== '/dashboard/overview')
              .map((page) => (
                <Route
                  key={page.id}
                  path={page.route}
                  element={<DynamicPage pageId={page.id} />}
                />
              ))}

            <Route path="*" element={<RoleAccessPage />} />
          </Route>
        </Routes>
      </AnimatePresence>
      <CognitoPilotPanel />
    </>
  )
}

export default function App() {
  const fetchMetadata = useMetadataStore((state) => state.fetchMetadata)

  useEffect(() => {
    void fetchMetadata()
  }, [fetchMetadata])

  return (
    <BrowserRouter>
      <AnimatedRoutes />
    </BrowserRouter>
  )
}
