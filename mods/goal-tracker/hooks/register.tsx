import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Goal, GoalElsewhere, GoalItem } from '../types'

const PANE = 'goal-tracker'
const DAY_MS = 24 * 60 * 60 * 1000

const goal = atom({ plugin: 'goal-tracker', key: 'goal' } as const, null)
const now = atom({ plugin: 'goal-tracker', key: 'now' } as const, 0)
const isAll = atom({ plugin: 'goal-tracker', key: 'isAll' } as const, false)
const others = atom({ plugin: 'goal-tracker', key: 'others' } as const, [])

const PLAN = [
  'Work toward this goal on your own until it is done:',
  '',
  '{goal}',
  '',
  'First plan it as a short checklist (about 4 items) with your task/todo tool,',
  'then work through the items one by one, marking each in progress and completed as you go.',
].join('\n')

const sharedDir = async ($: EngineInterface) =>
  `${(await $.env.get('HOME')) ?? '/tmp'}/.claude/mods-shared/goal-tracker`

const percentOf = (g: Goal) =>
  g.items.length === 0
    ? 0
    : Math.round((g.items.filter(i => i.status === 'completed').length / g.items.length) * 100)

const bar = (percent: number, width: number) => {
  const full = Math.round((percent / 100) * width)

  return `${'█'.repeat(full)}${'░'.repeat(width - full)}`
}

const elapsed = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)

  return h > 0 ? `${h}h ${m}m` : `${m}m ${String(s % 60).padStart(2, '0')}s`
}

const phaseOf = (g: Goal) =>
  g.endedAt !== null
    ? 'Done'
    : g.items.length === 0
      ? 'Planning…'
      : `Working: ${g.items.find(i => i.status === 'in_progress')?.text ?? 'next item'}`

const publish = async ($: EngineInterface, g: Goal | null) => {
  const dir = await sharedDir($)
  const id = await $.session.id()
  const entry: GoalElsewhere | null = g === null ? null : { sessionId: id, goal: g, updatedAt: await $.clock.now() }
  await $.fs.write(`${dir}/${id}.json`, JSON.stringify(entry)).catch(() => undefined)
}

const setGoal = async ($: EngineInterface, fn: (g: Goal | null) => Goal | null) => {
  const t = await $.clock.now()
  await update($, goal, prev => {
    const g = fn(prev)
    if (g === null || g.items.length === 0) {
      return g
    }
    const isDone = g.items.every(i => i.status === 'completed')

    return { ...g, endedAt: isDone ? (g.endedAt ?? t) : null }
  })
  await publish($, await read($, goal))
}

const ensureGoal = (title: string, t: number) => (g: Goal | null): Goal =>
  g ?? { title, startedAt: t, endedAt: null, items: [] }

const startGoal = async ($: EngineInterface, title: string) => {
  const t = await $.clock.now()
  await setGoal($, () => ({ title, startedAt: t, endedAt: null, items: [] }))
  await update($, now, () => t)
  await $.ui.open({ id: PANE, title: 'Goal Tracker' })
}

const parse = (text: string): GoalElsewhere | null => {
  try {
    return JSON.parse(text) as GoalElsewhere | null
  } catch {
    return null
  }
}

const loadOthers = async ($: EngineInterface) => {
  const dir = await sharedDir($)
  const id = await $.session.id()
  const t = await $.clock.now()
  const entries = await $.fs.list(dir).catch(() => [])
  const found: GoalElsewhere[] = []
  for (const entry of entries) {
    if (entry.kind !== 'file' || !entry.name.endsWith('.json') || entry.name === `${id}.json`) {
      continue
    }
    const text = await $.fs.read(`${dir}/${entry.name}`).catch(() => 'null')
    const parsed = parse(text)
    if (parsed !== null && t - parsed.updatedAt < DAY_MS) {
      found.push(parsed)
    }
  }
  await update($, others, () => found.sort((a, b) => b.updatedAt - a.updatedAt))
}

