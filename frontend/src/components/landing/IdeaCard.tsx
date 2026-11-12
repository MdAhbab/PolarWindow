import { useEffect, useMemo, useRef, type RefObject } from 'react'
import { useMetrics, useSites } from '../../lib/api/queries'
import { DEFAULT_STEP_S } from '../../lib/store'
import { Skeleton } from '../States'
import { EnterLink } from './Enter'
import { exampleLine, pickExampleSite, type ExampleLine } from './example'
import type { Idea } from './ideas'
import { Tag } from './Tag'
import './landing.css'

/**
 * One idea, as a card: where it is in the four ("1 of 4"), its title and
 * words, its drawing (which makes its point by moving once when the card comes
 * into view), one real figure from the service where it has one, and one link
 * to the page of the dashboard that shows the idea.
 *
 * Two shapes. `stacked` is the card all at once, for a page that is not
 * pinned (a phone, reduced motion, data saver, a film that did not load). `beats`
 * is the same card over a scroll-driven film: the title and drawing stay, and
 * the words under the title change as the film moves (the stage sets which
 * beat shows; see ScrubStage and landing.css).
 */
export function IdeaCard({
  idea,
  index,
  total,
  variant,
  animate,
  playOn,
}: {
  idea: Idea
  index: number
  total: number
  variant: 'stacked' | 'beats'
  /** Motion is allowed: the drawing plays its one movement. */
  animate: boolean
  /** The element whose crossing of the window plays the drawing; the card itself by default. */
  playOn?: RefObject<HTMLElement | null>
}) {
  const card = useRef<HTMLElement>(null)
  const art = useRef<HTMLDivElement>(null)
  useArtPlay(art, playOn ?? card, animate, playOn ? '0px 0px -88% 0px' : '-22% 0px -22% 0px')
  const beats = variant === 'beats' && idea.beats
  const slot = idea.example ? <ExampleSlot kind={idea.example} /> : null
  const where = (
    <p className="flex flex-col items-start gap-0.5 text-lede leading-7 text-ink-2">
      <span>{idea.lives.line}</span>
      <EnterLink to={idea.lives.to}>{idea.lives.link}</EnterLink>
    </p>
  )

  return (
    <article ref={card} className="pw-card flex w-full max-w-lg flex-col gap-4 p-6 sm:p-8">
      <p className="pw-eyebrow">
        {index + 1} of {total}
      </p>
      <h3 className="pw-display text-[26px] leading-[1.12] sm:text-[30px]">{idea.title}</h3>
      {beats ? (
        <div className="pw-beats">
          <div className="pw-beat flex flex-col gap-4" data-i="0">
            <p className="max-w-[62ch] text-lede leading-7 text-ink-2 text-pretty">{idea.beats?.first}</p>
          </div>
          <div className="pw-beat flex flex-col gap-4" data-i="1">
            <p className="max-w-[62ch] text-lede leading-7 text-ink-2 text-pretty">{idea.beats?.second}</p>
            {slot}
          </div>
          <div className="pw-beat flex flex-col gap-4" data-i="2">
            {where}
          </div>
        </div>
      ) : (
        <p className="max-w-[62ch] text-lede leading-7 text-ink-2 text-pretty">{idea.body}</p>
      )}
      <figure className="flex flex-col gap-2 border-t border-line pt-4">
        <div ref={art} className="pw-art max-h-[30dvh] [&>svg]:mx-auto [&>svg]:max-h-[30dvh]">
          <idea.Art />
        </div>
        <figcaption className="text-caption leading-caption text-ink-2">Drawing, not to scale.</figcaption>
      </figure>
      {!beats && (
        <>
          {slot}
          {where}
        </>
      )}
    </article>
  )
}

/**
 * The drawing's one movement: armed while its card is out of the window, played
 * when it comes in (the crossing of a band across the middle of the window, an
 * IntersectionObserver, no scroll listener), armed again when it goes, so
 * scrolling back to a card plays it again. With motion off nothing is set and
 * the drawing is as drawn.
 */
function useArtPlay(art: RefObject<HTMLElement | null>, trigger: RefObject<HTMLElement | null>, enabled: boolean, margin: string) {
  useEffect(() => {
    const el = art.current
    const watch = trigger.current
    if (!el || !watch) return
    if (!enabled || typeof IntersectionObserver === 'undefined') {
      delete el.dataset.art
      return
    }
    el.dataset.art = 'armed'
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) el.dataset.art = e.isIntersecting ? 'play' : 'armed'
      },
      { rootMargin: margin, threshold: 0 },
    )
    io.observe(watch)
    return () => {
      io.disconnect()
      delete el.dataset.art
    }
  }, [art, trigger, enabled, margin])
}

/**
 * The figure under a card: read off the service for one named site over its
 * own default dates, so a card shows a real number or nothing. While the answer
 * is on its way a slot of the line's height holds the place; if it never
 * comes, or the figure cannot honestly be given (see exampleLine), the slot is
 * gone and takes no room.
 */
function ExampleSlot({ kind }: { kind: NonNullable<Idea['example']> }) {
  const sites = useSites({ kind: 'all' })
  const site = useMemo(() => pickExampleSite(sites.data?.items), [sites.data])
  const metrics = useMetrics(site?.id, { start: site?.start ?? '', end: site?.end ?? '', stepS: DEFAULT_STEP_S })
  const line = site ? exampleLine(kind, site, metrics.data) : null

  if (sites.isPending || (site && metrics.isPending)) {
    return <Skeleton className="h-[72px] w-full" />
  }
  if (!line) return null
  return <ExampleBlock line={line} />
}

function ExampleBlock({ line }: { line: ExampleLine }) {
  return (
    <div className="flex flex-col gap-1 border-l-2 border-line-strong pl-4">
      <span className="sr-only">{line.spoken}</span>
      <div aria-hidden="true" className="flex flex-col gap-1">
        <span className="text-small leading-5 text-ink-2">{line.label}</span>
        <span className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <span className="font-mono text-title leading-6 font-medium text-ink tnum">
            {line.figure} <span className="text-uncertain">{line.margin}</span> {line.unit}
          </span>
          <Tag kind={line.tag} />
        </span>
        <span className="text-caption leading-caption text-ink-3">
          {line.note ? `${line.note}, ` : ''}
          {line.dates}
        </span>
      </div>
    </div>
  )
}
