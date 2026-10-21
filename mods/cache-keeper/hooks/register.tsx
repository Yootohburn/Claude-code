import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, Timer } from 'claude-code'

import type { CacheReading } from '../types'

const PANE = 'cache-keeper'
const TTL_MS = 60 * 60 * 1000
const WARN_MS = 5 * 60 * 1000
const TICK_MS = 15 * 1000

const reading = atom({ plugin: 'cache-keeper', key: 'reading' } as const, null)
const handoff = atom(
  { plugin: 'cache-keeper', key: 'handoff' } as const,
  { text: null, isBusy: false },
)

const HANDOFF_ASK = [
  'Write a session handoff so a fresh session can continue this work with no other context.',
  'Cover: the goal, what is done (files, branches, commits), decisions made and why,',
  'open problems, and the exact next steps. Be dense: bullet points, under 400 words.',
  'Reply with the handoff only.',
].join(' ')

const clockText = (ms: number) => {
  const left = Math.max(0, ms)
  const m = Math.floor(left / 60000)
  const s = Math.floor((left % 60000) / 1000)

  return `${m}:${String(s).padStart(2, '0')}`
}

const usd = (n: number) => `$${n.toFixed(n < 1 ? 3 : 2)}`

let warn: Timer | undefined

const measure = async ($: EngineInterface, isFresh: boolean) => {
  const now = await $.clock.now()
  const usage = await $.session.usage()
  const cost = usage.cost?.usd ?? 0
  await update($, reading, prev => {
    const next: CacheReading = {
      lastAt: isFresh || prev === null ? now : prev.lastAt,
      now,
      tokens: usage.context.tokens ?? 0,
      window: usage.context.window,
      costUsd: cost,
      turnCostUsd: isFresh ? cost - (prev?.costUsd ?? 0) : (prev?.turnCostUsd ?? 0),
    }

    return next
  })
}

const arm = ($: EngineInterface) => {
  warn?.cancel()
  warn = $.clock.after(TTL_MS - WARN_MS, () => {
    $.ui.toast('Prompt cache expires in 5 minutes: send a short message to keep it warm.', {
      timeoutMs: 15000,
    })
    void $.ui.notify('Prompt cache expires in 5 minutes.', { title: 'CacheKeeper' })
  })
}

const tick = async ($: EngineInterface) => {
  const r = await read($, reading)
  if (r === null) {
    return
  }
  const now = await $.clock.now()
  await update($, reading, prev => (prev === null ? prev : { ...prev, now }))
  const left = r.lastAt + TTL_MS - now
  $.ui.status(
    left > 0
      ? `cache ${clockText(left)} · ${Math.round(r.tokens / 1000)}k tok`
      : 'cache expired',
  )
}


const makeHandoff = async ($: EngineInterface) => {
  await update($, handoff, h => ({ ...h, isBusy: true }))
  const reply = await $.model.fork({ prompt: HANDOFF_ASK })
  if (!reply.isAnswered) {
    $.ui.toast(`Handoff failed: ${reply.reason}`)
    await update($, handoff, h => ({ ...h, isBusy: false }))

    return
  }
  await $.store.set('handoff', reply.text)
  await update($, handoff, () => ({ text: reply.text, isBusy: false }))
  $.ui.toast('Handoff ready. Press "Clear and Continue" to start fresh with it.')
}

const clearAndContinue = async ($: EngineInterface) => {
  const { text } = await read($, handoff)
  if (text === null) {
    return
  }
  await $.command.run({ command: 'clear' })
  await update($, handoff, () => ({ text: null, isBusy: false }))
  await update($, reading, () => null)
  await $.prompt.submit({
    text: `Continue from this handoff of my previous session:\n\n${text}`,
    asUser: true,
  })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'cachekeeper',
      description: 'Open the CacheKeeper dashboard (cache countdown, tokens, cost, handoff)',
    })
    $.clock.every(TICK_MS, () => void tick($))
    void $.ui.open({ id: PANE, title: 'CacheKeeper' })

    return next(e)
  })

  on('command.run', { command: 'cachekeeper' }, async $ => {
    await $.ui.open({ id: PANE, title: 'CacheKeeper' })

    return { text: 'CacheKeeper opened.' }
  })

  on('prompt.submit', async ($, e, next) => {
    arm($)

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (e.agentId === undefined) {
      await measure($, true)
      arm($)
      await tick($)
    }

    return done
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const r = await read($, reading)
    const h = await read($, handoff)

    const left = r === null ? TTL_MS : r.lastAt + TTL_MS - r.now
    const isWarm = r !== null && left > 0
    const percent = r === null || r.window === 0 ? 0 : Math.round((r.tokens / r.window) * 100)

    return (
      <Box flexDirection="column">
        <Text bold>Prompt cache</Text>
        {r === null ? (
          <Text dimColor>Starts after the first reply (60:00).</Text>
        ) : (
          <Text color={left <= WARN_MS ? 'red' : undefined}>
            {isWarm ? `${clockText(left)} left of 60:00` : 'Expired: next message pays full price'}
          </Text>
        )}
        <Text> </Text>
        <Text bold>Context</Text>
        <Text>
          {r === null
            ? '-'
            : `${r.tokens.toLocaleString('en-US')} / ${r.window.toLocaleString('en-US')} tokens (${percent}%)`}
        </Text>
        {percent >= 60 && <Text color="yellow">Context is getting long: consider a handoff.</Text>}
        <Text> </Text>
        <Text bold>Cost</Text>
        <Text>
          {r === null ? '-' : `last turn ${usd(r.turnCostUsd)} · session ${usd(r.costUsd)}`}
        </Text>
        <Text> </Text>
        <Button
          key="handoff"
          label={h.isBusy ? 'Writing handoff…' : 'Session Handoff'}
          onPress={() => (h.isBusy ? undefined : makeHandoff($))}
        />
        {h.text !== null && (
          <Button
            key="clear"
            variant="primary"
            label="Clear and Continue"
            onPress={() => clearAndContinue($)}
          />
        )}
        {h.text !== null && <Text dimColor>{h.text.slice(0, 600)}</Text>}
      </Box>
    )
  })
}
