// Tatami Room inside Claude Code. Every few seconds the mod asks `tatami mod poll` how this
// window's agent and its room are doing; the parts below draw from that. `tatami mod` runs as a
// child of this Claude process, which is how it finds the window's agent.
import { atom, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Snapshot } from '../types'
import { band } from './band'
import { tatamiPath } from './room'
import { sawMail, status } from './status'

const EVERY_MS = 4000
const snap = atom({ plugin: 'tatami', key: 'snap' } as const, null)

let wake = false // the "Wake on room mail" option
let busy = false // a turn is running: room mail reaches it through the status hooks instead
let polling = false
let last = ''

async function poll($: EngineInterface, withWake: boolean): Promise<Snapshot | null> {
  const ran = await $.process.run([tatamiPath(await $.env.get('HOME')), 'mod', 'poll', ...(withWake ? ['--wake'] : [])],
    { timeoutMs: 10_000 })
  if (ran.exitCode !== 0) {
    return null // tatami isn't installed here
  }
  try {
    return JSON.parse(ran.stdout) as Snapshot
  } catch {
    return null
  }
}

async function tick($: EngineInterface) {
  if (polling) {
    return
  }
  polling = true
  try {
    const s = await poll($, wake && !busy)
    if (!s) {
      return
    }
    sawMail(s.unread)
    const shown = JSON.stringify({ ...s, wake: null })
    if (shown !== last) {
      last = shown
      await update($, snap, () => ({ ...s, wake: null }))
    }
    if (s.wake) {
      void $.prompt.submit({ text: s.wake })
    }
  } finally {
    polling = false
  }
}

export const register: Register = (on, options) => {
  wake = options.wake === true

  on('session.start', async ($, e, next) => {
    void tick($)
    $.clock.every(EVERY_MS, () => void tick($))
    return next(e)
  })

  on('turn.start', ($, e, next) => {
    busy = true
    return next(e)
  })

  on('turn.complete', ($, e, next) => {
    busy = false
    return next(e)
  })

  band(on)
  status(on, options.chime !== false)
}
