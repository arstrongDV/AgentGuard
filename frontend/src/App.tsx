import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import { LiveFeed } from './pages/LiveFeed'

// Pages are split into their own chunks; the chart library only loads with the Overview.
const Overview = lazy(() => import('./pages/Overview').then((m) => ({ default: m.Overview })))
const Approvals = lazy(() => import('./pages/Approvals').then((m) => ({ default: m.Approvals })))
const Budgets = lazy(() => import('./pages/Budgets').then((m) => ({ default: m.Budgets })))
const Policy = lazy(() => import('./pages/Policy').then((m) => ({ default: m.Policy })))
const Audit = lazy(() => import('./pages/Audit').then((m) => ({ default: m.Audit })))
const AttackLab = lazy(() => import('./pages/AttackLab').then((m) => ({ default: m.AttackLab })))

function App() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-muted">Loading…</p>}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/overview" replace />} />
          <Route path="overview" element={<Overview />} />
          <Route path="feed" element={<LiveFeed />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="budgets" element={<Budgets />} />
          <Route path="policy" element={<Policy />} />
          <Route path="audit" element={<Audit />} />
          <Route path="lab" element={<AttackLab />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}

export default App
