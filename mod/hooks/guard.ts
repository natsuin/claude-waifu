// Keeping a team out of each other's way. On a team (or with a worktree of its own), before
// Claude edits a file the mod asks `tatami mod guard` (tatami/work.py underneath), which refuses
// an edit to a teammate's file and sends an edit in the user's checkout to the agent's own
// worktree, making it the first time; the refusal tells Claude where to make the edit instead.
// Git commands that would change the user's checkout get the same answer. Reading a file in the
// user's checkout is fine, but Claude is reminded that its own copy is in its worktree.
import { atom, read } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import type { Worktree } from '../types'
import { tatamiPath } from './room'

const snap = atom({ plugin: 'tatami', key: 'snap' } as const, null)

/** Asks tatami/work.py; null when the edit may go ahead (or tatami can't say). */
async function refusal($: EngineInterface, ask: object): Promise<string | null> {
  const ran = await $.process.run([tatamiPath(await $.env.get('HOME')), 'mod', 'guard'],
    { stdin: JSON.stringify(ask), timeoutMs: 15_000 })
  if (ran.exitCode !== 0) {
    return null
  }
  try {
    return (JSON.parse(ran.stdout) as { deny?: string }).deny ?? null
  } catch {
    return null
  }
}

/** The user's checkouts this agent has worktrees of, each as written out and with ~. */
function checkouts(trees: readonly Worktree[], home: string | undefined): string[] {
  return trees.flatMap(t => (home && t.main.startsWith(`${home}/`) ? [t.main, `~${t.main.slice(home.length)}`] : [t.main]))
}

/** The worktree whose user's checkout holds `path`, if there is one. */
function treeFor(trees: readonly Worktree[], path: string): Worktree | undefined {
  return trees.find(t => path.startsWith(`${t.main}/`))
}

/** The refusal for an edit to `path`, when its agent is on a team or has a worktree. */
async function checked($: EngineInterface, tool: string, path: string): Promise<string | null> {
  const s = await read($, snap)
  return s?.guarded ? refusal($, { tool, path }) : null // on its own: nothing to keep apart
}

export function guard(on: On) {
  on('tool.call', { tool: 'Edit' }, async ($, e, next) => {
    const deny = await checked($, 'Edit', e.file_path)
    return deny ? { deny } : next(e)
  })

  on('tool.call', { tool: 'Write' }, async ($, e, next) => {
    const deny = await checked($, 'Write', e.file_path)
    return deny ? { deny } : next(e)
  })

  on('tool.call', { tool: 'NotebookEdit' }, async ($, e, next) => {
    const deny = await checked($, 'NotebookEdit', e.notebook_path)
    return deny ? { deny } : next(e)
  })

  // Only a command that names one of the user's checkouts it has a worktree of needs asking about.
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const s = await read($, snap)
    const trees = s?.worktrees ?? []
    if (trees.length === 0 || !checkouts(trees, await $.env.get('HOME')).some(c => e.command.includes(c))) {
      return next(e)
    }
    const deny = await refusal($, { tool: 'Bash', command: e.command })
    return deny ? { deny } : next(e)
  })

  on('tool.call', { tool: 'Read' }, async ($, e, next) => {
    const s = await read($, snap)
    const tree = treeFor(s?.worktrees ?? [], e.file_path)
    const r = await next(e)
    if (!tree || r.deny !== undefined) {
      return r
    }
    const mine = `${tree.path}${e.file_path.slice(tree.main.length)}`
    const note = `Tatami Room: that's the user's checkout, which doesn't have your uncommitted or unlanded work. Your copy is ${mine}.`
    return { ...r, context: [...(r.context ?? []), note] }
  })
}
