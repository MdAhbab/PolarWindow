/**
 * Ground-station names for people, plain words first and the station code second
 * ("DSS-14 (70-meter)" reads "Goldstone, 70 m dish (DSS-14)"). A display map over the
 * catalogue's names: the data keeps its own, and a name that is not one of these is
 * shown as it is.
 */

/** The complex each Deep Space Network antenna belongs to, by the first digit of its number. */
const COMPLEX: Record<string, string> = { '1': 'Goldstone', '2': 'Goldstone', '3': 'Canberra', '4': 'Canberra', '5': 'Madrid', '6': 'Madrid' }

const CATALOGUE_NAME = /^(DSS-(\d)\d)\s*\((\d+)-(?:meter|m)(?:\s+([A-Z]+))?\)$/

export function stationName(name: string): string {
  const m = CATALOGUE_NAME.exec(name)
  if (!m) return name
  const [, code, group, size, kind] = m
  const place = COMPLEX[group]
  if (!place) return name
  return `${place}, ${size} m dish (${code}${kind ? `, ${kind}` : ''})`
}
