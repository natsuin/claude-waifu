// The /room pane: the window's team (who's working, who needs you, how far each has read), the
// room's plan (each task, its owner and how far it has got) and the room's messages, with a line
// at the bottom to post to the room as yourself. `/room hello` posts without opening it; "@dusk
// hello" sends a message to one agent.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import type { Member, Message, Snapshot, Task } from '../types'
import { line, tatamiPath } from './room'

/** The pane's id (the band's Open button opens it too). */
export const PANE = 'tatami-room'

const snap = atom({ plugin: 'tatami', key: 'snap' } as const, null)
const draft = atom({ plugin: 'tatami', key: 'draft' } as const, '')

const STATE: Record<string, string> = { working: 'working', done: 'idle, waiting for you', asking: 'needs your OK' }

/** Posts as the user through `tatami mod post`; answers what to show (an error starts with !). */
async function post($: EngineInterface, text: string): Promise<string> {
  const ran = await $.process.run([tatamiPath(await $.env.get('HOME')), 'mod', 'post', text], { timeoutMs: 10_000 })
  if (ran.exitCode !== 0) {
    return `! ${(ran.stderr || ran.stdout).trim() || 'tatami mod post failed'}`
  }
  // Show it now rather than at the next poll.
  const to = text.startsWith('@') && text.includes(' ') ? text.slice(1, text.indexOf(' ')) : null
  const said = to ? text.slice(text.indexOf(' ') + 1).trim() : text.trim()
  const mine: Message = { ts: Date.now() / 1000, from: 'the user', to, text: said, mine: false }
  await update($, snap, s => (s ? { ...s, messages: [...s.messages, mine] } : s))
  return ran.stdout.trim()
}

const PLAN_ROWS = 6 // tasks the pane shows; the rest are counted
const MARK: Record<string, string> = { open: '○', doing: '◐', blocked: '■', done: '●' }

/** 'rose', 'no one yet', or 'a helper' while the helper it went to starts. */
function owner(t: Task): string {
  return !t.owner ? 'no one yet' : t.owner.startsWith('invite:') ? 'a helper' : t.owner
}

/** What's left first (blocked, doing, open), then what's done and waiting to land. */
function planned(tasks: readonly Task[]): Task[] {
  const order = ['blocked', 'doing', 'open', 'done']
  return [...tasks].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status))
}

