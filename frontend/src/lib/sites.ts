import type { Site } from './types'

/**
 * The candidate site registry.
 *
 * Sites used to be a hardcoded array with synthetic terrain specs. They now
 * come from the API, where their coordinates are *derived from the LOLA DEM*
 * rather than asserted -- the IAU coordinate for a named crater is its centre,
 * which is the permanently shadowed floor and the worst possible place to land.
 *
 * This stays a synchronous module-level registry, rather than becoming a hook,
 * for one practical reason: eight components call `siteById(id)` in render, and
 * the list is 15 entries that are immutable for a session. `App` gates every
 * screen on the list having loaded, so the synchronous accessor is always safe
 * by the time a screen runs. Converting all eight call sites to hooks would
 * have been churn in components whose design is finished.
 */

let registry: Site[] = []
let byId: Record<string, Site> = {}

export function setSites(sites: Site[]): void {
  registry = sites
  byId = Object.fromEntries(sites.map((s) => [s.id, s]))
}

export function getSites(): Site[] {
  return registry
}

export const SITES: Site[] = new Proxy([] as Site[], {
  get(_t, prop, receiver) {
    return Reflect.get(registry, prop, receiver)
  },
  has: (_t, prop) => Reflect.has(registry, prop),
  ownKeys: () => Reflect.ownKeys(registry),
  getOwnPropertyDescriptor: (_t, prop) => Reflect.getOwnPropertyDescriptor(registry, prop),
})

export function siteById(id: string): Site {
  const s = byId[id]
  if (!s) {
    throw new Error(
      `Unknown site: ${id}. The site registry holds ${registry.length} sites; ` +
        `if this is zero, a screen rendered before the site list finished loading.`,
    )
  }
  return s
}

export function hasSite(id: string): boolean {
  return Boolean(byId[id])
}

/**
 * The derived candidate sites only.
 *
 * The registry holds every site (`kind=all`) so a mission target resolves by
 * id on the Site, Compare, Horizon and Blackout screens. The Map's list, its
 * pins and the default comparison stay the 15 candidates, as in v1.
 */
export function getCandidates(): Site[] {
  return registry.filter((s) => s.kind === 'candidate')
}

/** The three the compare screen opens on, resolved against whatever loaded. */
export function defaultCompare(): string[] {
  const preferred = ['connecting-ridge', 'malapert-massif', 'faustini-rim']
  const present = preferred.filter(hasSite)
  if (present.length >= 2) return present
  return getCandidates()
    .slice(0, 3)
    .map((s) => s.id)
}
