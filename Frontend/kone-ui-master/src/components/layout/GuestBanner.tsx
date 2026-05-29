import { X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

export function GuestBanner() {
  const { isGuest, guestBannerDismissed, dismissGuestBanner } = useAuthStore()

  if (!isGuest || guestBannerDismissed) return null

  return (
    <div className="flex items-center justify-between gap-4 bg-[#0A0A0A] px-4 py-2.5">
      <p className="text-[13px] text-white/70">
        You're browsing as a guest. Your work is saved for this session only.
      </p>
      <div className="flex items-center gap-3 shrink-0">
        <Link
          to="/signup"
          className="rounded-[5px] bg-white px-3 py-1 text-xs font-medium text-[#0A0A0A] transition-colors duration-[120ms] hover:bg-white/90"
        >
          Sign up to save permanently
        </Link>
        <Link
          to="/signin"
          className="text-[13px] text-[#A3A3A3] transition-colors duration-[120ms] hover:text-white"
        >
          Sign in
        </Link>
        <button
          onClick={dismissGuestBanner}
          aria-label="Dismiss banner"
          className="text-white/30 transition-colors duration-[120ms] hover:text-white/60"
        >
          <X style={{ width: 13, height: 13 }} />
        </button>
      </div>
    </div>
  )
}
