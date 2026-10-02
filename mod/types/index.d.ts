// What `tatami mod poll` answers (see tatami/mod.py in the Tatami Room repo).

export type Message = {
  ts: number
  /** an agent id, or "the user" for a line typed in a /room pane */
  from: string
  to: string | null
  text: string
  /** posted by this window's agent */
  mine: boolean
}

export type Member = {
  id: string
  you: boolean
  /** working, done or asking, once the status hooks have seen it */
  state: string | null
  readUpto: number
  readAll: boolean
  helperOf: string | null
}

export type Snapshot = {
  /** this window's agent; null in a session without the Tatami Room channel */
  id: string | null
  color: string | null
  /** who's in the window's picture, from waifu's art credits */
  character: string | null
  /** null while the agent is on its own */
  room: string | null
  roomColor: string | null
  /** room messages the agent hasn't read yet */
  unread: number
  latest: { from: string; text: string } | null
  messages: Message[]
  members: Member[]
  /** a prompt to wake the idle agent with (only with --wake) */
  wake: string | null
}

declare module 'claude-code' {
  interface PluginState {
    tatami: { snap: Snapshot | null }
  }
}
