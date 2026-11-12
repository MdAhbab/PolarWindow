import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { BrandLogo, BrandName } from '../components/Brand'
import { createMoonScene, type MoonScene, type SceneState } from '../landing/moonScene'
import { readPrefs } from '../lib/prefs'
import { DATA_MODE, snapshotTileUrl } from '../lib/api/snapshot'
import { API_BASE } from '../lib/api/client'
import { Counts } from '../components/landing/HeroCounts'
import { EnterButton } from '../components/landing/Enter'
import { FeatureGroup } from '../components/landing/FeatureGroup'
import { CloseStage, LightStage } from '../components/landing/FilmStage'
import { BEATS } from '../components/landing/film'
import { IdeaCard } from '../components/landing/IdeaCard'
import { IDEAS } from '../components/landing/ideas'
import { Margins } from '../components/landing/Margins'
import { ScrubStage } from '../components/landing/ScrubStage'
import { SoundToggle } from '../components/landing/SoundToggle'
import { useFilmEnv } from '../components/landing/useFilmEnv'
import '../components/landing/landing.css'

gsap.registerPlugin(ScrollTrigger)

/**
 * The front page: what the product is for, in four ideas, and one button in.
 *
 * Scrolling turns the Moon to its south pole. After the hero, three films take
 * over the middle of the page: one that plays by itself, and two that scroll
 * drives (components/landing); the Moon returns as a crescent for what the
 * product does, and a last film plays under the way in. The pointer tilts the
 * Moon a little. None of that carries information the text does not: the
 * canvas and the films are decoration, hidden from assistive technology, and
 * with reduced motion (or without WebGL, or without the film files) the page is
 * the same words with still drawings.
 *
 * No number appears here unless the API sent it: the two counts are the
 * mission list's and the site list's own, and the three figures under the idea
 * cards are the service's own, each with its margin and its tag; all are left
 * out if they don't load.
 */

// The first picture: a waxing gibbous Moon, lit from the right of the viewer, the craters sharp along its terminator.
const START: SceneState = { tilt: -0.3, spin: 0.6, distance: 4.4, sunAz: 0.15, earth: 0, shift: 0.5 }
// The pole, which the hero's scroll turns the Moon to; the films cover the Moon from here until the product is shown.
const POLE = { tilt: -1.25, spin: 0, distance: 3.6, sunAz: 2.6, shift: 0.45 }

function useReducedMotionPref(): boolean {
  const [reduced] = useState(() => {
    const os = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
    return os || readPrefs().motion === 'reduced'
  })
  return reduced
}

