import { expect, mock, test } from 'claude-code/testing'

const QUIET = { id: 'claude-grape', color: 'grape', character: null, room: 'sakura', roomColor: '#ffafd1',
  unread: 0, latest: null, messages: [], members: [], wake: null }

test('status hooks note the state, pass room mail on, and keep quiet tool calls cheap', async ($, on) => {
  mock.clock(on)
  mock.env(on, { HOME: '/home/test' })
  const events: string[] = []
  let answer = {}
  on('process.run', async (_$, e) => {
    const [, , cmd, ...rest] = e.argv
    if (cmd === 'event') {
      const ev = JSON.parse(e.init?.stdin ?? '{}') as { hook_event_name: string }
      events.push(ev.hook_event_name + (rest.includes('--chime') ? '+chime' : ''))
    }
    const stdout = JSON.stringify(cmd === 'poll' ? QUIET : answer)
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('classic.UserPromptSubmit', async () => ({ additionalContext: ['from another hook'] }))
  on('classic.PostToolUse', async () => ({}))
  on('classic.Stop', async () => ({}))
  on('classic.Notification', async () => ({}))

  answer = { hookSpecificOutput: { additionalContext: 'Tatami Room: 1 new message' } }
  const sent = await $.classic.UserPromptSubmit({ prompt: 'hi', permission_mode: 'default' })
  expect(sent.additionalContext).toEqual(['from another hook', 'Tatami Room: 1 new message'])

  answer = {}
  await $.classic.PostToolUse({ tool_name: 'Bash', tool_input: {}, tool_response: {}, tool_use_id: 't1' })
  expect(events).toEqual(['UserPromptSubmit']) // working already, no mail: no process

  answer = { decision: 'block', reason: 'Tatami Room: 1 message to you' }
  const stop = await $.classic.Stop({ stop_hook_active: false })
  expect(stop.block).toBe('Tatami Room: 1 message to you')

  answer = {}
  await $.classic.Notification({ message: 'Claude needs your permission', notification_type: 'permission_prompt' })
  expect(events).toEqual(['UserPromptSubmit', 'Stop', 'Notification+chime'])

  await $.classic.PostToolUse({ tool_name: 'Bash', tool_input: {}, tool_response: {}, tool_use_id: 't2' })
  expect(events.at(-1)).toBe('PostToolUse') // after a notice, the next tool call notes "working" again
})
