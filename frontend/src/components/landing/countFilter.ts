/**
 * The two numbers on the front page. They come from the API's own lists, and
 * count only what the product ships with: a project somebody added in the
 * dashboard (origin "project", which the audit's test projects are too) is not
 * a CLPS mission, and the site it brings is not a candidate.
 */
export function catalogueMissionCount(items: readonly { origin?: 'catalogue' | 'project' }[]): number {
  return items.filter((m) => m.origin !== 'project').length
}

export function candidateSiteCount(items: readonly { site: { id: string; kind: string } }[]): number {
  return items.filter((i) => i.site.kind === 'candidate' && !i.site.id.startsWith('project-')).length
}
