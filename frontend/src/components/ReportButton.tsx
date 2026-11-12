import { Link } from 'react-router-dom'
import { Icon } from './Icon'
import { pillClass } from './ui'

/** The printable report, from the same place on Site, Compare and Plan: the top right of the title. */
export function ReportButton() {
  return (
    <Link to="/report" className={`${pillClass('secondary')} shrink-0`}>
      <Icon name="export" size={16} strokeWidth={2} />
      Report
    </Link>
  )
}
