import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

const steps = atom({ plugin: 'next-steps', key: 'steps' } as const, [])
const isThinking = atom({ plugin: 'next-steps', key: 'isThinking' } as const, false)

const ASK = [
  'Looking at this conversation so far, suggest exactly 3 concrete next actions',
  'the user could ask you to do now (fix a bug, merge, test, clean up, ship...).',
  'Each one is an instruction to you, at most 10 words, in the language the user writes in.',
  'Reply with the 3 lines only: no numbering, bullets, or other text.',
].join(' ')

const toSteps = (text: string): string[] =>
  text
    .split('\n')
    .map(line => line.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, '').trim())
    .filter(line => line.length > 0)
    .slice(0, 3)

const suggest = async ($: EngineInterface) => {
  await update($, isThinking, () => true)
  const reply = await $.model.fork({ prompt: ASK })
  await update($, isThinking, () => false)
  await update($, steps, () => (reply.isAnswered ? toSteps(reply.text) : []))
}

export const register: Register = on => {
  on('prompt.submit', async ($, e, next) => {
    await update($, steps, () => [])

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)

    if (e.agentId === undefined && e.reason === 'answer') {
      $.clock.after(0, () => void suggest($))
    }

    return done
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const list = await read($, steps)
    const thinking = await read($, isThinking)

    if (e.props.hasSurvey || e.props.isWorking || (list.length === 0 && !thinking)) {
      return next(e)
    }

    const { Box, Button, Text } = $.ui.resolve(e)

    if (list.length === 0) {
      return (
        <Box>
          <Text dimColor>Next steps: thinking…</Text>
        </Box>
      )
    }

    const run = async (step: string) => {
      await update($, steps, () => [])
      await $.prompt.submit({ text: step, asUser: true })
    }

    return (
      <Box flexDirection="column">
        <Text dimColor>Next steps</Text>
        {list.map((step, i) => (
          <Button
            key={`step-${i}`}
            plain
            hotkey={String(i + 1)}
            label={step}
            onPress={() => run(step)}
          />
        ))}
        <Button
          key="dismiss"
          role="dismiss"
          label="Dismiss"
          onPress={() => update($, steps, () => [])}
        />
      </Box>
    )
  })
}
