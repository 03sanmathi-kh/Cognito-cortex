import { create } from 'zustand'

type FilterValue = string | string[] | null
type UiStateSource = 'user' | 'agent'

type FilterMetadata = {
  name: string
  type?: string
  allowed_values?: string[]
  default?: FilterValue
  default_value?: FilterValue
}

type SortMetadata = { id?: string; field?: string }

type PageUiMetadata = {
  id: string
  filters?: FilterMetadata[]
  date_range_options?: string[]
  default_date_range?: string
  sort_options?: SortMetadata[]
  default_sort?: { id?: string; field?: string }
}

export interface PageUiState {
  filters: Record<string, FilterValue>
  dateRange: string | null
  customStart: string | null
  customEnd: string | null
  sort: string | null
  sortDirection?: string | null
  highlights: string[]
  defaults: {
    filters: Record<string, FilterValue>
    dateRange: string | null
    customStart: string | null
    customEnd: string | null
    sort: string | null
    sortDirection?: string | null
  }
}

export interface UiContext {
  page_id: string
  filters: Record<string, FilterValue>
  date_range: string | null
  sort: string | null
  sort_direction?: string | null
}

type UiStatePatch = {
  filters?: Record<string, FilterValue>
  dateRange?: string | null
  customStart?: string | null
  customEnd?: string | null
  sort?: string | null
  sortDirection?: string | null
}

interface UiStateStore {
  pages: Record<string, PageUiState>
  activePageId: string | null
  initializePage: (page: PageUiMetadata) => void
  setActivePage: (pageId: string) => void
  clearAll: () => void
  setFilter: (pageId: string, key: string, value: FilterValue) => void
  setDateRange: (pageId: string, value: string | null) => void
  setSort: (pageId: string, value: string | null) => void
  resetPage: (pageId: string) => void
  applyUiState: (pageId: string, patch: UiStatePatch, source: UiStateSource) => void
  clearHighlights: (pageId: string) => void
  getUiContext: () => UiContext | null
}

const filterDefaults = (filters: FilterMetadata[] = []) => Object.fromEntries(
  filters.map((filter) => {
    const configured = filter.default ?? filter.default_value
    const value = filter.type === 'multi_select'
      ? Array.isArray(configured) ? configured : configured == null ? [] : [configured]
      : Array.isArray(configured) ? configured[0] ?? null : configured ?? null
    return [filter.name, value]
  })
)

const optionId = (option?: SortMetadata) => option?.id ?? option?.field ?? null

export const useUiStateStore = create<UiStateStore>((set, get) => {
  const applyPatch = (pageId: string, patch: UiStatePatch, source: UiStateSource) => {
    const current = get().pages[pageId]
    if (!current) return

    const nextFilters = { ...current.filters, ...(patch.filters ?? {}) }
    const changed: string[] = []
    for (const [key, value] of Object.entries(patch.filters ?? {})) {
      if (JSON.stringify(current.filters[key]) !== JSON.stringify(value)) changed.push(`filter:${key}`)
    }
    if (patch.dateRange !== undefined && current.dateRange !== patch.dateRange) changed.push('date_range')
    if (patch.sort !== undefined && current.sort !== patch.sort) changed.push('sort')
    if (patch.sortDirection !== undefined && current.sortDirection !== patch.sortDirection) changed.push('sort')

    set((state) => ({
      pages: {
        ...state.pages,
        [pageId]: {
          ...current,
          filters: nextFilters,
          dateRange: patch.dateRange === undefined ? current.dateRange : patch.dateRange,
          customStart: patch.customStart === undefined ? current.customStart : patch.customStart,
          customEnd: patch.customEnd === undefined ? current.customEnd : patch.customEnd,
          sort: patch.sort === undefined ? current.sort : patch.sort,
          sortDirection: patch.sortDirection === undefined ? current.sortDirection : patch.sortDirection,
          highlights: source === 'agent' ? changed : [],
        },
      },
    }))
  }

  return {
    pages: {},
    activePageId: null,
    initializePage: (page) => set((state) => {
      if (state.pages[page.id]) return { activePageId: page.id }

      const filters = filterDefaults(page.filters)
      const dateRange = page.default_date_range ?? page.date_range_options?.[0] ?? null
      const sort = page.default_sort?.id
        ?? page.default_sort?.field
        ?? optionId(page.sort_options?.[0])
      const sortDirection = 'asc'

      return {
        activePageId: page.id,
        pages: {
          ...state.pages,
          [page.id]: {
            filters,
            dateRange,
            customStart: null,
            customEnd: null,
            sort,
            sortDirection,
            highlights: [],
            defaults: { filters: { ...filters }, dateRange, customStart: null, customEnd: null, sort, sortDirection },
          },
        },
      }
    }),
    setActivePage: (pageId) => set({ activePageId: pageId }),
    clearAll: () => set({ pages: {}, activePageId: null }),
    setFilter: (pageId, key, value) => applyPatch(pageId, { filters: { [key]: value } }, 'user'),
    setDateRange: (pageId, value) => applyPatch(pageId, { dateRange: value, customStart: null, customEnd: null }, 'user'),
    setSort: (pageId, value) => applyPatch(pageId, { sort: value }, 'user'),
    resetPage: (pageId) => {
      const current = get().pages[pageId]
      if (!current) return
      applyPatch(pageId, {
        filters: current.defaults.filters,
        dateRange: current.defaults.dateRange,
        customStart: current.defaults.customStart,
        customEnd: current.defaults.customEnd,
        sort: current.defaults.sort,
      }, 'user')
    },
    applyUiState: applyPatch,
    clearHighlights: (pageId) => {
      const current = get().pages[pageId]
      if (!current) return
      set((state) => ({ pages: { ...state.pages, [pageId]: { ...current, highlights: [] } } }))
    },
    getUiContext: () => {
      const state = get()
      const pageId = state.activePageId
      const page = pageId ? state.pages[pageId] : undefined
      if (!pageId || !page) return null
      return { page_id: pageId, filters: page.filters, date_range: page.dateRange, sort: page.sort, sort_direction: page.sortDirection ?? 'asc' }
    },
  }
})
