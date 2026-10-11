import { create } from 'zustand'
import { apiFetch } from '@/lib/api'

export interface MetadataApp {
  id: string
  name: string
  currency: string
  description?: string
}

export interface MetadataDirectory {
  id: string
  title: string
  icon?: string
  subdirectories?: Array<{ id: string; title: string }>
}

export interface MetadataPage {
  id: string
  title: string
  description: string
  directory: string
  subdirectory: string
  route: string
  icon?: string
  keywords?: string[]
  widgets?: Array<any>
  filters?: Array<any>
  date_range_options?: string[]
  default_date_range?: string
  region_scoped?: boolean
  actions?: Array<{ id: string; label?: string; requires_confirmation?: boolean }>
  sort_options?: Array<{ id?: string; field?: string; label?: string; order?: string }>
  default_sort?: { id?: string; field?: string; order?: string }
}

interface MetadataState {
  app: MetadataApp | null
  asOf: string | null
  directories: MetadataDirectory[]
  pages: MetadataPage[]
  loading: boolean
  error: string | null
  fetchMetadata: () => Promise<void>
  getPage: (id: string) => MetadataPage | undefined
  refetch: () => Promise<void>
}

export const useMetadataStore = create<MetadataState>((set, get) => ({
  app: null,
  asOf: null,
  directories: [],
  pages: [],
  loading: true,
  error: null,
  fetchMetadata: async () => {
    set({ loading: true, error: null })

    try {
      const response = await apiFetch('/api/metadata')
      if (!response.ok) {
        throw new Error(`Metadata request failed: ${response.status}`)
      }

      const payload = await response.json()
      set({
        app: payload.app ?? null,
        asOf: payload.as_of ?? null,
        directories: payload.directories ?? [],
        pages: payload.pages ?? [],
        loading: false,
        error: null,
      })
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : 'Unable to load metadata',
      })
    }
  },
  getPage: (id) => get().pages.find((page) => page.id === id),
  refetch: async () => {
    await get().fetchMetadata()
  },
}))
