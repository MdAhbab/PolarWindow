import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { Icon } from '../components/Icon'
import { BrandLogo, BrandName } from '../components/Brand'
import { SunPathArt, RidgeArt, EarthArt, IceArt } from '../landing/Illustrations'
import { createMoonScene, type MoonScene, type SceneState } from '../landing/moonScene'
import { readPrefs } from '../lib/prefs'
import { SignInFailed, useSession } from '../lib/session'
import { useMissions, useSites } from '../lib/api/queries'
import { DATA_MODE, snapshotTileUrl } from '../lib/api/snapshot'
import { API_BASE } from '../lib/api/client'

gsap.registerPlugin(ScrollTrigger)

/**
 * The front page: what the product is for, in four ideas, and one button in.
 *
 * Scrolling turns the Moon to its south pole, sends the Sun around the
 * horizon, brings Earth up low, and closes in on the real terrain. The pointer
 * tilts it a little. None of that carries information the text does not: the
 * canvas is decoration, hidden from assistive technology, and with reduced
 * motion (or without WebGL) the page is the same words with still drawings.
 *
 * No number appears here unless the API sent it: the two counts are the
 * mission list's and the site list's own, and are left out if they don't load.
 */

// The first picture: a waxing gibbous Moon, lit from the right of the viewer, the craters sharp along its terminator.
const START: SceneState = { tilt: -0.3, spin: 0.6, distance: 4.4, sunAz: 0.15, earth: 0, shift: 0.5, near: 1 }

const IDEAS = [
  {
    id: 'sun',
    title: 'The Sun never climbs',
    body: 'Near the Moon’s south pole the Sun doesn’t rise overhead. It circles along the horizon all month, so its light always arrives sideways.',
    Art: SunPathArt,
  },
  {
    id: 'ridge',
    title: 'So a hill can switch off the Sun',
    body: 'Light that low is easy to block. A ridge kilometres away can put a lander in shadow for days, and it has to survive on its batteries until the Sun returns.',
    Art: RidgeArt,
  },
  {
    id: 'earth',
    title: 'Earth is low in the sky too',
    body: 'Radio needs a clear line to Earth. From the pole, Earth hangs near the horizon and bobs up and down, so hills cut off contact for stretches of time.',
    Art: EarthArt,
  },
  {
    id: 'ice',
    title: 'The ice is in the dark. The power is in the light.',
    body: 'Water ice survives only in crater floors the Sun never reaches. Solar power works only where it does. Missions land on the edge between them, so the exact spot matters.',
    Art: IceArt,
  },
]

const FEATURES = [
  {
    icon: 'pin' as const,
    title: 'Missions',
    body: 'Every NASA CLPS delivery, flown and planned, with its landing spot, dates, what it carries and where each fact comes from.',
  },
  {
    icon: 'clocks' as const,
    title: 'Sunlight and contact',
    body: 'For any site and dates: hours of sunlight, hours in contact with Earth, the longest night and the longest time without contact.',
  },
  {
    icon: 'compare' as const,
    title: 'Compare',
    body: 'Rank candidate sites by one measure at a time. The page never merges them into one score.',
  },
  {
    icon: 'gap' as const,
    title: 'Plan',
    body: 'Every stretch without contact, longest first, what the lander must handle alone, and a spreadsheet to share.',
  },
]

function useReducedMotionPref(): boolean {
  const [reduced] = useState(() => {
    const os = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
    return os || readPrefs().motion === 'reduced'
  })
  return reduced
}

