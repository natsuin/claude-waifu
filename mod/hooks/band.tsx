// Above the prompt: the "your turn" box once Claude finishes (see turn.tsx), and room mail: while
// this window's agent has room messages it hasn't read, a line says how many and shows the
// newest. The mail line goes away once the agent calls room_read.
import { atom, read } from 'claude-code'
import type { EngineInterface, On, RenderElement, RenderInput } from 'claude-code'

import { PANE } from './pane'
import { line } from './room'
import { SKY } from './turn'

const snap = atom({ plugin: 'tatami', key: 'snap' } as const, null)
const finished = atom({ plugin: 'tatami', key: 'finished' } as const, null)
const beat = atom({ plugin: 'tatami', key: 'beat' } as const, 0)

/** The "your turn" box, its border at this beat's shade; null when there's none to show. */
async function yourTurn($: EngineInterface, e: RenderInput<'AbovePrompt'>): Promise<RenderElement | null> {
  const f = await read($, finished)
  if (f === null) {
    return null
  }
  const { Box, Text } = $.ui.resolve(e)
  const shade = SKY[(await read($, beat)) % SKY.length]

  return (
    <Box borderStyle="round" borderColor={shade} paddingX={1}>
      <Text wrap="truncate-end"><Text color={shade} bold>● Your turn</Text><Text dimColor> · {f.text}</Text></Text>
    </Box>
  )
}

export function band(on: On, glows: boolean) {
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) {
      return next(e)
    }
    const turn = glows ? await yourTurn($, e) : null
    const s = await read($, snap)
    if (!s?.room || s.unread === 0) {
      return turn ? stack($, e, turn, await next(e)) : next(e)
    }
    const { Box, Text, Button } = $.ui.resolve(e)
    const head = ` ${s.room} `
    const count = ` ${s.unread} unread `
    const room = e.props.bodyColumns - head.length - count.length - 12
    const latest = s.latest ? line(`${s.latest.from}: ${s.latest.text}`, room) : ''

    const mail = (
      <Box>
        <Text color={s.roomColor ?? undefined} bold>●{head}</Text>
        <Text>{count}</Text>
        <Text dimColor>{latest} </Text>
        <Button key="open" label="Open" onPress={() => void $.ui.open({ id: PANE, title: s.room ?? 'Room' })} />
      </Box>
    )
    return turn ? stack($, e, turn, mail) : mail
  })
}

function stack($: EngineInterface, e: RenderInput<'AbovePrompt'>, top: RenderElement, below: RenderElement | null) {
  const { Box } = $.ui.resolve(e)
  return (
    <Box flexDirection="column">
      {top}
      {below}
    </Box>
  )
}
