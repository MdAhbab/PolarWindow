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
  list_missions: 'Mission list',
  get_mission_sections: 'A mission’s sections',
  get_mission_section: 'One section of a mission',
  get_space_weather: 'Space weather now',
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
  sunlight: 'time in sunlight',
  heard: 'time a ground station can hear it',
  longest_shadow: 'longest time in shadow',
  longest_unheard: 'longest time without contact',
  station_hears: 'time a ground station can hear the lander',
  via_relay: 'time through a relay',
  either: 'time in contact either way',
  direct: 'time in contact with Earth',
  longest_message_wait: 'longest message wait',
  dark_and_unheard: 'time dark and out of contact at once',
  flight_days: 'flight time',
  orbit_wait_days: 'wait in orbit around the Moon',
  sun_elevation: 'Sun height',
  sunlight_after: 'sunlight after landing',
  wave_height: 'wave height',
  wind: 'wind speed',
  belt_hours: 'time in the radiation belts',
}

const UNITS: [RegExp, string][] = [
  // Longest first: "wind_m_s" is a speed, not "wind m" in seconds.
  [/_km_s$/, 'kilometres a second'],
  [/_m_s$/, 'metres a second'],
  [/_mgy_d$/, 'milligray a day'],
  [/_mgy$/, 'milligray'],
  [/_nt$/, 'nanotesla'],
  [/_s$/, 'seconds'],
  [/_deg$/, 'degrees'],
  [/_m$/, 'metres'],
  [/_h$/, 'hours'],
  [/_min$/, 'minutes'],
  [/_days$/, 'days'],
  [/_km$/, 'kilometres'],
  [/_pct$/, 'percent'],
]

const PART_OF: Record<string, string> = { pm: 'margin on ', lo: 'low end of ', hi: 'high end of ', factor: 'factor on ' }

/**
 * `longest_dark_s` → "longest night (seconds)"; an unknown name loses its
 * underscores. A path into a mission section or the space weather
 * (`data.booster.wave_height_m.value`) reads as the field with where it sits:
 * "booster: wave height (metres)"; a list item keeps its place ("opportunities 3").
 */
export function fieldWords(key: string): string {
  if (!/[.[]/.test(key)) return flatWords(key)
  const parts = key.split('.').filter(Boolean)
  if (parts[0] === 'data') parts.shift()
  let prefix = ''
  const tail = parts[parts.length - 1]
  if (parts.length > 1 && (tail === 'value' || tail in PART_OF)) {
    prefix = PART_OF[tail] ?? ''
    parts.pop()
  }
  const place = (p: string) => p.replace(/_/g, ' ').replace(/\[(\d+)\]/g, (_, i: string) => ` ${Number(i) + 1}`)
  const last = parts.pop() ?? key
  const name = last.replace(/\[(\d+)\]/g, '')
  const at = last.match(/\[(\d+)\]/)
  const words = `${prefix}${flatWords(name)}${at ? ` ${Number(at[1]) + 1}` : ''}`
  return parts.length ? `${parts.map(place).join(', ')}: ${words}` : words
}

function flatWords(key: string): string {
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

/**
 * The word a `verdict_word` guard caught, from its detail ("'safe' in
 * summary is a verdict. …"); null when the detail does not quote one.
 */
export function verdictWord(detail: string | undefined | null): string | null {
  const m = detail?.match(/^'([^']+)'/)
  return m ? m[1] : null
}
