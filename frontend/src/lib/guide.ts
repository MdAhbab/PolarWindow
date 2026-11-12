import { create } from 'zustand'

/**
 * The guide bar's three steps: one per major feature, each introduced once. It is
 * optional and never opens by itself; Guide in the header's menu opens it. The
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
    body: 'Landing sites holds the candidate sites near the pole. See the map, one site, sites side by side, and a plan for time without contact. Numbers are never added into one.',
  },
  {
    id: 'journey',
    path: '/missions/im-2/trip',
    target: 'journey',
    title: 'Follow a mission from start to finish',
    body: 'Each mission has six steps, from getting ready to coming home. Every step answers one question the same way. Press the name of any number to see what it means and where it comes from.',
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
    // Closed until the person opens it (ruling L-5); after that, as it was left.
    return { open: v.open === true, step }
  } catch {
    return { open: false, step: 0 }
  }
}

function write(v: Stored): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(v))
  } catch {
    /* storage refused: the guide starts closed next visit */
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
