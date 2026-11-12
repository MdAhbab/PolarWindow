/**
 * A site's two shares as a small ring: the outer arc is the time the Sun is up
 * (amber), the inner arc the time Earth is in view (cyan), each from the top,
 * clockwise. A picture beside the words, never in place of them.
 */
export function ShareRing({ sun, earth, size = 30 }: { sun: number; earth: number; size?: number }) {
  const arc = (r: number, f: number, color: string) => {
    const c = 2 * Math.PI * r
    const v = Math.max(0, Math.min(1, f))
    return (
      <>
        <circle r={r} fill="none" stroke="var(--color-line)" strokeWidth="3" />
        <circle
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeDasharray={`${v * c} ${c}`}
          transform="rotate(-90)"
          strokeLinecap="butt"
        />
      </>
    )
  }
  return (
    <svg width={size} height={size} viewBox="-15 -15 30 30" aria-hidden="true" className="shrink-0">
      {arc(12, sun, 'var(--color-sun-fill)')}
      {arc(7.5, earth, 'var(--color-earth-fill)')}
    </svg>
  )
}