export default function LandingScreen() {
  const reduced = useReducedMotionPref()
  const rootRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sceneRef = useRef<MoonScene | null>(null)
  const [webgl, setWebgl] = useState(true)

  // The theme the visitor chose last time, before the first paint.
  useLayoutEffect(() => {
    const p = readPrefs()
    document.documentElement.dataset.theme = p.theme
    document.documentElement.dataset.motion = p.motion
    document.title = 'POLAR WINDOW · plan landings at the Moon’s south pole'
  }, [])

  // The Moon, and what scrolling and the pointer do to it.
  useEffect(() => {
    const canvas = canvasRef.current
    const root = rootRef.current
    if (!canvas || !root) return
    let scene: MoonScene
    try {
      const tile = (z: number, x: number, y: number) =>
        DATA_MODE === 'snapshot' ? snapshotTileUrl('hillshade', z, x, y) : `${API_BASE}/tiles/hillshade/${z}/${x}/${y}.png`
      // Dark: the Moon in the night sky. Light: Earth in front of the Moon.
      const theme = readPrefs().theme === 'light' ? 'light' : 'dark'
      scene = createMoonScene(canvas, tile, reduced ? { ...START, tilt: -1.3, distance: 3.8, sunAz: 1.4 } : START, { theme })
    } catch {
      setWebgl(false)
      return
    }
    sceneRef.current = scene

    if (reduced) {
      // One still frame, drawn again only when the window changes size.
      scene.render()
      const redraw = () => scene.render()
      window.addEventListener('resize', redraw)
      return () => {
        window.removeEventListener('resize', redraw)
        scene.dispose()
        sceneRef.current = null
      }
    }

    scene.setAutoSpin(true)
    scene.start()
    const ctx = gsap.context(() => {
      const s = scene.state
      const tl = gsap.timeline({
        defaults: { ease: 'none' },
        scrollTrigger: { trigger: root, start: 'top top', end: 'bottom bottom', scrub: 0.8 },
      })
      // Hero -> the Sun never climbs: leave Earth behind and turn to the south pole.
      tl.to(s, { tilt: -1.25, spin: 0, distance: 3.6, sunAz: 2.6, shift: 0.45, near: 0 })
      // -> a hill switches off the Sun: the pole head-on, the Sun circling it.
      tl.to(s, { tilt: -1.52, distance: 2.5, sunAz: 4.8 })
      // -> Earth is low: step back and let Earth rise over the horizon.
      tl.to(s, { tilt: -1.3, distance: 4.0, earth: 1, sunAz: 5.8 })
      // -> ice in the dark: close in on the real terrain.
      tl.to(s, { tilt: -1.57, distance: 1.55, earth: 0, sunAz: 7.4 })
      // -> what you can do, and the way in: back out.
      tl.to(s, { tilt: -0.6, distance: 4.4, sunAz: 8.6, shift: 0.5 })
      tl.to(s, { tilt: -0.4, distance: 4.8, sunAz: 9.6 })

      ScrollTrigger.create({
        trigger: root,
        start: 'top top',
        end: '+=200',
        onLeave: () => scene.setAutoSpin(false),
        onEnterBack: () => scene.setAutoSpin(true),
      })

      // The dashboard's arrival: a rise on the settle curve (expo.out is
      // cubic-bezier(0.16, 1, 0.3, 1)), never a fade, so the words are
      // readable from the first frame; cards in a group follow 60 ms apart.
      gsap.utils.toArray<HTMLElement>('[data-reveal]').forEach((el) => {
        gsap.from(el, {
          y: 18,
          duration: 0.82,
          ease: 'expo.out',
          delay: Number(el.dataset.revealI ?? 0) * 0.06,
          scrollTrigger: { trigger: el, start: 'top 88%' },
        })
      })
    }, root)

    const onPointer = (e: PointerEvent) => {
      scene.setPointer((e.clientX / window.innerWidth) * 2 - 1, (e.clientY / window.innerHeight) * 2 - 1)
    }
    window.addEventListener('pointermove', onPointer)
    const onVisibility = () => (document.hidden ? scene.stop() : scene.start())
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      window.removeEventListener('pointermove', onPointer)
      document.removeEventListener('visibilitychange', onVisibility)
      ctx.revert()
      scene.dispose()
      sceneRef.current = null
    }
  }, [reduced])

  // Arriving at /#why (the old story's address) scrolls to the four ideas.
  const { hash } = useLocation()
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' })
  }, [hash, reduced])

  return (
    <div ref={rootRef} className="relative min-h-full bg-canvas text-ink">
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        // Below lg the Moon sits behind the text, so it is dimmed to keep the
        // words readable; beside the text it is shown in full.
        className={`pointer-events-none fixed inset-0 h-full w-full opacity-40 lg:opacity-100 ${webgl ? '' : 'hidden'}`}
      />
      <a
        href="#landing-main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-pill focus:bg-raised focus:px-5 focus:py-3"
      >
        Skip to the content
      </a>

      {/* The dashboard's island, so the front page and the dashboard read as one product. */}
      <header className="pointer-events-none sticky top-0 z-20 px-3 pt-3 sm:px-4">
        <div className="pw-island pointer-events-auto mx-auto flex w-fit max-w-full items-center gap-3 rounded-pill py-1.5 pr-1.5 pl-4 sm:gap-6">
          <span className="flex h-12 items-center">
            <BrandName />
          </span>
          {/* Below 640 px the hero's own button is just below; the island keeps the logo alone. */}
          <span className="hidden sm:inline-flex">
            <EnterButton compact />
          </span>
        </div>
      </header>

      <main id="landing-main" tabIndex={-1} className="relative z-10 outline-none">
        <Section className="min-h-[86vh] justify-center">
          <div className="flex max-w-2xl flex-col gap-7">
            <p className="pw-eyebrow">NASA CLPS missions · the Moon’s south pole</p>
            <h1 className="pw-display text-[40px] leading-[1.02] sm:text-[60px] lg:text-[72px]">
              Plan a landing where the Sun barely rises
            </h1>
            <p className="max-w-xl text-large leading-8 text-ink-2 text-pretty">
              For every NASA CLPS mission and a set of candidate landing sites near the Moon’s south pole: when a lander
              gets sunlight for power, and when it can talk to Earth.
            </p>
            <Counts />
            <div className="flex flex-wrap items-center gap-3">
              <EnterButton />
              <a
                href="#why"
                className="pw-press inline-flex h-12 items-center gap-2 rounded-pill border border-line-strong bg-tray px-5 text-control font-semibold text-ink no-underline hover:border-ink-3 hover:bg-inset"
              >
                How it works
                <span aria-hidden="true">↓</span>
              </a>
            </div>
            <p className="text-caption leading-caption text-ink-3">
              No account needed: the button signs you in as the project manager.
            </p>
          </div>
        </Section>

        <div id="why" className="scroll-mt-20">
          <Section>
            <h2 data-reveal className="pw-display max-w-xl text-[32px] leading-[1.06] sm:text-[44px]">
              Why the south pole is hard
            </h2>
          </Section>
          {IDEAS.map((idea, i) => (
            <Section key={idea.id} className="min-h-[65vh] justify-center">
              <article data-reveal className="pw-card flex max-w-lg flex-col gap-4 p-6 sm:p-8">
                <p className="pw-eyebrow">
                  {i + 1} of {IDEAS.length}
                </p>
                <h3 className="pw-display text-[26px] leading-[1.12] sm:text-[30px]">{idea.title}</h3>
                <p className="text-lede leading-7 text-ink-2 text-pretty">{idea.body}</p>
                <figure className="flex flex-col gap-2 border-t border-line pt-4">
                  <idea.Art />
                  <figcaption className="text-caption leading-caption text-ink-3">Drawing, not to scale.</figcaption>
                </figure>
              </article>
            </Section>
          ))}
        </div>

        <Section>
          <div className="flex max-w-3xl flex-col gap-8">
            <h2 data-reveal className="pw-display text-[32px] leading-[1.06] sm:text-[44px]">
              What you can do
            </h2>
            <ul className="grid gap-5 sm:grid-cols-2">
              {FEATURES.map((f, i) => (
                <FeatureCard key={f.title} {...f} index={i} reduced={reduced} />
              ))}
            </ul>
          </div>
        </Section>

        <Section>
          <div data-reveal className="pw-card flex max-w-xl flex-col gap-4 p-6 sm:p-8">
            <h2 className="pw-display text-[26px] leading-[1.12] sm:text-[30px]">Measured, with the margins shown</h2>
            <p className="text-lede leading-7 text-ink-2 text-pretty">
              The numbers come from NASA’s laser-altimeter map of the pole (LOLA) and the computed positions of the Sun
              and Earth (SPICE). Each one shows how far it could be off. The AI helpers can only use these numbers, and
              every answer is checked against them.
            </p>
          </div>
        </Section>

        <Section className="min-h-[70vh] justify-center">
          <div data-reveal className="flex max-w-xl flex-col gap-7">
            <h2 className="pw-display text-[36px] leading-[1.04] sm:text-[56px]">Open the dashboard</h2>
            <div>
              <EnterButton />
            </div>
          </div>
        </Section>
      </main>

      <footer className="relative z-10 flex flex-col gap-6 border-t border-line px-4 py-10 lg:px-8">
        <BrandLogo className="h-10 sm:h-12" />
        <p className="max-w-3xl text-caption leading-caption text-ink-3">
          Not an official product of NASA or any space agency. The Moon is NASA’s LRO camera mosaic, with the LOLA
          relief map at the south pole; Earth is NASA’s Blue Marble; the stars are drawn. Sizes and distances are not
          to scale.
        </p>
      </footer>
    </div>
  )
}

