import { expect, mock, test } from 'claude-code/testing'

import type { Snapshot } from '../types'

const ALONE: Snapshot = {
  id: 'rose', color: 'rouge', character: null, room: null, roomColor: null, unread: 0, latest: null,
  messages: [], members: [], tasks: [], worktrees: [], guarded: false, wake: null,
}
const TEAMED: Snapshot = {
  ...ALONE, room: 'fuji', roomColor: '#d3bdfe', guarded: true,
  worktrees: [{ main: '/home/test/proj', path: '/home/test/.local/share/tatami/worktrees/proj/rose', branch: 'tatami/rose' }],
}
const NO = 'Tatami Room: /home/test/proj/a.txt is the user\'s checkout. You work in your worktree.'

test('edits are checked on a team, and only there', async ($, on) => {
  const clock = mock.clock(on)
  mock.env(on, { HOME: '/home/test' })
  let snap = ALONE
  const asked: object[] = []
  const ran: string[] = []
  on('process.run', async (_$, e) => {
    const [, , cmd] = e.argv
    if (cmd === 'guard') {
      asked.push(JSON.parse(e.init?.stdin ?? '{}') as object)
    }
    const stdout = JSON.stringify(cmd === 'poll' ? snap : cmd === 'guard' ? { deny: NO } : {})
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('command.register', async (_$, e) => ({ value: { command: e.name } }))
  on('ui.status', async () => ({ value: undefined }))
  on('tool.call', async (_$, e) => { // the engine, running the tool
    ran.push(e.tool)
    return { result: 'ran', text: 'ran' }
  })
  await $.session.start({ cwd: '/home/test', surface: 'terminal', isInteractive: true })
  await clock.advance(0)

  // On its own: no asking, the edit runs.
  await $.tool.call({ tool: 'Edit', file_path: '/home/test/proj/a.txt', old_string: 'a', new_string: 'b' })
  expect(asked).toEqual([])
  expect(ran).toEqual(['Edit'])

  // On a team: asked first, and refused with tatami's reason.
  snap = TEAMED
  await clock.advance(4000)
  const edit = await $.tool.call({ tool: 'Write', file_path: '/home/test/proj/a.txt', content: 'x' })
  expect(asked).toEqual([{ tool: 'Write', path: '/home/test/proj/a.txt' }])
  expect(edit.deny).toBe(NO)
  expect(ran).toEqual(['Edit'])

  // Bash only asks when it names the user's checkout (written out, or with ~).
  await $.tool.call({ tool: 'Bash', command: 'ls /tmp' })
  expect(asked.length).toBe(1)
  await $.tool.call({ tool: 'Bash', command: 'cd ~/proj && git commit -am x' })
  expect(asked.at(-1)).toEqual({ tool: 'Bash', command: 'cd ~/proj && git commit -am x' })
})

test('reading the user\'s checkout says where its own copy is', async ($, on) => {
  const clock = mock.clock(on)
  mock.env(on, { HOME: '/home/test' })
  on('process.run', async (_$, e) => {
    const stdout = JSON.stringify(e.argv[2] === 'poll' ? TEAMED : {})
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('command.register', async (_$, e) => ({ value: { command: e.name } }))
  on('ui.status', async () => ({ value: undefined }))
  on('tool.call', async () => ({ result: 'one\ntwo\n', text: 'one\ntwo\n' }))
  await $.session.start({ cwd: '/home/test', surface: 'terminal', isInteractive: true })
  await clock.advance(0)

  const there = await $.tool.call({ tool: 'Read', file_path: '/home/test/proj/src/a.ts' })
  expect(there.context?.at(-1)).toContain('/home/test/.local/share/tatami/worktrees/proj/rose/src/a.ts')
  const elsewhere = await $.tool.call({ tool: 'Read', file_path: '/home/test/other/a.ts' })
  expect(elsewhere.context ?? []).toEqual([])
})
