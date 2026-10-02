import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Icon } from './Icon'

export interface Choice<T extends string = string> {
  value: T
  label: string
  /** Options that share a group are listed together under its name. */
  group?: string
}

/**
 * A box that offers a list to choose one thing from, drawn by the page.
 *
 * The browser's own `<select>` opens a list drawn by the operating system,
 * which ignores the theme and looks different on every machine. This is the
 * same control built from a button and a list: the button says what is chosen,
 * the list opens under it (or over it when there is no room below) in the
 * page's own colours.
 *
 * It behaves as the native one does. Focus stays on the button; the arrow
 * keys, Home, End and typing a name move through the list; Enter, Space or
 * Tab choose; Esc closes without choosing. A `<label for>` names it as it
 * would a native select. The list is put in the browser's top layer, so it is
 * never cut off by a scrolling panel and it opens above a sheet.
 */
/** Whether the browser can put the list in its top layer; without that it is drawn fixed, over the page. */
const TOP_LAYER = typeof HTMLElement !== 'undefined' && 'showPopover' in HTMLElement.prototype

const LOOKS = {
  /** A form field (the project manager's forms). */
  field:
    'h-12 w-full rounded-control border border-field bg-panel pr-3 pl-3.5 text-body text-ink hover:border-ink-3 aria-expanded:border-focus aria-invalid:border-alert',
  /** A control on a page, beside the pills. */
  pill: 'h-12 rounded-pill border border-line-strong bg-tray pr-4 pl-5 text-control text-ink hover:border-ink-3 aria-expanded:border-ink-3',
  /** No box of its own: the caller draws it. */
  bare: '',
} as const

