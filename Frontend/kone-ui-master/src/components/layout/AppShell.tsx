import { Outlet, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { Sidebar } from './Sidebar'
import { GuestBanner } from './GuestBanner'
import { useAuthStore } from '../../store/authStore'

export function AppShell() {
  const location = useLocation()
  const resetGuestBanner = useAuthStore(s => s.resetGuestBanner)

  useEffect(() => {
    resetGuestBanner()
  }, [location.pathname, resetGuestBanner])

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#F5F6F8]">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        <GuestBanner />
        <div className="flex-1 overflow-auto">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
