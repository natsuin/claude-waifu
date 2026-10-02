import { expect, mock, test } from 'claude-code/testing'

import type { Snapshot } from '../types'

const SNAP: Snapshot = {
  id: 'claude-grape', color: 'grape', character: 'Yixuan', room: 'sakura', roomColor: '#ffafd1',
  unread: 2, latest: { from: 'claude-sky', text: 'found the UTF-8 bug in SendToJS' },
  messages: [], members: [], wake: null,
}

const BAND = {
  plugin: 'tatami', surface: 'terminal', component: 'AbovePrompt',
  props: { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 100, scroll: { offset: 0, bodyRows: 10 }, view: {} },
} as const

test('room mail shows above the prompt until the agent reads it', async ($, on) => {
  const clock = mock.clock(on)
  mock.env(on, { HOME: '/home/test' })
  let snap: Snapshot = SNAP
  const runs: string[][] = []
  on('process.run', async (_$, e) => {
    runs.push([...e.argv])
    return { value: { exitCode: 0, stdout: JSON.stringify(snap), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('ui.render', async ($r, e) => { // stands for the engine's own band
    const { Text } = $r.ui.resolve(e)
    return h(Text, { key: 'engine' }, 'engine')
  })
  await $.session.start({ cwd: '/home/test', surface: 'terminal', isInteractive: true })
  await clock.advance(0)
  expect(runs[0]).toEqual(['/home/test/.local/bin/tatami', 'mod', 'poll'])

  const ui = await $.ui.mount(BAND)
  expect(await ui.find({ type: 'Text', text: /2 unread/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /claude-sky: found the UTF-8 bug/ })).toBeDefined()
  expect(await ui.find({ key: 'open' })).toBeDefined()
  await ui.unmount()

  snap = { ...SNAP, unread: 0, latest: null }
  await clock.advance(4000)
  const quiet = await $.ui.mount(BAND)
  expect(await quiet.find({ type: 'Text', text: /unread/ })).toBeUndefined()
  expect(await quiet.find({ type: 'Text', text: 'engine' })).toBeDefined()
  await quiet.unmount()
})
