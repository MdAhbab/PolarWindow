import { useEffect } from 'react'
import { useReducedMotion } from './useMotion'

/** What arrives: every card that is not inside another card, and anything marked `data-reveal`. */
const TARGETS = '.pw-card, [data-reveal]'
/** 60 ms between things arriving together, and no more than eight steps of it. */
const STAGGER_MS = 60
const MAX_STEPS = 8

/**
 * The page arriving (design-visual-refresh.md, *Motion choreography*): each
 * card rises 18 px into place on the settle curve as it comes into view, the
 * ones that come in together 60 ms apart in reading order, and the bars in a
 * card grow 120 ms after it. Once per element; never a fade, so the words are
 * readable from the first frame.
 *
 * One IntersectionObserver for the whole page, no scroll listener. A card
 * below the fold waits 18 px low (`.pw-pre`, invisible since it is off
 * screen) and rises when it enters; one already in view rises at once. New
 * content (an answer replacing its skeleton, another page) is picked up by a
 * MutationObserver. Under reduced motion nothing is marked at all.
 */
export function useArrivals(rootId: string) {
  const reduced = useReducedMotion()
  useEffect(() => {
    const root = document.getElementById(rootId)
    if (reduced || !root || typeof IntersectionObserver === 'undefined') return
    const seen = new WeakSet<Element>()

    const rise = (els: Element[]) => {
      els
        .sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1))
        .forEach((el, i) => {
          const h = el as HTMLElement
          h.style.setProperty('--pw-delay', `${Math.min(i, MAX_STEPS) * STAGGER_MS}ms`)
          h.classList.remove('pw-pre')
          h.classList.add('pw-rise')
          // Once arrived, the card is itself again: its own hover lift and transitions apply.
          const done = (e: AnimationEvent) => {
            if (e.target !== h || e.animationName !== 'pw-rise') return
            h.classList.remove('pw-rise')
            h.style.removeProperty('--pw-delay')
            h.removeEventListener('animationend', done)
          }
          h.addEventListener('animationend', done)
        })
    }

    const io = new IntersectionObserver(
      (entries) => {
        const inView = entries.filter((e) => e.isIntersecting).map((e) => e.target)
        inView.forEach((el) => io.unobserve(el))
        if (inView.length) rise(inView)
      },
      { rootMargin: '0px 0px -6% 0px' },
    )

    const scan = () => {
      const fresh: Element[] = []
      root.querySelectorAll(TARGETS).forEach((el) => {
        if (seen.has(el)) return
        seen.add(el)
        // A card inside a card arrives with it; a row arrives with its list.
        if (el.parentElement?.closest('.pw-card, [data-reveal]')) return
        if (el.closest('dialog, [role="dialog"]')) return
        fresh.push(el)
      })
      if (!fresh.length) return
      const vh = window.innerHeight
      const now: Element[] = []
      for (const el of fresh) {
        const r = el.getBoundingClientRect()
        // Not drawn yet (hidden until asked for) counts as below the fold: it rises when it shows.
        const drawn = r.width > 0 || r.height > 0
        if (drawn && r.top < vh * 0.94 && r.bottom > 0) now.push(el)
        else {
          el.classList.add('pw-pre')
          io.observe(el)
        }
      }
      if (now.length) rise(now)
    }

    scan()
    let queued = 0
    const mo = new MutationObserver(() => {
      if (queued) return
      queued = requestAnimationFrame(() => {
        queued = 0
        scan()
      })
    })
    mo.observe(root, { childList: true, subtree: true })
    return () => {
      mo.disconnect()
      io.disconnect()
      cancelAnimationFrame(queued)
      root.querySelectorAll('.pw-pre, .pw-rise').forEach((el) => el.classList.remove('pw-pre', 'pw-rise'))
    }
  }, [rootId, reduced])
}
