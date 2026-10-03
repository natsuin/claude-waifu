import type { RenderElement } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import type { Snapshot } from '../types'

const SNAP: Snapshot = {
  id: 'claude-grape', color: 'grape', character: 'Yixuan', room: 'sakura', roomColor: '#ffafd1',
  unread: 1, latest: { from: 'claude-sky', text: 'parser done' },
  messages: [
    { ts: 1_790_000_000, from: 'claude-sky', to: null, text: 'starting on the parser', mine: false },
    { ts: 1_790_000_060, from: 'claude-grape', to: 'claude-sky', text: 'I will take the tests', mine: true },
  ],
  members: [
    { id: 'claude-grape', you: true, state: 'working', readUpto: 1_790_000_060, readAll: true, helperOf: null },
    { id: 'claude-sky', you: false, state: 'asking', readUpto: 1_790_000_000, readAll: false, helperOf: null, lead: true },
  ],
  tasks: [
    { id: 't1', title: 'Fix the parser', owner: 'claude-sky', status: 'done' },
    { id: 't2', title: 'Write the tests', owner: 'claude-grape', status: 'doing' },
    { id: 't3', title: 'Port the docs', owner: null, status: 'open' },
  ],
  wake: null,
}

const PANE = {
  plugin: 'tatami', surface: 'terminal', component: 'Pane', requestId: 'tatami-room',
  props: { title: 'sakura', isFocused: true, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
  viewport: { columns: 160, rows: 40 },
} as const

// How the person's Enter runs a command in a fullscreen terminal 160 columns wide.
const TYPED = { origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 160 } } as const

test('/room shows the team and its messages, and posts as the user', async ($, on) => {
  const clock = mock.clock(on)
  mock.env(on, { HOME: '/home/test' })
  const posts: string[] = []
  const opened: string[] = []
  on('process.run', async (_$, e) => {
    const [, , cmd, ...rest] = e.argv
    if (cmd === 'post') {
      posts.push(rest.join(' '))
    }
    const stdout = cmd === 'poll' ? JSON.stringify(SNAP) : cmd === 'post' ? "Posted to room 'sakura'." : '{}'
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('command.register', async (_$, e) => ({ value: { command: e.name } }))
  on('ui.status', async () => ({ value: undefined }))
  on('ui.open', async (_$, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('ui.render', async ($r, e) => {
    const { Text } = $r.ui.resolve(e)
    return h(Text, {}, 'engine') as RenderElement
  })
  await $.session.start({ cwd: '/home/test', surface: 'terminal', isInteractive: true })
  await clock.advance(0)

  const opening = await $.command.run({ ...TYPED, command: 'room', args: '' })
  expect(opening.text).toBe('The sakura pane is open (Esc closes it).')
  expect(opened).toEqual(['tatami-room'])

  const ui = await $.ui.mount(PANE)
  expect(await ui.find({ type: 'Text', text: /● sakura/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /claude-sky orchestrator · needs your OK · read up to/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /claude-grape this window · working · read everything/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /claude-grape → claude-sky: I will take the tests/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Plan · 1 done, 2 left/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /t2 Write the tests · claude-grape · doing/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /t3 Port the docs · no one yet/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /t1 Fix the parser · claude-sky · to land/ })).toBeDefined()

  await $.ui.input({ plugin: 'tatami', key: 'say', text: '@claude-sky please pause' })
  expect(posts).toEqual(['@claude-sky please pause'])
  expect(await ui.find({ type: 'Text', text: /you → claude-sky: please pause/ })).toBeDefined()
  await ui.unmount()

  const direct = await $.command.run({ ...TYPED, command: 'room', args: 'hello all' })
  expect(direct.text).toBe("Posted to room 'sakura'.")
  expect(posts.at(-1)).toBe('hello all')

  const phone = await $.ui.mount({ ...PANE, surface: 'mobile' })
  expect(await phone.find({ type: 'Text', text: /● sakura/ })).toBeDefined()
  await phone.unmount()
})