function hhmm(ts: number): string {
  const d = new Date(ts * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function who(m: Member, s: Snapshot): string {
  const bits = [m.you ? 'this window' : '', m.lead ? 'orchestrator' : '', m.state ? STATE[m.state] ?? m.state : '',
    m.helperOf ? `helper of ${m.helperOf}` : '',
    s.messages.length === 0 ? '' : m.readAll ? 'read everything' : m.readUpto ? `read up to ${hhmm(m.readUpto)}` : 'hasn’t read the room']
  return bits.filter(Boolean).join(' · ')
}

/** The newest messages that fit in `rows`, oldest first, each wrapped to `width`. */
function fitting(msgs: readonly Message[], width: number, rows: number): Message[] {
  const out: Message[] = []
  let used = 0
  for (const m of [...msgs].reverse()) {
    const head = `${hhmm(m.ts)} ${m.from}${m.to ? ` → ${m.to}` : ''}: `
    const need = Math.max(1, Math.ceil((head.length + m.text.length) / Math.max(10, width)))
    if (used + need > rows && out.length > 0) {
      break
    }
    out.unshift(m)
    used += need
  }
  return out
}

/** The /room command, registered in register.tsx's session.start. */
export const ROOM_COMMAND = {
  name: 'room',
  description: 'Tatami Room: your team and its messages, and a line to post as you',
  argumentHint: '[@agent] [message]',
}

export function pane(on: On) {
  on('command.run', { command: 'room' }, async ($, e) => {
    const args = (e.args ?? '').trim()
    if (args) {
      const said = await post($, args)
      return said.startsWith('! ') ? { text: said.slice(2), exitCode: 1 } : { text: said }
    }
    const s = await read($, snap)
    await $.ui.open({ id: PANE, title: s?.room ?? 'Tatami Room', focus: true, closeOnEscape: true })
    return { text: s?.room ? `The ${s.room} pane is open (Esc closes it).` : 'The Tatami Room pane is open (Esc closes it).' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const s = await read($, snap)
    const width = e.props.bodyColumns
    if (!s?.id) {
      return <Text dimColor>This window has no Tatami Room channel (is `tatami` installed and registered?).</Text>
    }
    if (!s.room) {
      return (
        <Box flexDirection="column">
          <Text bold>{s.id} is on its own</Text>
          <Text dimColor>Drag its card onto another agent's on the Tatami Room desk to team them up.</Text>
        </Box>
      )
    }
    const tasks = planned(s.tasks ?? [])
    const plan = tasks.slice(0, PLAN_ROWS)
    const planRows = tasks.length === 0 ? 0 : plan.length + 1 + (tasks.length > plan.length ? 1 : 0)
    const rows = (e.viewport?.rows ?? 24) - s.members.length - planRows - 7
    const shown = fitting(s.messages, width, Math.max(3, rows))
    const Say = e.surface === 'mobile' ? null : (() => {
      const { Input } = $.ui.resolve(e)
      return Input
    })()
    const typed = await read($, draft)

    return (
      <Box flexDirection="column">
        <Text>
          <Text color={s.roomColor ?? undefined} bold>● {s.room}</Text>
          <Text dimColor> · {s.members.length} here</Text>
        </Text>
        {s.members.map(m => (
          <Text key={`m-${m.id}`} wrap="truncate-end">
            {'  '}{m.id}<Text dimColor>{' '}{who(m, s)}</Text>
          </Text>
        ))}
        {plan.length > 0 && (
          <Text key="plan-head">
            <Text bold>Plan</Text>
            <Text dimColor> · {tasks.filter(t => t.status === 'done').length} done, {tasks.filter(t => t.status !== 'done').length} left</Text>
          </Text>
        )}
        {plan.map(t => (
          <Text key={`p-${t.id}`} wrap="truncate-end">
            {'  '}<Text color={t.status === 'blocked' ? 'red' : t.status === 'done' ? s.roomColor ?? undefined : undefined}>{MARK[t.status] ?? '·'}</Text>
            {' '}<Text dimColor>{t.id}</Text> {t.title}<Text dimColor> · {owner(t)}{t.status === 'done' ? ' · to land' : t.status === 'open' ? '' : ` · ${t.status}`}</Text>
          </Text>
        ))}
        {tasks.length > plan.length && <Text dimColor>{'  '}+{tasks.length - plan.length} more (room_task list)</Text>}
        <Text dimColor>{'─'.repeat(Math.max(1, width))}</Text>
        {shown.length === 0 && <Text dimColor>No messages yet.</Text>}
        {shown.map(m => (
          <Text key={`t-${m.ts}`} wrap="wrap">
            <Text dimColor>{hhmm(m.ts)} </Text>
            <Text bold color={m.from === 'the user' ? s.roomColor ?? undefined : undefined}>{m.from === 'the user' ? 'you' : m.from}</Text>
            <Text dimColor>{m.to ? ` → ${m.to}` : ''}: </Text>
            {line(m.text, 4000)}
          </Text>
        ))}
        {Say && <Say
          key="say"
          label="you: "
          placeholder="message the room (@agent to send it to one)"
          submitLabel="post"
          value={typed}
          autoFocus
          onInput={(value: string) => void update($, draft, () => value)}
          onSubmit={async (value: string) => {
            if (!value.trim()) {
              return
            }
            await update($, draft, () => '')
            const said = await post($, value.trim())
            if (said.startsWith('! ')) {
              $.ui.toast(said.slice(2))
            }
          }}
        />}
      </Box>
    )
  })
}
