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
    title: 'Find a mission',
    body: 'Every NASA CLPS delivery to the Moon, flown and planned. Filter by what it carries or who built it. You’ll open one at the end of this guide.',
  },
  {
    id: 'map',
    path: '/map',
    target: 'map',
    title: 'Choose a site on the map',
    body: 'Select a pin to see its numbers. The shading is the part of the pole in darkness at the moment shown; press Play to watch it move.',
  },
  {
    id: 'site',
    path: '/clocks',
    target: 'rings',
    title: 'Read one site in detail',
    body: 'The outer ring is sunlight and the inner ring is contact with Earth, over the chosen dates. Gaps in a ring are when hills or the horizon block it.',
  },
  {
    id: 'compare',
    path: '/compare',
    target: 'rank-by',
    title: 'Compare sites side by side',
    body: 'Rank the sites by one measure at a time. The four measures are never added into one score, because a long night can’t be traded for extra sunlight.',
  },
  {
    id: 'plan',
    path: '/blackout',
    target: 'plan-list',
    title: 'Plan for time without contact',
    body: 'Every stretch when the lander can’t reach Earth, longest first, and what it must handle alone. Download the list as a spreadsheet for your team.',
  },
  {
    id: 'mission',
    path: '/missions/im-2',
    target: 'sun-earth',
    title: 'See the Sun and Earth at a mission’s landing spot',
    body: 'For the days a mission is on the surface: hours of sunlight, hours in contact with Earth, the longest night and the longest time without contact.',
  },
  {
    id: 'dates',
    path: '/missions/im-2',
    target: 'dates',
    title: 'Try other dates',
    body: 'Pick a month to move the dates. Its two bars show how much sunlight and Earth contact that month has, so a better month stands out.',
  },
  {
    id: 'helpers',
    path: '/missions/im-2',
    target: 'listen',
    title: 'Listen, or ask the AI',
    body: 'Listen reads a short summary aloud. The AI panels answer in words, and every number they use is checked against the measurements; the log shows each step.',
  },
  {
    id: 'settings',
    path: '/missions/im-2',
    target: 'detail',
    title: 'Choose the detail, and manage the project',
    body: 'Simple, Explain and Expert change how much is shown, never the numbers. Settings holds the display options and the project controls: the AI, its log and saved results.',
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
