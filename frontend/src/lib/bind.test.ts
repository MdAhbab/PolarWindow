// @vitest-environment jsdom
import { createElement, type ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { NBSP, bind } from './format'
import { bindNode } from './bindNode'

const nb = (s: string) => s.replace(/_/g, NBSP)

describe('bind: figures held together', () => {
  it('keeps a number, its margin and its unit on one line', () => {
    expect(bind('422.6 ±0.5 h')).toBe(nb('422.6_±0.5_h'))
    expect(bind('about 12 h over 3 days')).toBe(nb('about 12_h over 3_days'))
    expect(bind('±15 s')).toBe('±15' + NBSP + 's')
    expect(bind('1.8 ±0.4 m against the limit of 2.5 m')).toBe(nb('1.8_±0.4_m against the limit of 2.5_m'))
    expect(bind('88.7 m/s in 99 of 100 runs')).toBe(nb('88.7_m/s in 99 of 100 runs'))
  })

  it('keeps a time with UTC, and a margin with the time it belongs to', () => {
    expect(bind('00:16 UTC ±15 s')).toBe(nb('00:16_UTC_±15_s'))
    expect(bind('at 07:00 UTC.')).toBe(nb('at 07:00_UTC.'))
    expect(bind('17:28:43 UTC')).toBe(nb('17:28:43_UTC'))
  })

  it('keeps a date inside itself but lets a line end between a date and its time', () => {
    expect(bind('(12 Nov 2026 07:00 UTC).')).toBe(nb('(12_Nov_2026 07:00_UTC).'))
    expect(bind('6 March 2025, 17:28 UTC')).toBe(nb('6_March_2025, 17:28_UTC'))
    expect(bind('from 14 Mar 2027')).toBe(nb('from 14_Mar_2027'))
    expect(bind('on 8 Jan')).toBe(nb('on 8_Jan'))
  })

  it('keeps a coordinate with its hemisphere letter', () => {
    expect(bind('near 89.45 S, 137.3 W.')).toBe(nb('near 89.45_S, 137.3_W.'))
    expect(bind('89.4500°S 137.3000°W')).toBe('89.4500°S 137.3000°W')
  })

  it('leaves everything else exactly as it is', () => {
    for (const s of ['A ground station can hear it.', 'Day 12 of 30', '5 of 31 model runs', 'the Sun is up 49% of the time', '', 'IM-2 · Athena']) {
      expect(bind(s)).toBe(s)
    }
  })

  it('changes only spaces: the words, their order and their count are the same', () => {
    const s = 'Over 12 days from 6 Mar 2025, 17:28 UTC it was heard for 159.0 ±0.5 h near 89.45 S, 137.3 W.'
    const b = bind(s)
    expect(b.replace(new RegExp(NBSP, 'g'), ' ')).toBe(s)
    expect(b).not.toBe(s)
  })
})

describe('bindNode: the same, for what is about to be drawn', () => {
  it('binds text at any depth and leaves elements, props and order alone', () => {
    const tree = createElement(
      'p',
      { className: 'x' },
      'It is heard for 159.0 ±0.5 h ',
      createElement('strong', { key: 'b' }, 'on 6 March 2025, 17:28 UTC'),
      ' and then not.',
    ) as ReactElement
    const html = renderToStaticMarkup(bindNode(tree) as ReactElement)
    expect(html).toBe(`<p class="x">It is heard for 159.0${NBSP}±0.5${NBSP}h <strong>on 6${NBSP}March${NBSP}2025, 17:28${NBSP}UTC</strong> and then not.</p>`)
  })

  it('passes numbers, nulls, booleans and render functions through', () => {
    const fn = () => 'x'
    expect(bindNode(3)).toBe(3)
    expect(bindNode(null)).toBeNull()
    expect(bindNode(false)).toBe(false)
    expect(bindNode(fn as unknown as never)).toBe(fn)
    expect(bindNode('plain')).toBe('plain')
  })
})