function Section({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`flex flex-col px-4 py-24 lg:px-8 lg:py-36 ${className}`}>{children}</section>
}

/** The two counts, from the API's own lists; nothing when they don't load. */
function Counts() {
  const missions = useMissions({})
  const sites = useSites({ kind: 'all' })
  const m = missions.data?.total
  const c = sites.data?.items.filter((i) => i.site.kind === 'candidate').length
  if (m === undefined || !c) return null
  return (
    <dl className="flex flex-wrap gap-10">
      <div className="flex flex-col-reverse">
        <dt className="text-small text-ink-3">CLPS missions</dt>
        <dd className="pw-figure text-[34px] leading-[38px]">{m}</dd>
      </div>
      <div className="flex flex-col-reverse">
        <dt className="text-small text-ink-3">candidate landing sites</dt>
        <dd className="pw-figure text-[34px] leading-[38px]">{c}</dd>
      </div>
    </dl>
  )
}

function FeatureCard({
  icon,
  title,
  body,
  index,
  reduced,
}: {
  icon: Parameters<typeof Icon>[0]['name']
  title: string
  body: string
  index: number
  reduced: boolean
}) {
  const ref = useRef<HTMLLIElement>(null)
  // A slight lean toward the pointer, as a hint that the cards are live.
  const onMove = (e: ReactPointerEvent<HTMLLIElement>) => {
    if (reduced || !ref.current) return
    const r = ref.current.getBoundingClientRect()
    const x = (e.clientX - r.left) / r.width - 0.5
    const y = (e.clientY - r.top) / r.height - 0.5
    gsap.to(ref.current, { rotateY: x * 6, rotateX: -y * 6, duration: 0.3, ease: 'power2.out', transformPerspective: 700 })
  }
  const onLeave = () => {
    if (!reduced && ref.current) gsap.to(ref.current, { rotateX: 0, rotateY: 0, duration: 0.4, ease: 'power2.out' })
  }
  return (
    <li
      ref={ref}
      onPointerMove={onMove}
      onPointerLeave={onLeave}
      data-reveal
      data-reveal-i={index}
      className="pw-card flex flex-col gap-3 p-6"
    >
      <span className="flex size-11 items-center justify-center rounded-pill bg-inset text-ink-2" aria-hidden="true">
        <Icon name={icon} size={22} />
      </span>
      <h3 className="pt-1 text-title-lg font-semibold tracking-title">{title}</h3>
      <p className="text-body leading-6 text-ink-2">{body}</p>
    </li>
  )
}

