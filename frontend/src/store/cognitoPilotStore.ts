import { create } from 'zustand'

interface CognitoPilotState {
  open: boolean
  prompt: string | null
  promptVersion: number
  resetSignal: number
  openPanel: (prompt?: string) => void
  closePanel: () => void
  clearSession: () => void
}

export const useCognitoPilotStore = create<CognitoPilotState>((set) => ({
  open: false,
  prompt: null,
  promptVersion: 0,
  resetSignal: 0,
  openPanel: (prompt) => set((state) => ({
    open: true,
    prompt: prompt ?? null,
    promptVersion: state.promptVersion + 1,
  })),
  closePanel: () => set({ open: false }),
  clearSession: () => set((state) => ({ resetSignal: state.resetSignal + 1 })),
}))
