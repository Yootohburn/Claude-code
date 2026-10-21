import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

const isOn = atom({ plugin: 'recording-mode', key: 'isOn' } as const, false)

// Each rule swaps what it matches for a placeholder of the same kind.
const RULES: ReadonlyArray<readonly [RegExp, string]> = [
  // Private keys, then tokens with a known prefix
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g, '[private key]'],
  [/\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}\b/g, '[api key]'],
  [/\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}\b/g, '[token]'],
  [/\bxox[abposr]-[A-Za-z0-9-]{10,}\b/g, '[token]'],
  [/\bAKIA[0-9A-Z]{16}\b/g, '[aws key]'],
  [/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g, '[jwt]'],
  // key=value secrets
  [
    /\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)(["']?\s*[:=]\s*["']?)[^\s"',;]{4,}/gi,
    '$1$2••••••',
  ],
  // Emails
  [/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, '•••@•••.•••'],
  // Money: $29, US$ 1,200.50, ฿500, €9, 29 ดอลลาร์, 500 บาท, 29 USD
  [/(?:US\$|[$€£¥฿])\s?\d[\d,]*(?:\.\d+)?/g, '$••'],
  [/\b\d[\d,]*(?:\.\d+)?\s?(?:ดอลลาร์|บาท|USD|THB|EUR|GBP|dollars?)\b/gi, '•• $$'],
  // Card numbers and long digit runs (account ids, phone numbers)
  [/\b(?:\d[ -]?){13,19}\b/g, '•••• •••• •••• ••••'],
  [/(?:\+?\d{1,3}[ -]?)?\(?\d{2,4}\)?[ -]\d{3,4}[ -]\d{3,4}\b/g, '••• ••• ••••'],
]

export const mask = (text: string): string =>
  RULES.reduce((out, [pattern, swap]) => out.replace(pattern, swap), text)

const maskDeep = (value: unknown): unknown => {
  if (typeof value === 'string') {
    return mask(value)
  }
  if (Array.isArray(value)) {
    return value.map(maskDeep)
  }
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, maskDeep(v)]))
  }

  return value
}

const setOn = async ($: EngineInterface, value: boolean) => {
  await update($, isOn, () => value)
  await $.store.set('isOn', value)
  $.ui.status(value ? '● REC: sensitive text masked' : undefined)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'record',
      description: 'Recording Mode: mask emails, money, keys and tokens on screen',
      argumentHint: 'on | off',
    })
    if ((await $.store.get('isOn')) === true) {
      await setOn($, true)
    }

    return next(e)
  })

  on('command.run', { command: 'record' }, async ($, e) => {
    const arg = e.args.trim().toLowerCase()
    const value = arg === 'off' ? false : arg === 'on' || arg === '' ? true : null
    if (value === null) {
      return { text: 'Usage: /record on | /record off' }
    }
    await setOn($, value)

    return {
      text: value
        ? 'Recording Mode ON: emails, amounts, keys and tokens show as placeholders. Files and tools still get the real values.'
        : 'Recording Mode OFF: real values are shown again.',
    }
  })

  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) =>
    (await read($, isOn)) ? next({ ...e, props: { ...e.props, text: mask(e.props.text) } }) : next(e),
  )

  on('ui.render', { component: 'UserMessage' }, async ($, e, next) =>
    (await read($, isOn)) ? next({ ...e, props: { ...e.props, text: mask(e.props.text) } }) : next(e),
  )

  on('ui.render', { component: 'CommandOutput' }, async ($, e, next) =>
    (await read($, isOn)) ? next({ ...e, props: { ...e.props, text: mask(e.props.text) } }) : next(e),
  )

  on('ui.render', { component: 'ToolUse' }, async ($, e, next) =>
    (await read($, isOn))
      ? next({
          ...e,
          props: {
            ...e.props,
            input: maskDeep(e.props.input),
            ...(e.props.output === undefined ? {} : { output: maskDeep(e.props.output) }),
          },
        })
      : next(e),
  )

  on('ui.render', { component: 'ToolResult' }, async ($, e, next) =>
    (await read($, isOn))
      ? next({ ...e, props: { ...e.props, output: maskDeep(e.props.output) } })
      : next(e),
  )
}