const tick = async ($: EngineInterface) => {
  const g = await read($, goal)
  if (g !== null && g.endedAt === null) {
    const t = await $.clock.now()
    await update($, now, () => t)
  }
  if (await read($, isAll)) {
    await loadOthers($)
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const commands = await $.command.list()
    if (!commands.some(c => c.name === 'goal')) {
      await $.command.register({
        name: 'goal',
        description: 'Set a long-running goal and track it in the Goal Tracker pane',
        argumentHint: '<what to achieve>',
      })
    }
    await $.command.register({
      name: 'goals',
      description: 'Open the Goal Tracker pane',
    })
    $.clock.every(5000, () => void tick($))

    return next(e)
  })

  on('command.run', { command: 'goals' }, async $ => {
    await $.ui.open({ id: PANE, title: 'Goal Tracker' })

    return { text: 'Goal Tracker opened.' }
  })

  on('command.run', { command: 'goal' }, async ($, e, next) => {
    const title = e.args.trim()
    if (title !== '') {
      await startGoal($, title)
    }
    const commands = await $.command.list()
    const isOurs = commands.some(c => c.name === 'goal' && c.plugin === $.plugin.name)
    if (!isOurs) {
      return next(e)
    }
    if (title === '') {
      return { text: 'Usage: /goal <what to achieve>' }
    }
    await $.prompt.submit({ text: PLAN.replace('{goal}', title), asUser: true })

    return { text: `Goal set: ${title}` }
  })

  on('tool.call', { tool: 'TodoWrite' }, async ($, e, next) => {
    const ran = await next(e)
    if (e.agentId === undefined && ran.deny === undefined && ran.isError !== true) {
      const t = await $.clock.now()
      const items: GoalItem[] = e.todos.map((todo, i) => ({
        id: String(i),
        text: todo.content,
        status: todo.status,
      }))
      await setGoal($, g => ({ ...ensureGoal('Session tasks', t)(g), items }))
    }

    return ran
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: 'TaskCreate' }, async ($, e, next) => {
    const ran = await next(e)
    if (e.agentId === undefined && ran.deny === undefined && ran.isError !== true) {
      const t = await $.clock.now()
      const id = ran.result.task.id
      await setGoal($, g => {
        const base = ensureGoal('Session tasks', t)(g)

        return { ...base, items: [...base.items, { id, text: e.subject, status: 'pending' }] }
      })
    }

    return ran
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: 'TaskUpdate' }, async ($, e, next) => {
    const ran = await next(e)
    if (e.agentId === undefined && ran.deny === undefined && ran.isError !== true) {
      await setGoal($, g => {
        if (g === null) {
          return g
        }
        const items = g.items
          .filter(i => !(i.id === e.taskId && e.status === 'deleted'))
          .map(i =>
            i.id !== e.taskId
              ? i
              : {
                  ...i,
                  text: e.subject ?? i.text,
                  status: e.status === undefined || e.status === 'deleted' ? i.status : e.status,
                },
          )

        return { ...g, items }
      })
    }

    return ran
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const g = await read($, goal)
    const t = await read($, now)
    const showAll = await read($, isAll)
    const list = await read($, others)
    const width = Math.max(10, Math.min(30, e.props.bodyColumns - 8))

    const toggle = async () => {
      const next = !(await read($, isAll))
      await update($, isAll, () => next)
      if (next) {
        await loadOthers($)
      }
    }

    return (
      <Box flexDirection="column">
        {g === null ? (
          <Text dimColor>No goal yet. Start one with /goal &lt;what to achieve&gt;.</Text>
        ) : (
          <Box flexDirection="column">
            <Text bold>{g.title}</Text>
            <Text dimColor>
              {phaseOf(g)} · {elapsed((g.endedAt ?? Math.max(t, g.startedAt)) - g.startedAt)}
            </Text>
            <Text>
              {bar(percentOf(g), width)} {percentOf(g)}%
            </Text>
            {g.items.map(item => (
              <Text
                color={item.status === 'in_progress' ? 'cyan' : undefined}
                dimColor={item.status === 'completed'}
              >
                {item.status === 'completed' ? '✓' : item.status === 'in_progress' ? '▸' : '○'} {item.text}
              </Text>
            ))}
          </Box>
        )}
        <Text> </Text>
        <Button key="all" label={showAll ? 'Hide other sessions' : 'All Tasks'} onPress={toggle} />
        {showAll && list.length === 0 && <Text dimColor>No goals in other sessions (last 24h).</Text>}
        {showAll &&
          list.map(o => (
            <Text>
              {o.goal.endedAt !== null ? '✓' : '▸'} {percentOf(o.goal)}% {o.goal.title}{' '}
              <Text dimColor>({o.sessionId.slice(0, 8)})</Text>
            </Text>
          ))}
      </Box>
    )
  })
}
