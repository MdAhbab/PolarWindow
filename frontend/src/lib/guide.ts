import { create } from 'zustand'

/**
 * The guide bar's steps: one per major feature, each introduced once. The
 * analysis pages come first, on the default dates (one lunar day); a mission's
 * page comes last, because opening one moves the dates to its time on the
 * surface, and the pages before it would then show only a few hours.
 *
 * Each step names the page it is about and the element on that page it points
 * at (`data-guide="…"`). The words describe what to do, not what the page
 * already says, so the guide never repeats the screen.
 */
export interface GuideStep {
  id: string
  /** The page this step is about. */
  path: string
  /** The `data-guide` value of the element it points at. */
  target: string
  title: string
  body: string
}

export const GUIDE_STEPS: GuideStep[] = [
  {
    id: 'missions',
    path: '/missions',
    target: 'missions-filters',
    title: 'Find a CLPS mission',
    body: 'CLPS is NASA’s program for buying Moon landings from private companies. This page lists every delivery, flown and planned; filter by instrument or company.',
  },
  {
    id: 'map',
    path: '/map',
    target: 'map',
    title: 'Choose a site on the map',
    body: 'Landing sites holds the candidate spots near the pole: the map, one site in detail, sites side by side, and a plan for time without contact. Numbers are never added into one score.',
  },
  {
    id: 'journey',
    path: '/missions/im-2/trip',
    target: 'journey',
    title: 'Follow a mission from start to finish',
    body: 'Each mission has six steps, from getting ready to coming home. Every step answers one question the same way: a sentence first, up to four numbers, one chart, and the rest in rows you open.',
  },
  {
    id: 'mission',
    path: '/missions/im-2/surface',
    target: 'sun-earth',
    title: 'See the Sun and Earth at a landing spot',
    body: 'The longest night decides how big the battery must be. Press the name of any number to see what it means and where it comes from; Listen reads the page out loud.',
  },
  {
    id: 'settings',
    path: '/missions/im-2/surface',
    target: 'settings',
    title: 'Settings and the project',
    body: 'Settings holds the project, its parameters and risk scale, where the live data comes from, the theme and motion. Press Guide at the top any time to see this tour again.',
  },
]

const KEY = 'pw-guide'

interface Stored {
  open: boolean
  step: number
}

function read(): Stored {
  try {
    const raw = typeof localStorage === 'undefined' ? null : localStorage.getItem(KEY)
    const v = raw ? (JSON.parse(raw) as Partial<Stored>) : {}
    const step = typeof v.step === 'number' && v.step >= 0 && v.step < GUIDE_STEPS.length ? v.step : 0
    // Open on the first visit to the dashboard; after that, as it was left.
    return { open: v.open !== false, step }
  } catch {
    return { open: true, step: 0 }
  }
}

function write(v: Stored): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(v))
  } catch {
    /* storage refused: the guide opens again next visit */
  }
}

interface GuideState extends Stored {
  setOpen: (open: boolean) => void
  go: (step: number) => void
}

export const useGuide = create<GuideState>((set, get) => ({
  ...read(),
  setOpen: (open) => {
    set({ open })
    write({ open, step: get().step })
  },
  go: (step) => {
    const s = Math.max(0, Math.min(GUIDE_STEPS.length - 1, step))
    set({ step: s, open: true })
    write({ open: true, step: s })
  },
}))

/** Whether a step is about the page at `pathname`. */
export function isOnStepPage(step: GuideStep, pathname: string): boolean {
  return step.path === pathname
}
