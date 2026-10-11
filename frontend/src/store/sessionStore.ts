import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface DemoUser {
  id: string
  name: string
  initials: string
  title: string
  role: 'admin' | 'regional_manager' | 'analyst'
  roleLabel: string
  regionScope: string | null
}

export const DEMO_USERS: DemoUser[] = [
  { id: 'sanmathi', name: 'Sanmathi', initials: 'S', title: 'VP Operations', role: 'admin', roleLabel: 'Admin', regionScope: null },
  { id: 'priya-nair', name: 'Priya Nair', initials: 'PN', title: 'South Regional Manager', role: 'regional_manager', roleLabel: 'Regional Manager', regionScope: 'South' },
  { id: 'arjun-mehta', name: 'Arjun Mehta', initials: 'AM', title: 'Analyst', role: 'analyst', roleLabel: 'Analyst', regionScope: null },
]

export interface SavedView {
  id: string
  pageId: string
  pageTitle: string
  filters: Record<string, string | string[] | null>
  dateRange: string | null
  sort: string | null
  savedAt: string
}

interface SessionState {
  activeUserId: string
  savedViews: SavedView[]
  setActiveUser: (userId: string) => void
  addSavedView: (view: Omit<SavedView, 'id' | 'savedAt'>) => void
}

export const useSessionStore = create<SessionState>()(persist(
  (set) => ({
    activeUserId: DEMO_USERS[0].id,
    savedViews: [],
    setActiveUser: (userId) => {
      if (DEMO_USERS.some((user) => user.id === userId)) set({ activeUserId: userId })
    },
    addSavedView: (view) => set((state) => ({
      savedViews: [{ ...view, id: crypto.randomUUID(), savedAt: new Date().toISOString() }, ...state.savedViews],
    })),
  }),
  {
    name: 'lumen-demo-session',
    partialize: (state) => ({ activeUserId: state.activeUserId, savedViews: state.savedViews }),
  }
))

export const getCurrentDemoUser = () => {
  const userId = useSessionStore.getState().activeUserId
  return DEMO_USERS.find((user) => user.id === userId) ?? DEMO_USERS[0]
}
