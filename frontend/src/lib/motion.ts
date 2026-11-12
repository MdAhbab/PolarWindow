import { useLayoutEffect, useRef, type RefObject } from 'react'
import { useReducedMotion } from '../hooks/useMotion'

/**
 * The motion grammar's helpers (docs/design-visual-refresh.md, "Motion grammar").
 * The timings themselves live in globals.css; nothing here names a duration.
 */

/** A duration token from globals.css, in milliseconds (`fallback` where there is no layout, as in jsdom). */
export function durationMs(token: string, fallback: number): number {
  if (typeof document === 'undefined' || typeof getComputedStyle === 'undefined') return fallback
  const raw = getComputedStyle(document.documentElement).getPropertyValue(token).trim()
  const v = parseFloat(raw)
  if (!Number.isFinite(v) || v <= 0) return fallback
  return raw.endsWith('ms') ? v : raw.endsWith('s') ? v * 1000 : v
}

const STRIP = /^(id|role|href|tabindex|title|name|for|type|disabled|popover|aria-.*|data-(testid|guide|pw-item|pw-on|pw-label))$/

/**
 * A copy of an element for the eye only: no ids, roles, links, names or focus,
 * and its words turned into generated content (`.pw-ind-t`), so a search for
 * a word, a screen reader and a test all find the original alone.
 */
export function copyForEye(el: HTMLElement, tag?: string): HTMLElement {
  const deep = el.cloneNode(true) as HTMLElement
  let c = deep
  if (tag && deep.tagName.toLowerCase() !== tag) {
    c = document.createElement(tag)
    for (const a of [...deep.attributes]) c.setAttribute(a.name, a.value)
    c.append(...deep.childNodes)
  }
  const strip = (n: Element) => {
    for (const a of [...n.attributes]) if (STRIP.test(a.name)) n.removeAttribute(a.name)
  }
  strip(c)
  c.querySelectorAll('*').forEach(strip)
  const walker = document.createTreeWalker(c, NodeFilter.SHOW_TEXT)
  const texts: Text[] = []
  while (walker.nextNode()) texts.push(walker.currentNode as Text)
  for (const t of texts) {
    if (!t.data.trim()) continue
    const s = document.createElement('span')
    s.className = 'pw-ind-t'
    s.dataset.t = t.data
    t.replaceWith(s)
  }
  c.setAttribute('aria-hidden', 'true')
  c.setAttribute('inert', '')
  return c
}

/**
 * Leave a copy of `el` where it was, playing `cls` (a leaving animation), and
 * remove the copy when it ends. The element itself goes at once, so the page's
 * state, its accessibility tree and its tests see it gone at once; the eye sees
 * it leave, in half the time it took to come (rule 1). Nothing under reduced
 * motion, nothing without layout (jsdom).
 */
export function leave(el: HTMLElement | null, cls: string, reduced: boolean): void {
  if (!el || reduced || !el.isConnected || typeof el.getAnimations !== 'function') return
  const parent = el.parentNode
  if (!parent) return
  const ghost = prepare(el, cls)
  parent.insertBefore(ghost, el.nextSibling)
  play(ghost, el)
}

function prepare(el: HTMLElement, cls: string): HTMLElement {
  const ghost = copyForEye(el)
  ghost.classList.remove('pw-pop', 'pw-dock-in', 'pw-toast-in', 'pw-sheet-in')
  ghost.classList.add(cls)
  ghost.style.pointerEvents = 'none'
  if (el.hasAttribute('popover')) ghost.setAttribute('popover', 'manual')
  return ghost
}

function play(ghost: HTMLElement, from: HTMLElement) {
  try {
    if (ghost.hasAttribute('popover') && from.matches(':popover-open')) ghost.showPopover()
  } catch {
    // Without the top layer it is drawn where it is.
  }
  let gone = false
  const done = () => {
    if (gone) return
    gone = true
    ghost.remove()
  }
  ghost.addEventListener('animationend', done, { once: true })
  // A hidden tab runs no animation: the copy goes anyway.
  window.setTimeout(done, durationMs('--pw-dur-sheet-out', 210) + 120)
}

/**
 * The same for an element that unmounts with its component (the Ask dock, a
 * toast): the copy is made as the component goes, and placed only if the
 * element really left the page (React's strict mode unmounts and remounts
 * once in development without removing anything).
 */
export function useLeaveCopy(ref: RefObject<HTMLElement | null>, cls: string): void {
  const reduced = useReducedMotion()
  const r = useRef(reduced)
  r.current = reduced
  useLayoutEffect(() => {
    const el = ref.current
    return () => {
      if (!el || r.current || typeof el.getAnimations !== 'function') return
      const parent = el.parentNode
      if (!parent) return
      const next = el.nextSibling
      const ghost = prepare(el, cls)
      const popover = el.matches(':popover-open')
      queueMicrotask(() => {
        if (el.isConnected || !(parent as Node).isConnected) return
        parent.insertBefore(ghost, next && next.parentNode === parent ? next : null)
        if (popover) {
          try {
            ghost.showPopover()
          } catch {
            // As above.
          }
        }
        play(ghost, ghost)
      })
    }
  }, [ref, cls])
}
