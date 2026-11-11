import { Disclosure } from '../ui'

/** A control that would write to the mission's record, held back while a scenario is shown, with the reason. */
export function HeldRow({ title, what }: { title: string; what: string }) {
  return (
    <Disclosure title={title} meta="not offered on a scenario">
      <p className="text-body leading-6 text-ink-2">
        {what} A scenario never writes to the record, so this is left out here. Leave the scenario to use it.
      </p>
    </Disclosure>
  )
}
