import { useId, useState } from 'react'
import { Icon } from '../Icon'
import { useAsk } from '../ask/store'

/**
 * Ask, front and centre: a question typed here, or a suggestion pressed,
 * opens the Ask dock with those words. The answer is the dock's, with the
 * same grounding as every AI answer in the app.
 */
export function AskBar({ suggestions }: { suggestions: string[] }) {
  const [text, setText] = useState('')
  const open = useAsk((s) => s.open)
  const id = useId()
  const send = (t: string) => {
    open(t)
    setText('')
  }
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <form
        role="search"
        aria-label="Ask"
        onSubmit={(e) => {
          e.preventDefault()
          send(text)
        }}
        className="pw-card flex min-h-16 items-center gap-2 py-2 pr-2 pl-4 has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-[7px] has-[input:focus-visible]:outline-focus"
      >
        <Icon name="ask" size={20} strokeWidth={1.8} className="shrink-0 text-ink-3" />
        <label htmlFor={id} className="sr-only">
          Ask about a mission, a site or a date
        </label>
        <input
          id={id}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ask about a mission, a site or a date"
          autoComplete="off"
          className="h-12 min-w-0 grow bg-transparent text-lede text-ink placeholder:text-ink-3 focus-visible:outline-none"
        />
        <kbd
          aria-hidden="true"
          className="hidden h-7 min-w-7 items-center justify-center rounded-control border border-line-strong px-2 font-mono text-caption text-ink-3 lg:inline-flex"
        >
          /
        </kbd>
        <button
          type="submit"
          className="pw-press inline-flex h-12 shrink-0 items-center rounded-pill bg-ink px-5 text-control font-semibold text-canvas hover:bg-ink-2"
        >
          Ask
        </button>
      </form>
      {suggestions.length > 0 && (
        <ul aria-label="Questions to start with" className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <li key={s}>
              <button
                type="button"
                onClick={() => send(s)}
                className="pw-press inline-flex min-h-11 items-center rounded-pill border border-line-strong bg-tray px-4 py-2 text-left text-body text-ink-2 hover:bg-inset hover:text-ink"
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
