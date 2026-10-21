export type NextStep = string

declare module 'claude-code' {
  interface PluginState {
    'next-steps': { steps: NextStep[]; isThinking: boolean }
  }
}
