import { Tag, type TagKind } from './Tag'

const KINDS: TagKind[] = ['worked out', 'published', 'entered by your team', 'assumed']

/**
 * "Measured, with the margins shown", made visible: under the sentence, the
 * four tags every number in the dashboard wears, drawn as the dashboard draws
 * them, and the one that is not a measurement, the assumed value, with the
 * hatch it always has (.pw-scenario). No example number: a real one is under
 * the idea cards.
 */
export function Margins() {
  return (
    <div className="flex flex-col gap-4 border-t border-line pt-4">
      <p className="text-small leading-5 text-ink-2">Every number says where it came from:</p>
      <ul className="flex flex-wrap gap-x-6 gap-y-3">
        {KINDS.map((k) => (
          <li key={k} className="flex items-center">
            <Tag kind={k} />
          </li>
        ))}
      </ul>
      <p className="pw-scenario self-start rounded-control px-3 py-2 text-small leading-5 text-ink-2">
        An assumed value always looks like this.
      </p>
    </div>
  )
}
