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
/** The rows the pane asks for when it opens: as many as the layout spares, and it shrinks to
 * what's in it. Left to a third of the screen it scrolls, and the team goes off the top. */
export const PANE_ROWS = 60
/** What a screen keeps besides a pane above the prompt (as claude-duo measured it, with slack). */
const PROMPT_ROWS = 15

const snap = atom({ plugin: 'tatami', key: 'snap' } as const, null)
const draft = atom({ plugin: 'tatami', key: 'draft' } as const, '')

const STATE: Record<string, string> = { working: 'working', done: 'idle, waiting for you', asking: 'needs your OK' }
/** The orchestrator's gold, as on the desk (its --kin). */
const GOLD = '#f5d891'

/** Posts as the user through `tatami mod post`; answers what to show (an error starts with !). */
async function post($: EngineInterface, text: string): Promise<string> {
  const ran = await $.process.run([tatamiPath(await $.env.get('HOME')), 'mod', 'post', text], { timeoutMs: 10_000 })
  if (ran.exitCode !== 0) {
    return `! ${(ran.stderr || ran.stdout).trim() || 'tatami mod post failed'}`
  }
  // Show it now rather than at the next poll.
  const to = text.startsWith('@') && text.includes(' ') ? text.slice(1, text.indexOf(' ')) : null
  const said = to ? text.slice(text.indexOf(' ') + 1).trim() : text.trim()
  const mine: Message = { ts: Date.now() / 1000, from: 'the user', to, text: said, mine: false, color: null,
    toColor: null, lead: false }
  await update($, snap, s => (s ? { ...s, messages: [...s.messages, mine] } : s))
  return ran.stdout.trim()
}

/** Each message's rail in its sender's colour, and the gap after it. */
const RAIL = 2
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

/** The orchestrator first, then the rest as they came. */
function seated(members: readonly Member[]): Member[] {
  return [...members].sort((a, b) => Number(!!b.lead) - Number(!!a.lead))
}

/** What a member is up to, after its name (and the orchestrator's gold "orchestrator"). */
function who(m: Member, s: Snapshot): string {
  const bits = [m.you ? 'this window' : '', m.state ? STATE[m.state] ?? m.state : '',
    m.helperOf ? `helper of ${m.helperOf}` : '',
    s.messages.length === 0 ? '' : m.readAll ? 'read everything' : m.readUpto ? `read up to ${hhmm(m.readUpto)}` : 'hasn’t read the room']
  return bits.filter(Boolean).join(' · ')
}

/** How many lines `text` takes wrapped at word breaks to `width`. */
function wrapped(text: string, width: number): number {
  let lines = 1
  let at = 0
  for (const word of text.split(' ')) {
    const need = (at > 0 ? 1 : 0) + word.length
    if (at > 0 && at + need > width) {
      lines += 1
      at = word.length
    } else {
      at += need
    }
    while (at > width) { // a word longer than the line breaks where it must
      lines += 1
      at -= width
    }
  }
  return lines
}

/** The lines a message takes in a pane `width` wide, beside its rail; its text cut to `chars`. */
function lines(m: Message, width: number, chars = 4000): number {
  const head = `${hhmm(m.ts)} ${m.lead ? '★ ' : ''}${m.from}${m.to ? ` → ${m.to}` : ''}: `
  return wrapped(head + line(m.text, chars), Math.max(10, width - RAIL))
}

/** The newest messages that fit in `rows`, oldest first. The newest always shows, its text cut
 * to fit if it must. */
