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
  /** the room's orchestrator, picked on the desk */
  lead?: boolean
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

/** The "your turn" box above the prompt, after Claude finishes. */
export type Finished = {
  /** after "Your turn ·": 'Claude finished in 1m 15s' */
  text: string
  /** until when its border breathes (a clock time in ms); then it holds still */
  breatheUntil: number
}

declare module 'claude-code' {
  interface PluginState {
    /**
     * snap: the newest poll; draft: what's typed in the /room pane's line, kept across redraws;
     * finished: the "your turn" box; asking: the tool call waiting for your OK; beat: how far
     * the glows' borders have stepped through their shades
     */
    tatami: { snap: Snapshot | null; draft: string; finished: Finished | null; asking: string; beat: number }
  }
}