export default function LandingScreen() {
  const reduced = useReducedMotionPref()
  const film = useFilmEnv()
  const rootRef = useRef<HTMLDivElement>(null)
  const canvasWrapRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<MoonScene | null>(null)
  const [webgl, setWebgl] = useState(true)

  // The theme the visitor chose last time, before the first paint.
  useLayoutEffect(() => {
    const p = readPrefs()
    document.documentElement.dataset.theme = p.theme
    document.documentElement.dataset.motion = p.motion
    document.title = 'POLAR WINDOW · plan landings at the Moon’s south pole'
  }, [])

  // Light theme, with motion: the page opens standing on the Moon at
  // Connecting Ridge with Earth rising, and the first scroll flies out to the
  // whole Moon, the black sky clearing to the page as it arrives.
  const earthrise = useState(() => readPrefs().theme === 'light')[0] && !reduced
  const onGround = earthrise && webgl
  const flightRef = useRef<HTMLDivElement>(null)
  const heroRef = useRef<HTMLDivElement>(null)
  // What the Moon returns for: the idea about ice, what the product does, and how it is measured.
  const crescentRef = useRef<HTMLDivElement>(null)
  // The three films, which cover the whole window from the first to the last: the Moon is not drawn behind them.
  const whyRef = useRef<HTMLDivElement>(null)

  // The Moon, and what scrolling and the pointer do to it.
  useEffect(() => {
    const wrap = canvasWrapRef.current
    const root = rootRef.current
    if (!wrap || !root) return

    const canvas = document.createElement('canvas')
    canvas.setAttribute('aria-hidden', 'true')
    canvas.className = 'pw-landing-canvas pointer-events-none fixed inset-0 h-full w-full'
    wrap.appendChild(canvas)

    let scene: MoonScene
    try {
      const tile = (z: number, x: number, y: number) =>
        DATA_MODE === 'snapshot' ? snapshotTileUrl('hillshade', z, x, y) : `${API_BASE}/tiles/hillshade/${z}/${x}/${y}.png`
      // Dark: the Moon in the night sky. Light: the Earthrise first, then the Moon on the page.
      const theme = readPrefs().theme === 'light' ? 'light' : 'dark'
      const first = reduced
        ? { ...START, tilt: -1.3, distance: 3.8, sunAz: 1.4 }
        : earthrise
          ? { ...START, ground: 1, space: 1 }
          : START
      scene = createMoonScene(canvas, tile, first, { theme, ground: earthrise })
    } catch {
      canvas.remove()
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
        canvas.remove()
      }
    }

    scene.setAutoSpin(true)
    scene.start()
    let covered = false
    const ctx = gsap.context(() => {
      const s = scene.state
      // Hero -> the Sun never climbs: turn to the south pole. It takes the scroll it always took (about
      // 1.15 screens, 1.36 on the light page with its flight out from the ground), whatever the page
      // after it grows to; the films come next and cover the Moon.
      gsap
        .timeline({
          defaults: { ease: 'none' },
          scrollTrigger: {
            trigger: root,
            start: 'top top',
            end: () => `+=${Math.round(window.innerHeight * (earthrise ? 1.36 : 1.15))}`,
            scrub: 0.8,
            invalidateOnRefresh: true,
          },
        })
        .to(s, POLE)
      // Back for the product: from the pole out to a crescent as the section after the films comes up,
      // then a slow drift. One move out, once; the Moon does not zoom in and out between.
      const back = gsap.timeline({
        defaults: { ease: 'none' },
        scrollTrigger: { trigger: crescentRef.current, start: 'top bottom', end: 'bottom bottom', scrub: 0.8 },
      })
      back.fromTo(s, { ...POLE }, { tilt: -0.6, distance: 4.4, sunAz: 8.6, shift: 0.5, immediateRender: false })
      back.fromTo(s, { tilt: -0.6, distance: 4.4, sunAz: 8.6, shift: 0.5 }, { tilt: -0.5, distance: 4.6, sunAz: 9.0, immediateRender: false })

      // Light: off the ground and out to the whole Moon over the hero and a
      // stretch of open sky after it, the sky clearing to the page at the end.
      const flight = flightRef.current
      if (earthrise && flight) {
        const ft = gsap.timeline({
          defaults: { ease: 'none' },
          // Over before the next heading comes into view: it is dark ink, for the light page.
          scrollTrigger: { trigger: flight, start: 'top top', end: 'bottom 85%', scrub: 0.8 },
          // The page's styles follow the sky: how pale the Moon is, and the shade behind the words (globals.css).
          onUpdate: () => root.style.setProperty('--pw-space', String(s.space ?? 0)),
        })
        ft.to(s, { ground: 0, duration: 0.8, ease: 'power1.inOut' })
        ft.to(s, { space: 0, duration: 0.25 }, 0.75)
        // The shade behind the first words goes as they scroll out.
        ScrollTrigger.create({
          trigger: heroRef.current,
          start: 'top top',
          end: 'bottom 35%',
          scrub: true,
          onUpdate: (st) => root.style.setProperty('--pw-hero', String(1 - st.progress)),
        })
      }

      // Under the films nothing of the Moon shows, so it is not drawn (the films seek and decode on the same thread).
      ScrollTrigger.create({
        trigger: whyRef.current,
        start: 'top top',
        end: 'bottom bottom',
        onToggle: (self) => {
          covered = self.isActive
          if (covered) scene.stop()
          else if (!document.hidden) scene.start()
        },
      })

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
    const onVisibility = () => (document.hidden || covered ? scene.stop() : scene.start())
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      window.removeEventListener('pointermove', onPointer)
      document.removeEventListener('visibilitychange', onVisibility)
      ctx.revert()
      scene.dispose()
      sceneRef.current = null
      canvas.remove()
    }
  }, [reduced, earthrise])

  // Arriving at /#why (the old story's address) scrolls to the four ideas.
  const { hash } = useLocation()
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' })
  }, [hash, reduced])

  const animate = !film.reduced

  return (
    <div
      ref={rootRef}
      className="relative min-h-full bg-canvas text-ink"
      // 1 while the light theme's first picture has its black sky, 0 once the page is the page (set by the scroll).
      style={{ ['--pw-space' as string]: onGround ? 1 : 0 }}
    >
      {/* The black of space under the first picture, there before the picture has loaded. */}
      {onGround && <div aria-hidden="true" className="pw-landing-space pointer-events-none fixed inset-0" />}
      <div ref={canvasWrapRef} aria-hidden="true" className={webgl ? '' : 'hidden'} />
      {/* The picture is shaded behind the words, so they read over the Milky Way or the Moon. */}
      {webgl && <div aria-hidden="true" className="pw-sky-shade pointer-events-none fixed inset-0" />}
      {webgl && (
        <div
          aria-hidden="true"
          className="pointer-events-none fixed inset-0 bg-canvas/55 lg:hidden"
          style={{ opacity: 'calc(1 - var(--pw-space, 0))' }}
        />
      )}
      {/* The first picture's own shade. It stays with the window and thins as the words scroll away,
          so it never shows an edge crossing the picture. */}
      {onGround && <div aria-hidden="true" className="pw-ground-shade pointer-events-none fixed inset-0 max-lg:bg-black/55" />}
      <a
        href="#landing-main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-pill focus:bg-raised focus:px-5 focus:py-3"
      >
        Skip to the content
      </a>

      {/* The dashboard's island, so the front page and the dashboard read as one product. */}
      <header className="pointer-events-none sticky top-0 z-20 px-3 pt-3 sm:px-4">
        {/* Over the films the island has no blur behind it (nothing blurs a film), so it is solid: the glass colour let the words scrolling under it show through. */}
        <div
          className="pw-island pointer-events-auto mx-auto flex w-fit max-w-full items-center gap-3 rounded-pill py-1.5 pr-1.5 pl-4 sm:gap-6"
          style={{ backdropFilter: 'none', WebkitBackdropFilter: 'none', background: 'var(--color-raised)' }}
        >
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
        {/* In the light theme the first screen is dark: Earth over the Moon's
            horizon, under the island and behind the words. */}
        <div ref={flightRef}>
        <div ref={heroRef} data-theme={onGround ? 'dark' : undefined}>
        <Section className={`justify-center ${onGround ? 'min-h-[100vh]' : 'min-h-[86vh]'}`}>
          <div className="flex max-w-2xl flex-col gap-7">
            <p className="pw-eyebrow !text-ink-2">NASA CLPS missions · the Moon’s south pole</p>
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
            <p className="text-caption leading-caption font-medium text-ink-2">
              No account needed: the button signs you in as the project manager.
            </p>
          </div>
        </Section>
        </div>
        {/* Open sky for the flight out to the Moon: nothing to read over it. */}
        {onGround && <div aria-hidden="true" className="h-[120vh]" />}
        </div>

        {/* The three films that explain the pole: one that plays by itself, two that scroll drives. */}
        <div ref={whyRef} id="why" className="scroll-mt-20">
          <LightStage idea={IDEAS[0]} total={IDEAS.length} autoplay={film.autoplay} small={film.size === 'small'} animate={animate} />
          <ScrubStage
            idea={IDEAS[1]}
            index={1}
            total={IDEAS.length}
            film="shadow"
            beats={BEATS.shadow}
            pinned={film.scrub}
            small={film.size === 'small'}
            animate={animate}
          />
          <ScrubStage
            idea={IDEAS[2]}
            index={2}
            total={IDEAS.length}
            film="earth"
            beats={BEATS.earth}
            pinned={film.scrub}
            small={film.size === 'small'}
            animate={animate}
          />
        </div>

        {/* The Moon comes back as a crescent behind the rest of the page. */}
        <div ref={crescentRef}>
          <Section className="min-h-[65vh] justify-center">
            <div data-reveal className="flex w-full max-w-lg">
              <IdeaCard idea={IDEAS[3]} index={3} total={IDEAS.length} variant="stacked" animate={animate} />
            </div>
          </Section>

          <Section>
            <div className="flex max-w-5xl flex-col gap-8">
              <h2 data-reveal className="pw-display text-[32px] leading-[1.06] sm:text-[44px]">
                What you can do
              </h2>
              <FeatureGroup animate={animate} />
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
              <Margins />
            </div>
          </Section>
        </div>

        <CloseStage autoplay={film.autoplay} phone={film.phone} small={film.size === 'small'} />
      </main>

      <SoundToggle />

      {/* On the page's own ground, so its small print never sits over the Moon. */}
      <footer className="relative z-10 flex flex-col gap-6 border-t border-line bg-canvas px-4 py-10 lg:px-8">
        <BrandLogo className="h-10 sm:h-12" />
        <p className="max-w-3xl text-caption leading-caption text-ink-3">
          Not an official product of NASA or any space agency. The Moon is NASA’s LRO camera mosaic, with the LOLA relief map at the south pole. Earth is NASA’s Blue Marble. Milky Way:{' '}
          <a href="https://www.eso.org/public/images/eso0932a/" target="_blank" rel="noreferrer">
            ESO/S. Brunier
          </a>{' '}
          (CC BY 4.0). These are pictures, not to scale. The Sun is placed to light them, not where it stands on any date. Illustration, generated. Not mission footage.
        </p>
      </footer>
    </div>
  )
}

function Section({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`flex flex-col px-4 py-24 lg:px-8 lg:py-36 ${className}`}>{children}</section>
}
