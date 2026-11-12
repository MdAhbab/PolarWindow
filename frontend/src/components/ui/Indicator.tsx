import { useLayoutEffect, useRef } from 'react'
import { useReducedMotion } from '../../hooks/useMotion'
import { copyForEye } from '../../lib/motion'

/**
 * Rule 2 of the motion grammar: one thing moves. The chosen item of a row of
 * choices is drawn by ONE pill that slides and resizes from the old choice to
 * the new (tabs, the site tabs, segmented controls, the header navigation, the
 * phone's bottom bar, the theme switch), by transform only.
 *
 * How a row uses it:
 * - the row carries `pw-ind-host` (it is the pill's frame);
 * - each item carries `data-pw-item={key}`, and the chosen one `data-pw-on`;
 * - the chosen item draws no ground of its own (the pill is its ground);
 * - `<Indicator selected={key} />` is the row's last child.
 * A new item (a fourth in the bottom bar) needs only its `data-pw-item`.
 *
 * The pill is the intersection of four boxes, each pinned to one corner of it
 * and moved by `translate` alone, so it is never scaled and its ends stay round
 * at every frame; the ground inside is moved back by as much, so the ink and
 * the copy of the words drawn in it stay over the items. All five move on the
 * same time and curve, so they stay in register through every frame, and
 * through an interruption. An `ink` pill draws a copy of the row's words in the
 * canvas colour over the row (generated content: no word is in the page twice);
 * an `inset` pill sits under the words, which read on both grounds.
 *
 * Under reduced motion the pill is simply where the choice is. A route change
 * slides it too: the shell stays mounted, and during a view transition the new
 * page is shown live.
 */
