// Small things every part of the mod shares. The window's Tatami Room state is the atom
// tatami.snap, which register.tsx keeps fresh from `tatami mod poll` (tatami/mod.py); each file
// that reads it declares it itself, as the plugin scanner wants.
export const PANE = 'tatami-room'

/** `tatami` through its link, so moving the repo can't break the mod. */
export const tatamiPath = (home: string | undefined) => `${home ?? ''}/.local/bin/tatami`

/** One line of text, at most `width` cells (close enough: room text is mostly narrow). */
export function line(text: string, width: number): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length <= width ? flat : `${flat.slice(0, Math.max(0, width - 1))}…`
}