function fitting(msgs: readonly Message[], width: number, rows: number): Message[] {
  const out: Message[] = []
  let used = 0
  for (const m of [...msgs].reverse()) {
    const need = lines(m, width)
    if (out.length === 0 && need > rows) {
      let chars = m.text.length
      while (chars > 1 && lines(m, width, chars) > rows) {
        chars = Math.floor(chars * 0.9)
      }
      return [{ ...m, text: line(m.text, chars) }]
    }
    if (used + need > rows) {
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
    await $.ui.open({ id: PANE, title: s?.room ?? 'Tatami Room', focus: true, closeOnEscape: true, rows: PANE_ROWS })
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
    // Above the prompt the pane shrinks to what's in it, so its body rows aren't what it could
    // have: the screen less what the prompt keeps is. The room line, the rule, the line to post
    // and the newest message always show; then the team (else it folds into the room line), then
    // the plan (else just its count), as they fit; older messages get the rest, less one spare.
    const inline = e.props.placement === 'inline' && e.viewport !== undefined
    const room = inline ? Math.max(e.props.scroll.bodyRows, (e.viewport?.rows ?? 0) - PROMPT_ROWS) : e.props.scroll.bodyRows
    const newest = s.messages.at(-1)
    const first = Math.max(1, Math.min(newest ? lines(newest, width) : 1, room - 3))
    let left = room - 3 - first
    const team = left >= s.members.length
    left -= team ? s.members.length : 0
    const tasks = planned(s.tasks ?? [])
    const listed = tasks.slice(0, PLAN_ROWS)
    const planRows = listed.length + 1 + (tasks.length > listed.length ? 1 : 0)
    const plan = tasks.length > 0 && left >= planRows ? listed : []
    const planHead = tasks.length > 0 && (plan.length > 0 || left > 0)
    left -= plan.length > 0 ? planRows : planHead ? 1 : 0
    const shown = fitting(s.messages, width, first + Math.max(0, left - 1))
    const Say = e.surface === 'mobile' ? null : (() => {
      const { Input } = $.ui.resolve(e)
      return Input
    })()
    const typed = await read($, draft)

    return (
      <Box flexDirection="column">
        <Text wrap="truncate-end">
          <Text color={s.roomColor ?? undefined} bold>● {s.room}</Text>
          <Text dimColor> · {s.members.length} here</Text>
          {!team && seated(s.members).map(m => (
            <Text key={`f-${m.id}`}>
              <Text dimColor> · </Text>
              {m.lead && <Text color={GOLD}>★ </Text>}
              <Text bold color={m.color ?? undefined}>{m.id}</Text>
            </Text>
          ))}
        </Text>
        {team && seated(s.members).map(m => (
          <Text key={`m-${m.id}`} wrap="truncate-end">
            {'  '}<Text color={m.lead ? GOLD : m.color ?? undefined}>{m.lead ? '★' : '▌'}</Text>
            {' '}<Text bold color={m.color ?? undefined}>{m.id}</Text>
            {m.lead && <Text color={GOLD}> orchestrator</Text>}
            <Text dimColor>{m.lead && who(m, s) ? ' · ' : ' '}{who(m, s)}</Text>
          </Text>
        ))}
        {planHead && (
          <Text key="plan-head" wrap="truncate-end">
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
        {plan.length > 0 && tasks.length > plan.length && <Text dimColor>{'  '}+{tasks.length - plan.length} more (room_task list)</Text>}
        <Text dimColor>{'─'.repeat(Math.max(1, width))}</Text>
        {shown.length === 0 && <Text dimColor>No messages yet.</Text>}
        {shown.map(m => {
          // Each sender in its window's colour, you in the room's; an earlier agent with a live
          // one's name ("rouge (earlier)") has no colour, so it isn't taken for the one here now.
          const user = m.from === 'the user'
          const ink = (user ? s.roomColor : m.color) ?? undefined
          return (
            <Box key={`t-${m.ts}`} flexDirection="row">
              <Box width={1} flexShrink={0} backgroundColor={ink} />
              <Box flexGrow={1} flexShrink={1} paddingLeft={RAIL - 1}>
                <Text wrap="wrap">
                  <Text dimColor>{hhmm(m.ts)} </Text>
                  {m.lead && <Text color={GOLD}>★ </Text>}
                  <Text bold={!!ink} dimColor={!ink} color={ink}>{user ? 'you' : m.from}</Text>
                  {m.to && <Text dimColor> → </Text>}
                  {m.to && <Text dimColor={!m.toColor} color={m.toColor ?? undefined}>{m.to}</Text>}
                  <Text dimColor>: </Text>
                  {line(m.text, 4000)}
                </Text>
              </Box>
            </Box>
          )
        })}
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
