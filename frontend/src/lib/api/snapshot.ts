/**
 * The offline copy: answers the API gave on the demo path, saved by
 * `scripts/snapshot.ts` into `public/snapshot/`.
 *
 * Two ways in:
 *  - a build made with `VITE_DATA_MODE=snapshot` reads only from it, so a
 *    judge can open a static copy with no backend at all;
 *  - a live build falls back to it, request by request, when the service
 *    cannot be reached.
 *
 * Either way the header's provenance badge reads "Cached snapshot", and a
 * view that was not saved says so instead of showing anything invented.
 * Nothing here computes a number: a saved response is returned as it was
 * received. The one exception is the mission list, whose filters are applied
 * to the saved full list (status, instrument type, provider, region, text),
 * because every combination of chips cannot be saved.
 */
import { useSyncExternalStore } from 'react'
import type { MissionListDTO } from './client'

export const DATA_MODE: 'live' | 'snapshot' =
  import.meta.env.VITE_DATA_MODE === 'snapshot' ? 'snapshot' : 'live'

/** Where the saved files are served from, next to the app. */
const ROOT = `${import.meta.env.BASE_URL}snapshot/`

export interface SnapshotIndex {
  captured_at: string
  api_base: string
  /** "GET /sites?kind=all&limit=100" or "POST /compare {…}" → the saved file. */
  entries: Record<string, { file: string; status: number }>
}

let index: Promise<SnapshotIndex | null> | null = null

function loadIndex(): Promise<SnapshotIndex | null> {
  index ??= fetch(`${ROOT}index.json`)
    .then((r) => (r.ok ? (r.json() as Promise<SnapshotIndex>) : null))
    .catch(() => null)
  return index
}

// -- whether the screen is showing saved answers ------------------------------

let active = DATA_MODE === 'snapshot'
let capturedAt: string | null = null
const listeners = new Set<() => void>()

function setActive(on: boolean) {
  if (on === active) return
  active = on
  for (const l of listeners) l()
}

/** A live answer arrived: the badge goes back to what `/healthz` says. */
export function markLive() {
  if (DATA_MODE === 'live') setActive(false)
}

export function isSnapshotActive(): boolean {
  return active
}

export function useSnapshotActive(): boolean {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => active,
  )
}

/** When the saved answers were taken, for the badge's tooltip. */
export function snapshotCapturedAt(): string | null {
  return capturedAt
}

// -- lookups ------------------------------------------------------------------

export class SnapshotMiss extends Error {
  constructor(readonly key: string) {
    super(`Not in the offline copy: ${key}`)
    this.name = 'SnapshotMiss'
  }
}

export function requestKey(method: 'GET' | 'POST', pathAndQuery: string, body?: unknown): string {
  return method === 'POST' ? `POST ${pathAndQuery} ${JSON.stringify(body ?? null)}` : `GET ${pathAndQuery}`
}

/**
 * The saved answer for a request, or a `SnapshotMiss`. `status` is the saved
 * HTTP status, so a saved 404 is still a 404.
 */
export async function fromSnapshot(
  method: 'GET' | 'POST',
  pathAndQuery: string,
  body?: unknown,
): Promise<{ status: number; json: unknown }> {
  const idx = await loadIndex()
  if (!idx) throw new SnapshotMiss('index.json')
  capturedAt = idx.captured_at
  const key = requestKey(method, pathAndQuery, body)
  const hit = idx.entries[key] ?? agentFallback(idx, method, pathAndQuery)
  if (hit) {
    const json = await fetch(`${ROOT}${hit.file}`).then((r) => r.json())
    setActive(true)
    return { status: hit.status, json }
  }
  const list = await missionListFallback(idx, method, pathAndQuery)
  if (list) {
    setActive(true)
    return { status: 200, json: list }
  }
  throw new SnapshotMiss(key)
}

/**
 * Ask and Advise take free text, which cannot be saved for every wording.
 * Their saved answer is the measurements-only one (no model is configured on
 * the machine that took the snapshot), and it claims no number, so it stands
 * for any wording.
 */
function agentFallback(idx: SnapshotIndex, method: string, pathAndQuery: string) {
  if (method !== 'POST' || !/^\/agents\/(ask|advise)$/.test(pathAndQuery)) return undefined
  const prefix = `POST ${pathAndQuery} `
  const key = Object.keys(idx.entries).find((k) => k.startsWith(prefix))
  return key ? idx.entries[key] : undefined
}

/** The mission list's filters, applied to the saved full list. */
async function missionListFallback(
  idx: SnapshotIndex,
  method: string,
  pathAndQuery: string,
): Promise<MissionListDTO | null> {
  if (method !== 'GET' || !pathAndQuery.startsWith('/missions?')) return null
  const full = idx.entries['GET /missions']
  if (!full) return null
  const all = (await fetch(`${ROOT}${full.file}`).then((r) => r.json())) as MissionListDTO
  const q = new URLSearchParams(pathAndQuery.slice('/missions?'.length))
  const status = q.getAll('status')
  const types = q.getAll('payload_type')
  const provider = q.get('provider')
  const region = q.get('region')
  const text = q.get('q')?.toLowerCase()
  const items = all.items.filter(
    (m) =>
      (!status.length || status.includes(m.status)) &&
      (!types.length || m.payload_types.some((t) => types.includes(t))) &&
      (!provider || m.provider === provider) &&
      (!region || m.region === region) &&
      (!text || m.name.toLowerCase().includes(text)),
  )
  return { ...all, items, total: items.length }
}

/** A saved hillshade tile, beside the saved answers. */
export function snapshotTileUrl(layer: string, z: number, x: number, y: number): string {
  return `${ROOT}tiles/${layer}/${z}/${x}/${y}.png`
}
