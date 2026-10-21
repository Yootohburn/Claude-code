export type GoalItem = { id: string; text: string; status: 'pending' | 'in_progress' | 'completed' }

export type Goal = {
  title: string
  startedAt: number
  endedAt: number | null
  items: GoalItem[]
}

export type GoalElsewhere = { sessionId: string; goal: Goal; updatedAt: number }

declare module 'claude-code' {
  interface PluginState {
    'goal-tracker': {
      goal: Goal | null
      now: number
      isAll: boolean
      others: GoalElsewhere[]
    }
  }
}
