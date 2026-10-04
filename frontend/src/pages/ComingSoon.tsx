import type { IconType } from 'react-icons'
import { Link } from 'react-router'
import { EmptyState } from '../components/EmptyState'

/** Placeholder for pages planned in frontend/docs/pages-and-ux.md that are not built yet. */
export function ComingSoon({ title, icon, children }: { title: string; icon: IconType; children: string }) {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{title}</h1>
      <EmptyState icon={icon} title="Coming in the next step">
        <p>{children}</p>
        <p className="mt-3">
          Meanwhile, everything is visible in the{' '}
          <Link to="/feed" className="text-accent hover:underline">
            Live Feed
          </Link>
          .
        </p>
      </EmptyState>
    </div>
  )
}