export function Indicator({
  selected,
  tone = 'ink',
  inset = 0,
  mark,
}: {
  /** The chosen item's `data-pw-item`, or null when none is chosen. */
  selected: string | null
  tone?: 'ink' | 'inset'
  /** How far the pill sits inside its item, px (the clear 4 px border of a segment). */
  inset?: number
  /** A dot that travels with the pill, this many px in from its left edge (the header navigation). */
  mark?: number
}) {
  const reduced = useReducedMotion()
  const root = useRef<HTMLSpanElement>(null)
  const boxes = useRef<(HTMLSpanElement | null)[]>([])
  const fill = useRef<HTMLSpanElement>(null)
  const dot = useRef<HTMLSpanElement>(null)
  // The last place drawn ('' before the first), and each label's place then (for its slide).
  const drawn = useRef('')
  const labels = useRef(new Map<string, number>())
  const state = useRef({ selected, reduced, tone, inset, mark })
  state.current = { selected, reduced, tone, inset, mark }

  /** Draw the pill on the chosen item; `animate` slides it from where it was. */
  const place = (animate: boolean) => {
    // The row is the pill's parent (read here: a parent's own ref is not set yet when its child's layout runs).
    const el = root.current
    const h = el?.parentElement
    const f = fill.current
    if (!h || !el || !f) return
    const { selected: key, tone: t, inset: k, mark: m } = state.current
    const items = [...h.querySelectorAll<HTMLElement>(':scope > [data-pw-item]')]
    const on = key === null ? undefined : items.find((i) => i.dataset.pwItem === key)
    if (!on || on.offsetWidth === 0) {
      el.style.visibility = 'hidden'
      drawn.current = ''
      return
    }
    const W = h.scrollWidth
    const H = h.scrollHeight
    const L = on.offsetLeft + k
    const T = on.offsetTop + k
    const R = on.offsetLeft + on.offsetWidth - k
    const B = on.offsetTop + on.offsetHeight - k
    const at = `${key}:${L},${T},${R},${B},${W},${H}`
    if (at === drawn.current) return
    const first = drawn.current === ''
    const still = !animate || first || state.current.reduced
    drawn.current = at
    const BIG = W + H

    el.toggleAttribute('data-still', still)
    el.style.visibility = ''
    el.style.width = `${W}px`
    el.style.height = `${H}px`
    el.style.setProperty('--pw-ind-r', `${Math.min(R - L, B - T) / 2}px`)
    el.style.setProperty('--pw-ind-ox', `${(L + R) / 2}px`)
    el.style.setProperty('--pw-ind-oy', `${(T + B) / 2}px`)
    const [tl, br, tr, bl] = boxes.current
    const size = (b: HTMLSpanElement | null) => {
      if (!b) return
      b.style.width = `${BIG}px`
      b.style.height = `${BIG}px`
    }
    ;[tl, br, tr, bl].forEach(size)
    // Each box relative to the one holding it (see the comment above).
    if (tl) tl.style.transform = `translate(${L}px, ${T}px)`
    if (br) br.style.transform = `translate(${R - BIG - L}px, ${B - BIG - T}px)`
    if (tr) tr.style.transform = `translate(0px, ${T - B + BIG}px)`
    if (bl) bl.style.transform = `translate(${L - R + BIG}px, ${B - BIG - T}px)`
    f.style.width = `${W}px`
    f.style.height = `${H}px`
    f.style.transform = `translate(${-L}px, ${BIG - B}px)`
    if (dot.current) {
      dot.current.hidden = m === undefined
      dot.current.style.transform = `translate(${m ?? 0}px, ${(B - T) / 2 - 3}px)`
    }

    // The ink pill's words: a copy of the row, in place, drawn in the canvas colour.
    if (t === 'ink') {
      f.replaceChildren(
        ...items.map((i) => {
          const c = copyForEye(i, 'span')
          c.classList.add('pw-ind-copy')
          c.style.left = `${i.offsetLeft}px`
          c.style.top = `${i.offsetTop}px`
          c.style.width = `${i.offsetWidth}px`
          c.style.height = `${i.offsetHeight}px`
          // A button centres its words by itself; the copy is a span, so it is told to.
          const d = getComputedStyle(i).display
          if (i.tagName === 'BUTTON' && !/flex|grid/.test(d)) {
            c.style.display = 'flex'
            c.style.alignItems = 'center'
            c.style.justifyContent = 'center'
          }
          return c
        }),
      )
    }

    // Labels that moved because the chosen item changed size (the dot's room)
    // slide to their new place rather than jump.
    const next = new Map<string, number>()
    for (const i of items) {
      const label = i.querySelector<HTMLElement>('[data-pw-label]')
      if (!label) continue
      const x = i.offsetLeft + label.offsetLeft
      const was = labels.current.get(i.dataset.pwItem ?? '')
      next.set(i.dataset.pwItem ?? '', x)
      if (still || was === undefined || was === x) continue
      label.style.transition = 'none'
      label.style.transform = `translateX(${was - x}px)`
      void label.offsetWidth
      label.style.transition = 'transform var(--pw-dur-base) var(--ease-move)'
      label.style.transform = ''
    }
    labels.current = next

    if (still) {
      void el.offsetWidth
      el.removeAttribute('data-still')
    }
  }
  const placeRef = useRef(place)
  placeRef.current = place

  // A new choice slides the pill (and the keyboard's arrows do the same as a click).
  useLayoutEffect(() => {
    placeRef.current(true)
  }, [selected, tone, inset, mark])

  // A change of size (fonts arriving, the window, a row shown again) puts it in place at once.
  useLayoutEffect(() => {
    const h = root.current?.parentElement
    if (!h || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => placeRef.current(false))
    ro.observe(h)
    h.querySelectorAll(':scope > [data-pw-item]').forEach((i) => ro.observe(i))
    return () => ro.disconnect()
  }, [])

  return (
    <span ref={root} aria-hidden="true" inert className="pw-ind" data-tone={tone} style={{ visibility: 'hidden' }}>
      <span ref={(b) => void (boxes.current[0] = b)} className="pw-ind-box" data-c="tl">
        <span ref={(b) => void (boxes.current[1] = b)} className="pw-ind-box" data-c="br">
          <span ref={(b) => void (boxes.current[2] = b)} className="pw-ind-box" data-c="tr">
            <span ref={(b) => void (boxes.current[3] = b)} className="pw-ind-box" data-c="bl">
              <span ref={fill} className="pw-ind-fill" />
            </span>
          </span>
        </span>
        <span ref={dot} className="pw-ind-mark" hidden />
      </span>
    </span>
  )
}
