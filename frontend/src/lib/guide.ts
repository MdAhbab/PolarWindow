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
    body: 'CLPS is NASA’s program for buying Moon landings from private companies. This page lists every CLPS delivery, both flown and planned. Filter by instrument or company, and open one at the end of this tour.',
  },
  {
    id: 'map',
    path: '/map',
    target: 'map',
    title: 'Choose a site on the map',
    body: 'Near the south pole, the Sun stays low and hills cast long shadows. The dark shading shows where the Sun is down at the moment shown. Select a pin to see that site’s four numbers.',
  },
  {
    id: 'site',
    path: '/site',
    target: 'rings',
    title: 'Read one site in detail',
    body: 'A lander needs sunlight for power and warmth, and Earth in view to talk. The outer ring shows sunlight, and the inner ring shows contact with Earth. Gaps mean a hill or the horizon blocks them.',
  },
  {
    id: 'compare',
    path: '/compare',
    target: 'rank-by',
    title: 'Compare sites side by side',
    body: 'Rank the sites by one number at a time. We never add the numbers into one score. Extra sunlight cannot make up for a night that drains the battery.',
  },
  {
    id: 'plan',
    path: '/plan',
    target: 'plan-list',
    title: 'Plan for time without contact',
    body: 'Without Earth in view, the lander must work alone on stored commands. This page lists every such stretch, longest first, with what to prepare. Download the list as a spreadsheet to share with your team.',
  },
  {
    id: 'mission',
    path: '/missions/im-2',
    target: 'sun-earth',
    title: 'See the Sun and Earth at a landing spot',
    body: 'These are the four numbers for this mission’s days on the surface. The longest night decides how big the battery must be. Press the name of any number to see what it means.',
  },
  {
    id: 'dates',
    path: '/missions/im-2',
    target: 'dates',
    title: 'Try other dates',
    body: 'Sunlight at the pole changes a lot from one month to the next. Open “Change the dates” and pick a month from the strip. Its two bars show sunlight and Earth contact, so good months stand out.',
  },
  {
    id: 'helpers',
    path: '/missions/im-2',
    target: 'listen',
    title: 'Listen, or ask the AI',
    body: 'Listen reads a short summary of this page out loud. The AI rows answer in plain words when you open them. Every number the AI uses is checked against our measurements first.',
  },
  {
    id: 'settings',
    path: '/missions/im-2',
    target: 'settings',
    title: 'Settings and the project',
    body: 'Settings holds the display options and the controls for this project. Turn the AI on or off, and read its activity log there. Press Guide at the top any time to see this tour again.',
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
