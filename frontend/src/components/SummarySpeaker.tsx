import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import type { SiteView } from '../lib/api/queries'
import { hasSite, siteById } from '../lib/sites'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { buildSiteSummary, type Summary } from '../lib/summaryScript'
import { Icon } from './Icon'

/**
 * "Listen" (U16): one press, a ~30-second spoken overview of the site on
 * screen, built only from the numbers the API returned.
 *
 * Accessibility contract:
 *  - Never auto-plays (WCAG 1.4.2). Starts only on an explicit press.
 *  - A real <button> with aria-pressed; its name says what a press will do.
 *  - The same words are always in the DOM as a transcript, linked by
 *    aria-describedby, so a screen-reader user can read them at their own
 *    rate instead of hearing two voices at once. "Read it" shows them.
 *  - Floating captions highlight the sentence being spoken, with no layout
 *    shift, and Stop stays reachable after scrolling.
 *  - Esc stops speech. Alt+S toggles it: a modified key, because WCAG 2.1.4
 *    forbids bare-letter shortcuts that cannot be turned off.
 *  - Stops on site change, route change and unmount, and when the tab hides.
 *  - Where speech synthesis is unavailable the button opens the transcript.
 */
export function SummarySpeaker({ view }: { view: SiteView }) {
  const m = view.data?.metrics
  const meta = view.data?.meta
  const summary = useMemo(() => {
    if (!m || !hasSite(m.siteId)) return null
    const site = siteById(m.siteId)
    return buildSiteSummary({
      siteName: site.name,
      latDeg: site.latDeg,
      windowStartIso: m.windowStartIso,
      windowHours: m.windowHours,
      sunUpH: m.sun.upHours,
      sunFraction: m.sun.fractionUp,
      earthUpH: m.earth.upHours,
      earthFraction: m.earth.fractionUp,
      nightH: m.sun.longestDownH,
      nightOpen: Boolean(m.sun.longestDownOpen),
      nightToleranceH: m.sun.longestDownToleranceH,
      nightGrazing: Boolean(m.sun.longestDownArc?.grazing),
      silenceH: m.earth.longestDownH,
      silenceOpen: Boolean(m.earth.longestDownOpen),
      silenceToleranceH: m.earth.longestDownToleranceH,
      silenceGrazing: Boolean(m.earth.longestDownArc?.grazing),
      worstCompoundH: m.worstCompoundH,
      survivalLimitH: SURVIVAL_LIMIT_H,
      coverage: meta?.uncertainty.coverage ?? 1,
      terrainModelled: meta?.uncertainty.terrainModelled ?? true,
    })
  }, [m, meta])
  return <Speaker summary={summary} what="this site" resetKey={`${m?.siteId}|${m?.windowStartIso}`} />
}

/**
 * The control itself, for any script built from API numbers: a site, a
 * comparison. `what` finishes its name ("a 28-second summary of this site");
 * a change of `resetKey` stops the voice, as a change of route does.
 */
