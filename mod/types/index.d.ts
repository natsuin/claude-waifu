// What `tatami mod poll` answers (see tatami/mod.py in the Tatami Room repo).

export type Message = {
  ts: number
  /** an agent id, or "the user" for a line typed in a /room pane */
  from: string
  to: string | null
  text: string
  /** posted by this window's agent */
  mine: boolean
  /** the sender's window colour, light, as a hex; null for the user and an earlier agent */
  color: string | null
  /** the same for who it was to */
  toColor: string | null
  /** said by the room's orchestrator */
  lead: boolean
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
  /** its window colour, light, as a hex (null for one the desk doesn't know) */
  color?: string | null
}

/** A task on the room's plan (see tatami/work.py). */
export type Task = {
  id: string
  title: string
  /** an agent id, "invite:<token>" while a helper starts, or null */
  owner: string | null
  /** open, doing, blocked or done (landed ones aren't sent) */
  status: string
}

/** One of this window's agent's own worktrees. */
export type Worktree = {
  /** the user's checkout of the repository */
  main: string
  path: string
  branch: string
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
  /** the room's plan, less what has landed */
  tasks?: Task[]
  worktrees?: Worktree[]
  /** on a team or with a worktree: its edits are checked before they run */
  guarded?: boolean
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
