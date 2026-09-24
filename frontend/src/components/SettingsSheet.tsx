import { Link } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { Sheet } from './Sheet'
import { Segmented } from './ui'

/**
 * Settings (U4): the controls that had no home on a phone, plus the shortcut
 * switch WCAG 2.1.4 requires (U8). On desktop the theme and motion buttons
 * stay in the header as well; this sheet is the one place all of them live.
 */
export function SettingsSheet() {
  const s = useMission(
    useShallow((m) => ({
      open: m.settingsOpen,
      setOpen: m.setSettingsOpen,
      theme: m.theme,
      setTheme: m.setTheme,
      motion: m.motion,
      setMotion: m.setMotion,
      shortcuts: m.shortcuts,
      setShortcuts: m.setShortcuts,
    })),
  )
  return (
    <Sheet open={s.open} onClose={() => s.setOpen(false)} title="Settings">
      <div className="flex flex-col gap-6 p-5">
        <Setting label="Appearance" note="Both themes pass contrast. The light one is for print and projection.">
          <Segmented
            label="Appearance"
            value={s.theme}
            onChange={s.setTheme}
            options={[
              { value: 'dark', label: 'Dark' },
              { value: 'light', label: 'Light' },
            ]}
          />
        </Setting>
        <Setting label="Motion" note="Every animation has a named static fallback.">
          <Segmented
            label="Motion"
            value={s.motion}
            onChange={s.setMotion}
            options={[
              { value: 'full', label: 'Full' },
              { value: 'reduced', label: 'Reduced' },
            ]}
          />
        </Setting>
        <Setting
          label="Keyboard shortcuts"
          note="Single keys: T reads the chart as a table, 1 2 3 switch the face, [ and ] step the date, Space plays. Turn them off if you use voice control or they get in the way."
        >
          <Segmented
            label="Keyboard shortcuts"
            value={s.shortcuts ? 'on' : 'off'}
            onChange={(v) => s.setShortcuts(v === 'on')}
            options={[
              { value: 'on', label: 'On' },
              { value: 'off', label: 'Off' },
            ]}
          />
        </Setting>
        <div className="flex flex-col gap-2 border-t border-line pt-5">
          <Link
            to="/story"
            onClick={() => s.setOpen(false)}
            className="inline-flex h-12 items-center text-[15px] font-semibold"
          >
            Start here: why the pole is hard →
          </Link>
        </div>
      </div>
    </Sheet>
  )
}

function Setting({ label, note, children }: { label: string; note: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-[15px] font-semibold text-ink">{label}</h3>
      {children}
      <p className="text-[12px] leading-[18px] text-ink-3">{note}</p>
    </div>
  )
}
