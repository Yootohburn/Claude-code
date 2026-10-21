export type CacheReading = {
  lastAt: number
  now: number
  tokens: number
  window: number
  costUsd: number
  turnCostUsd: number
}

export type CacheHandoff = { text: string | null; isBusy: boolean }

declare module 'claude-code' {
  interface PluginState {
    'cache-keeper': { reading: CacheReading | null; handoff: CacheHandoff }
  }
}