export function Speaker({ summary, what, resetKey }: { summary: Summary | null; what: string; resetKey: string }) {
  const { pathname } = useLocation()
  const transcriptId = useId()
  const [speaking, setSpeaking] = useState(false)
  const [current, setCurrent] = useState(-1)
  const [showText, setShowText] = useState(false)
  const cancelled = useRef(false)
  const canSpeak = typeof window !== 'undefined' && 'speechSynthesis' in window

  const stop = useCallback(() => {
    cancelled.current = true
    if (canSpeak) window.speechSynthesis.cancel()
    setSpeaking(false)
    setCurrent(-1)
  }, [canSpeak])

  const play = useCallback(() => {
    if (!summary) return
    if (!canSpeak) {
      setShowText(true)
      return
    }
    window.speechSynthesis.cancel()
    cancelled.current = false
    setSpeaking(true)
    // One utterance per sentence: reliable progress on every engine, where
    // word-boundary events are not.
    summary.sentences.forEach((sentence, i) => {
      const u = new SpeechSynthesisUtterance(sentence)
      u.lang = 'en-GB'
      u.rate = 1
      u.onstart = () => !cancelled.current && setCurrent(i)
      if (i === summary.sentences.length - 1) {
        u.onend = () => {
          setSpeaking(false)
          setCurrent(-1)
        }
      }
      u.onerror = () => {
        setSpeaking(false)
        setCurrent(-1)
      }
      window.speechSynthesis.speak(u)
    })
  }, [summary, canSpeak])

  // A new site, window, route, or leaving the page must never leave a voice talking.
  useEffect(() => stop, [resetKey, pathname, stop])

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      const t = ev.target as HTMLElement
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return
      if (ev.key === 'Escape' && speaking) stop()
      // `code`, not `key`: on macOS Option+S types "ß".
      if (ev.altKey && !ev.metaKey && !ev.ctrlKey && ev.code === 'KeyS') {
        ev.preventDefault()
        if (speaking) stop()
        else play()
      }
    }
    const onHide = () => {
      if (document.hidden && speaking) stop()
    }
    window.addEventListener('keydown', onKey)
    document.addEventListener('visibilitychange', onHide)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('visibilitychange', onHide)
    }
  }, [speaking, play, stop])

  if (!summary) return null

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={speaking ? stop : play}
          aria-pressed={speaking}
          aria-describedby={transcriptId}
          aria-keyshortcuts="Alt+S"
          className="inline-flex h-11 min-w-11 items-center gap-2 rounded-control border border-line-strong px-4 text-[15px] font-medium text-ink hover:bg-inset"
        >
          <Icon name="speaker" size={18} strokeWidth={2} />
          {/* Both words share one grid cell, so the button keeps the wider
              one's width and nothing beside it moves when it changes. The
              hidden word is out of the accessible name as well as the view. */}
          <span className="grid">
            <span className={`col-start-1 row-start-1 ${speaking ? 'invisible' : ''}`}>Listen</span>
            <span className={`col-start-1 row-start-1 ${speaking ? '' : 'invisible'}`}>Stop</span>
          </span>
          <span className="sr-only">
            {speaking ? ' the summary' : ` to a ${summary.seconds}-second summary of ${what}`}
          </span>
        </button>
        <button
          type="button"
          onClick={() => setShowText((v) => !v)}
          aria-expanded={showText}
          aria-controls={transcriptId}
          className="h-11 px-2 text-[15px] text-ink-2 underline-offset-4 hover:underline"
        >
          {showText ? 'Hide text' : 'Read it'}
        </button>
      </div>

      {/* Always in the DOM so aria-describedby resolves; shown only on request. */}
      <p id={transcriptId} className={showText ? 'max-w-[62ch] text-[15px] leading-6 text-ink-2' : 'sr-only'}>
        {summary.sentences.join(' ')}
      </p>

      {/* Live captions: a floating bar, so nothing on the page moves. The
          caption is aria-hidden because the voice is already saying it; the
          transcript above is the screen-reader copy. Above the phone tab bar. */}
      {speaking && (
        <div
          role="region"
          aria-label="Summary playing"
          className="fixed inset-x-4 bottom-[calc(5rem+env(safe-area-inset-bottom))] z-50 mx-auto flex max-w-2xl items-center gap-4 border border-line-strong bg-raised p-4 shadow-[0_8px_24px_rgba(0,0,0,0.45)] lg:bottom-4"
        >
          <p aria-hidden="true" className="grow text-[17px] leading-7 text-ink">
            {summary.sentences[Math.max(current, 0)]}
          </p>
          <button
            type="button"
            onClick={stop}
            className="h-11 shrink-0 rounded-control border border-line-strong px-4 text-[15px] font-medium text-ink hover:bg-inset"
          >
            Stop
          </button>
        </div>
      )}
    </div>
  )
}
