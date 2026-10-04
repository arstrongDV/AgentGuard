import { LuFileDown, LuGauge, LuLayoutDashboard, LuSlidersHorizontal } from 'react-icons/lu'
import { Navigate, Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import { Approvals } from './pages/Approvals'
import { ComingSoon } from './pages/ComingSoon'
import { LiveFeed } from './pages/LiveFeed'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/feed" replace />} />
        <Route path="feed" element={<LiveFeed />} />
        <Route path="approvals" element={<Approvals />} />
        <Route
          path="overview"
          element={
            <ComingSoon title="Overview" icon={LuLayoutDashboard}>
              Posture at a glance: requests, % blocked and redacted, top threat categories and p50/p95 latency per check.
            </ComingSoon>
          }
        />
        <Route
          path="budgets"
          element={
            <ComingSoon title="Budgets" icon={LuGauge}>
              Token and cost spend per agent and model against its daily limits, plus rate-limit and loop blocks.
            </ComingSoon>
          }
        />
        <Route
          path="policy"
          element={
            <ComingSoon title="Policy" icon={LuSlidersHorizontal}>
              Monitor / enforce switch, strictness per agent and the live policy.yaml, all written back to the file.
            </ComingSoon>
          }
        />
        <Route
          path="audit"
          element={
            <ComingSoon title="Audit export" icon={LuFileDown}>
              Filter the audit log and download it as CSV or JSONL for the security team.
            </ComingSoon>
          }
        />
        <Route path="*" element={<Navigate to="/feed" replace />} />
      </Route>
    </Routes>
  )
}

export default App
