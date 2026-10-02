// Room mail above the prompt: while this window's agent has room messages it hasn't read, a line
// says how many and shows the newest. It goes away once the agent calls room_read.
import { atom, read } from 'claude-code'
import type { On } from 'claude-code'

import { line, PANE } from './room'

const snap = atom({ plugin: 'tatami', key: 'snap' } as const, null)

export function band(on: On) {
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = await read($, snap)
    if (e.props.hasSurvey || !s?.room || s.unread === 0) {
      return next(e)
    }
    const { Box, Text, Button } = $.ui.resolve(e)
    const head = ` ${s.room} `
    const count = ` ${s.unread} unread `
    const room = e.props.bodyColumns - head.length - count.length - 12
    const latest = s.latest ? line(`${s.latest.from}: ${s.latest.text}`, room) : ''

    return (
      <Box>
        <Text color={s.roomColor ?? undefined} bold>●{head}</Text>
        <Text>{count}</Text>
        <Text dimColor>{latest} </Text>
        <Button key="open" label="Open" onPress={() => void $.ui.open({ id: PANE, title: s.room ?? 'Room' })} />
      </Box>
    )
  })
}
