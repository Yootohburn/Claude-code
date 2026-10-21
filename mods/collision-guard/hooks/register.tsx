import type { EngineInterface, Register, ToolCallResult } from 'claude-code'

// Every session writes the files it edited to its own ledger, so no two
// processes ever write the same file: <HOME>/.claude/mods-shared/collision-guard/<session>.json
type Ledger = { sessionId: string; cwd: string; edits: Record<string, number> }

const WINDOW_MS = 30 * 60 * 1000
const PROCEED = 'Proceed'
const WORKTREE = 'Move to a worktree'
const CANCEL = 'Cancel'

const ledgerDir = async ($: EngineInterface) =>
  `${(await $.env.get('HOME')) ?? '/tmp'}/.claude/mods-shared/collision-guard`

const parse = (text: string): Ledger | null => {
  try {
    return JSON.parse(text) as Ledger
  } catch {
    return null
  }
}

const absolute = async ($: EngineInterface, path: string) => {
  const stat = await $.fs.stat(path, { resolve: true }).catch(() => undefined)
  if (stat?.realPath !== undefined) {
    return stat.realPath
  }

  return path.startsWith('/') ? path : `${await $.session.cwd()}/${path}`
}

const lastEditElsewhere = async ($: EngineInterface, path: string) => {
  const dir = await ledgerDir($)
  const own = `${await $.session.id()}.json`
  const now = await $.clock.now()
  const entries = await $.fs.list(dir).catch(() => [])
  let latest: { at: number; cwd: string } | undefined
  for (const entry of entries) {
    if (entry.kind !== 'file' || entry.name === own || now - entry.mtimeMs > WINDOW_MS) {
      continue
    }
    const ledger = parse(await $.fs.read(`${dir}/${entry.name}`).catch(() => ''))
    const at = ledger?.edits[path]
    if (ledger !== null && at !== undefined && now - at < WINDOW_MS && (latest === undefined || at > latest.at)) {
      latest = { at, cwd: ledger.cwd }
    }
  }

  return latest === undefined ? undefined : { minutes: Math.max(0, Math.round((now - latest.at) / 60000)), cwd: latest.cwd }
}

const remember = async ($: EngineInterface, path: string) => {
  const dir = await ledgerDir($)
  const sessionId = await $.session.id()
  const file = `${dir}/${sessionId}.json`
  const now = await $.clock.now()
  const ledger = parse(await $.fs.read(file).catch(() => '')) ?? {
    sessionId,
    cwd: await $.session.cwd(),
    edits: {},
  }
  const edits = Object.fromEntries(
    Object.entries(ledger.edits).filter(([, at]) => now - at < WINDOW_MS),
  )
  edits[path] = now
  await $.fs.write(file, JSON.stringify({ ...ledger, edits }))
}

// Resolves the path and, when another session edited it lately, asks the
// person; `deny` is set when the edit should not run.
const check = async ($: EngineInterface, target: string) => {
  const path = await absolute($, target)
  const hit = await lastEditElsewhere($, path)
  if (hit === undefined) {
    return { path }
  }
  const ago = hit.minutes === 0 ? 'less than a minute ago' : `${hit.minutes} min ago`
  const answer = await $.ui
    .ask(`${path} was edited by another Claude session ${ago}. Edit it anyway?`, {
      header: 'Collision',
      options: [PROCEED, WORKTREE, CANCEL],
    })
    .catch(() => CANCEL)

  if (answer === PROCEED) {
    return { path }
  }

  return {
    path,
    deny:
      answer === WORKTREE
        ? `Collision Guard: another session edited ${path} ${ago}. The user chose to move to a worktree: call EnterWorktree, then redo this change there.`
        : `Collision Guard: another session edited ${path} ${ago}, and the user cancelled this edit. Ask the user how to continue.`,
  }
}

const recordIfRan = async <R extends ToolCallResult>($: EngineInterface, path: string, ran: R) => {
  if (ran.deny === undefined && ran.isError !== true) {
    await remember($, path).catch(() => undefined)
  }

  return ran
}

export const register: Register = on => {
  on('tool.call', { tool: 'Edit' }, async ($, e, next) => {
    const { path, deny } = await check($, e.file_path)

    return deny !== undefined ? { deny } : recordIfRan($, path, await next(e))
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: 'Write' }, async ($, e, next) => {
    const { path, deny } = await check($, e.file_path)

    return deny !== undefined ? { deny } : recordIfRan($, path, await next(e))
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: 'NotebookEdit' }, async ($, e, next) => {
    const { path, deny } = await check($, e.notebook_path)

    return deny !== undefined ? { deny } : recordIfRan($, path, await next(e))
  }).catch(($, e, next) => next(e))
}
