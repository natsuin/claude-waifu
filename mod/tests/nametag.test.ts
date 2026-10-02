import { expect, test } from 'claude-code/testing'

import { nameTag } from '../hooks/register'
import type { Snapshot } from '../types'

const BASE: Snapshot = { id: 'claude-teal', color: 'teal', character: null, room: null, roomColor: null,
  unread: 0, latest: null, messages: [], members: [], wake: null }

test('the name tag reads like the desk card', async () => {
  expect(nameTag(BASE)).toBe('claude-teal · on its own')
  expect(nameTag({ ...BASE, character: 'Firefly', room: 'ajisai' })).toBe('claude-teal · Firefly · ajisai')
  expect(nameTag({ ...BASE, character: 'Furina, Nahida, Raiden Shogun, Yae Miko' })).toBe('claude-teal · Furina, Nahida +2 · on its own')
  expect(nameTag({ ...BASE, character: 'Qingming Bird, Yixuan' })).toBe('claude-teal · Qingming Bird, Yixuan · on its own')
  expect(nameTag({ ...BASE, id: null })).toBeUndefined()
})
