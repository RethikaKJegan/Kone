import { X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { useAuthStore } from '../../store/authStore'

export function GuestBanner() {
  const [dismissed, setDismissed] = useState(false)
  const { isGuest } = useAuthStore()

  if (!isGuest || dismissed) return null

  return (
    <div className="flex items-center justify-between gap-4 bg-[#0A0A0A] px-4 py-2.5">
      <p className="text-[13px] text-white/70">
        You're using a guest session. The workflow is fully enabled for demo use.
      </p>
      <div className="flex shrink-0 items-center gap-3">
        <Link
          to="/signup"
          className="rounded-[5px] bg-white px-3 py-1 text-xs font-medium text-[#0A0A0A] transition-colors duration-[120ms] hover:bg-white/90"
        >
          Create account
        </Link>
        <button
          onClick={() => setDismissed(true)}
          aria-label="Dismiss banner"
          className="text-white/30 transition-colors duration-[120ms] hover:text-white/60"
        >
          <X style={{ width: 13, height: 13 }} />
        </button>
      </div>
    </div>
  )
}
