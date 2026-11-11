import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ActivityDTO } from '../../lib/api/experience.types'
import { toast } from '../Toast'
import { finishedScenarios } from './model'

/**
 * A toast when a scenario that was being worked out finishes, with a link
 * back to its answer. Runs once, in the shell, so it is heard on any page.
 */
export function useActivityToasts(data: ActivityDTO | undefined) {
  const navigate = useNavigate()
  const seen = useRef<Set<string>>(new Set())
  useEffect(() => {
    if (!data) return
    for (const item of finishedScenarios(seen.current, data)) {
      const href = item.href
      const name = item.label.replace(/^Scenario:\s*/i, '')
      const where = item.mission_name ? ` for ${item.mission_name}` : ''
      toast(
        item.status === 'done'
          ? `Scenario worked out${where}: ${name}.`
          : `Scenario did not finish${where}: ${name}. ${item.message}`.trim(),
        {
          tone: item.status === 'done' ? 'done' : 'problem',
          action: href ? { label: 'Open', run: () => navigate(href) } : undefined,
        },
      )
    }
    seen.current = new Set(data.active.map((a) => a.key))
  }, [data, navigate])
}
