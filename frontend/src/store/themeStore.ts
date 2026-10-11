import { create } from 'zustand'

type Theme = 'dark' | 'light'

interface UIState {
  theme: Theme
  isSidebarCollapsed: boolean
  toggleTheme: () => void
  setTheme: (theme: Theme) => void
  toggleSidebar: () => void
  setSidebarCollapsed: (collapsed: boolean) => void
}

const getInitialTheme = (): Theme => {
  if (typeof window !== 'undefined') {
    const saved = localStorage.getItem('lumen_theme') as Theme | null
    if (saved === 'dark' || saved === 'light') {
      return saved
    }
  }
  return 'dark'
}

export const useUIStore = create<UIState>((set) => {
  const initialTheme = getInitialTheme()

  // Apply to document immediately
  if (typeof document !== 'undefined') {
    if (initialTheme === 'dark') {
      document.documentElement.classList.add('dark')
      document.documentElement.classList.remove('light')
    } else {
      document.documentElement.classList.remove('dark')
      document.documentElement.classList.add('light')
    }
  }

  return {
    theme: initialTheme,
    isSidebarCollapsed: false,
    toggleTheme: () =>
      set((state) => {
        const nextTheme: Theme = state.theme === 'dark' ? 'light' : 'dark'
        if (typeof window !== 'undefined') {
          localStorage.setItem('lumen_theme', nextTheme)
          if (nextTheme === 'dark') {
            document.documentElement.classList.add('dark')
            document.documentElement.classList.remove('light')
          } else {
            document.documentElement.classList.remove('dark')
            document.documentElement.classList.add('light')
          }
        }
        return { theme: nextTheme }
      }),
    setTheme: (theme: Theme) => {
      if (typeof window !== 'undefined') {
        localStorage.setItem('lumen_theme', theme)
        if (theme === 'dark') {
          document.documentElement.classList.add('dark')
          document.documentElement.classList.remove('light')
        } else {
          document.documentElement.classList.remove('dark')
          document.documentElement.classList.add('light')
        }
      }
      set({ theme })
    },
    toggleSidebar: () =>
      set((state) => ({ isSidebarCollapsed: !state.isSidebarCollapsed })),
    setSidebarCollapsed: (collapsed: boolean) =>
      set({ isSidebarCollapsed: collapsed }),
  }
})
