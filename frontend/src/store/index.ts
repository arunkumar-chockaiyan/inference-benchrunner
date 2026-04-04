import { create } from 'zustand'
import type { RunSummary } from '../api'

interface AppStore {
  // Run list
  runs: RunSummary[]
  runsLoading: boolean
  runsError: string | null
  setRuns: (runs: RunSummary[]) => void
  setRunsLoading: (v: boolean) => void
  setRunsError: (e: string | null) => void

  // Compare: selected run IDs
  selectedRunIds: string[]
  toggleRunSelection: (id: string) => void
  clearSelection: () => void
}

export const useAppStore = create<AppStore>((set) => ({
  runs: [],
  runsLoading: false,
  runsError: null,
  setRuns: (runs) => set({ runs }),
  setRunsLoading: (runsLoading) => set({ runsLoading }),
  setRunsError: (runsError) => set({ runsError }),

  selectedRunIds: [],
  toggleRunSelection: (id) =>
    set((s) => ({
      selectedRunIds: s.selectedRunIds.includes(id)
        ? s.selectedRunIds.filter((x) => x !== id)
        : [...s.selectedRunIds, id],
    })),
  clearSelection: () => set({ selectedRunIds: [] }),
}))
