/**
 * API names, in words, for the places the AI's workings are shown: the
 * "Numbers used" table, the Ask answer's rows and the activity log. The value
 * beside a name is always printed exactly as the API sent it, so the unit is
 * named rather than converted.
 */

const TOOLS: Record<string, string> = {
  get_site: 'Site details',
  get_metrics: 'Site numbers',
  get_windows: 'Sunlight and contact times',
  get_horizon_profile: 'Skyline',
  search_sites: 'Site search',
  compare_sites: 'Site comparison',
  user_request: 'Your request',
}

const NAMES: Record<string, string> = {
  sunlit: 'time in sunlight',
  sunlit_tolerance: 'margin on time in sunlight',
  sunlit_full_disc: 'time with the whole Sun up',
  sunlit_any_limb: 'time with any of the Sun up',
  earth_contact: 'time in contact with Earth',
  earth_contact_tolerance: 'margin on contact with Earth',
  earth_contact_full_disc: 'contact, whole Earth up',
  earth_contact_any_limb: 'contact, any of Earth up',
  longest_dark: 'longest night',
  longest_dark_tolerance: 'margin on the longest night',
  longest_blackout: 'longest time without contact',
  longest_blackout_tolerance: 'margin on the longest time without contact',
  worst_compound: 'longest time dark and out of contact',
  required_autonomy: 'time working alone',
  survival_needed: 'battery time needed',
  max_el: 'highest skyline',
  max_el_bearing: 'direction of the highest skyline',
  mean_el: 'average skyline height',
  elev: 'height',
  lat: 'latitude',
  lon: 'longitude',
  rank: 'rank',
}

const UNITS: [RegExp, string][] = [
  [/_s$/, 'seconds'],
  [/_deg$/, 'degrees'],
  [/_m$/, 'metres'],
  [/_h$/, 'hours'],
  [/_pct$/, 'percent'],
]

/** `longest_dark_s` → "longest night (seconds)"; an unknown name loses its underscores. */
export function fieldWords(key: string): string {
  for (const [re, unit] of UNITS) {
    if (re.test(key)) {
      const base = key.replace(re, '')
      return `${NAMES[base] ?? base.replace(/_/g, ' ')} (${unit})`
    }
  }
  return NAMES[key] ?? key.replace(/_/g, ' ')
}

export function toolWords(tool: string): string {
  return TOOLS[tool] ?? tool.replace(/_/g, ' ')
}
