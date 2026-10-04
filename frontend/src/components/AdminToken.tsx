import { useState } from 'react'
import { LuKeyRound } from 'react-icons/lu'
import { getAdminToken, setAdminToken } from '../lib/api'

/** Changing policy, deciding approvals and running attacks need the admin token.
 *  Kept in this browser only; the demo default (dev-admin) is prefilled. */
export function AdminToken() {
  const [value, setValue] = useState(getAdminToken)
  const [saved, setSaved] = useState(false)
  return (
    <form
      className="ml-auto flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        setAdminToken(value)
        setSaved(true)
        setTimeout(() => setSaved(false), 1500)
      }}
    >
      <LuKeyRound className="text-muted" aria-hidden />
      <input
        type="password"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label="Admin token"
        className="w-36 rounded-md border border-line bg-surface px-2 py-1 font-mono text-xs focus:border-accent focus:outline-none"
      />
      <button type="submit" className="rounded-md border border-line px-2 py-1 text-xs text-muted hover:text-fg">
        {saved ? 'Saved' : 'Save token'}
      </button>
    </form>
  )
}