export function Select<T extends string = string>({
  id,
  value,
  onChange,
  options,
  placeholder = 'Choose…',
  disabled = false,
  look = 'field',
  className = '',
  labelClassName = '',
  chevron = 18,
  'aria-label': ariaLabel,
  'aria-describedby': describedBy,
  'aria-invalid': invalid,
}: {
  id?: string
  value: T | ''
  onChange: (value: T) => void
  options: Choice<T>[]
  /** Shown while nothing is chosen. */
  placeholder?: string
  disabled?: boolean
  look?: keyof typeof LOOKS
  className?: string
  /** For the chosen option's name on the button. */
  labelClassName?: string
  /** The chevron's size, px. */
  chevron?: number
  'aria-label'?: string
  'aria-describedby'?: string
  'aria-invalid'?: boolean
}) {
  const ownId = useId()
  const buttonId = id ?? ownId
  const listId = `${ownId}-list`
  const optionId = (i: number) => `${ownId}-o${i}`
  const buttonRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [listName, setListName] = useState('')
  const typed = useRef({ text: '', at: 0 })
  // Only a move made with the keyboard scrolls the list; the pointer is already where it points.
  const byKey = useRef(false)

  const chosen = options.findIndex((o) => o.value === value)
  const current = chosen >= 0 ? options[chosen] : undefined

  const show = (at?: number) => {
    if (disabled || options.length === 0) return
    const b = buttonRef.current
    setListName(ariaLabel ?? b?.labels?.[0]?.textContent ?? '')
    byKey.current = true
    setActive(at ?? Math.max(0, chosen))
    setOpen(true)
  }
  const close = () => setOpen(false)
  const choose = (i: number) => {
    const o = options[i]
    close()
    if (o && o.value !== value) onChange(o.value)
  }
  const move = (i: number) => {
    byKey.current = true
    setActive(Math.max(0, Math.min(options.length - 1, i)))
  }

  // Place the list against the button: under it, or over it when the room below is short.
  useLayoutEffect(() => {
    if (!open) return
    const list = listRef.current
    const b = buttonRef.current
    if (!list || !b) return
    try {
      if (TOP_LAYER) list.showPopover()
    } catch {
      // Already shown.
    }
    const place = () => {
      const r = b.getBoundingClientRect()
      const vw = window.innerWidth
      const vh = window.innerHeight
      const below = vh - r.bottom - 14
      const above = r.top - 14
      list.style.maxHeight = ''
      const want = Math.min(list.scrollHeight + 2, 340)
      const up = below < Math.min(want, 180) && above > below
      list.style.maxHeight = `${Math.max(96, Math.min(340, up ? above : below))}px`
      list.style.minWidth = `${Math.min(r.width, vw - 16)}px`
      list.style.left = `${Math.max(8, Math.min(r.left, vw - list.offsetWidth - 8))}px`
      list.style.top = up ? 'auto' : `${r.bottom + 6}px`
      list.style.bottom = up ? `${vh - r.top + 6}px` : 'auto'
    }
    place()
    const onScroll = (e: Event) => {
      if (e.target !== list) place()
    }
    const onPress = (e: PointerEvent) => {
      const t = e.target as Node
      if (!list.contains(t) && !b.contains(t)) close()
    }
    window.addEventListener('resize', place)
    window.addEventListener('scroll', onScroll, { capture: true, passive: true })
    document.addEventListener('pointerdown', onPress, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', onScroll, { capture: true })
      document.removeEventListener('pointerdown', onPress, true)
    }
  }, [open, options.length])

  useEffect(() => {
    if (!open || active < 0 || !byKey.current) return
    document.getElementById(optionId(active))?.scrollIntoView?.({ block: 'nearest' })
    // optionId is built from a stable id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, active])

  /** The next option, after the active one, whose name starts with what was typed. */
  const find = (ch: string) => {
    const now = Date.now()
    const t = typed.current
    t.text = now - t.at > 700 ? ch : t.text + ch
    t.at = now
    const from = t.text.length === 1 ? active + 1 : Math.max(0, active)
    for (let k = 0; k < options.length; k++) {
      const i = (from + k) % options.length
      if (options[i].label.toLowerCase().startsWith(t.text.toLowerCase())) return i
    }
    return -1
  }

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return
    const last = options.length - 1
    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
        e.preventDefault()
        show()
      } else if (e.key === 'Home' || e.key === 'End') {
        e.preventDefault()
        show(e.key === 'Home' ? 0 : last)
      } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const i = find(e.key)
        if (i >= 0) show(i)
      }
      return
    }
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        move(active + 1)
        break
      case 'ArrowUp':
        e.preventDefault()
        if (e.altKey) choose(active)
        else move(active - 1)
        break
      case 'Home':
        e.preventDefault()
        move(0)
        break
      case 'End':
        e.preventDefault()
        move(last)
        break
      case 'PageDown':
        e.preventDefault()
        move(active + 8)
        break
      case 'PageUp':
        e.preventDefault()
        move(active - 8)
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        choose(active)
        break
      case 'Tab':
        choose(active)
        break
      case 'Escape':
        // The list closes; a sheet it is in stays open.
        e.preventDefault()
        e.stopPropagation()
        close()
        break
      default:
        if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
          const i = find(e.key)
          if (i >= 0) move(i)
        }
    }
  }

  // Runs of options with the same group, in the order given.
  const runs: { group?: string; from: number; to: number }[] = []
  options.forEach((o, i) => {
    const r = runs[runs.length - 1]
    if (r && r.group === o.group) r.to = i + 1
    else runs.push({ group: o.group, from: i, to: i + 1 })
  })

  const option = (o: Choice<T>, i: number) => (
    <div
      key={o.value}
      id={optionId(i)}
      role="option"
      aria-selected={i === chosen}
      data-active={i === active || undefined}
      onClick={() => choose(i)}
      onPointerMove={() => {
        if (i !== active) {
          byKey.current = false
          setActive(i)
        }
      }}
      className="pw-menu-option"
    >
      <span className="min-w-0 grow">{o.label}</span>
      {i === chosen && <Icon name="check" size={16} strokeWidth={2.2} className="shrink-0" />}
    </div>
  )

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        id={buttonId}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open && active >= 0 ? optionId(active) : undefined}
        aria-label={ariaLabel}
        aria-describedby={describedBy}
        aria-invalid={invalid}
        disabled={disabled}
        onClick={() => (open ? close() : show())}
        onKeyDown={onKeyDown}
        onBlur={close}
        className={`inline-flex min-w-0 max-w-full cursor-pointer items-center justify-between gap-2 text-left disabled:cursor-not-allowed disabled:text-ink-3 ${LOOKS[look]} ${className}`}
      >
        <span className={`min-w-0 truncate ${current ? '' : 'text-ink-3'} ${labelClassName}`}>
          {current ? current.label : placeholder}
        </span>
        <Icon
          name="chevron"
          size={chevron}
          strokeWidth={2.2}
          className={`shrink-0 text-ink-3 transition-transform duration-[var(--pw-dur-quick)] ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div
          ref={listRef}
          id={listId}
          role="listbox"
          aria-label={listName || 'Options'}
          popover={TOP_LAYER ? 'manual' : undefined}
          className="pw-menu"
          // Pressing in the list must not take focus off the button.
          onMouseDown={(e) => e.preventDefault()}
        >
          {runs.map((r) =>
            r.group ? (
              <div key={r.group} role="group" aria-labelledby={`${ownId}-g${r.from}`}>
                <div id={`${ownId}-g${r.from}`} role="presentation" className="pw-menu-group">
                  {r.group}
                </div>
                {options.slice(r.from, r.to).map((o, k) => option(o, r.from + k))}
              </div>
            ) : (
              options.slice(r.from, r.to).map((o, k) => option(o, r.from + k))
            ),
          )}
        </div>
      )}
    </>
  )
}