/** Signs in (one click, no password) and opens the page the visitor asked for. */
function EnterButton({ compact = false }: { compact?: boolean }) {
  const session = useSession((s) => s.session)
  const signIn = useSession((s) => s.signIn)
  const navigate = useNavigate()
  const { search } = useLocation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const next = (() => {
    const n = new URLSearchParams(search).get('next')
    return n && n.startsWith('/') && !n.startsWith('//') ? n : '/missions'
  })()
  const signedIn = Boolean(session && session.expiresAt > Date.now())

  const go = async () => {
    setError(null)
    if (signedIn) return navigate(next)
    setBusy(true)
    try {
      await signIn()
      navigate(next)
    } catch (e) {
      setError(e instanceof SignInFailed ? e.message : 'Signing in did not work. Try again in a moment.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="inline-flex flex-col gap-2">
      <button
        type="button"
        onClick={() => void go()}
        disabled={busy}
        className={`pw-press group inline-flex h-12 items-center justify-center gap-2 rounded-pill bg-sun-fill font-semibold whitespace-nowrap text-on-sun hover:bg-sun-soft disabled:bg-inset disabled:text-ink-3 ${
          compact ? 'pr-1.5 pl-4 text-body' : 'pr-2 pl-6 text-control'
        }`}
      >
        {busy ? 'Signing in…' : signedIn ? 'Go to the dashboard' : compact ? 'Open dashboard' : 'Open the dashboard'}
        {!busy && (
          <span className={`pw-orb ml-1 ${compact ? 'size-9' : ''}`} aria-hidden="true">
            <Icon name="arrow" size={15} strokeWidth={2} />
          </span>
        )}
      </button>
      {error && (
        <span role="alert" className="text-small text-ink">
          {error}
        </span>
      )}
    </span>
  )
}
