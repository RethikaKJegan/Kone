import { Outlet, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { Sidebar } from './Sidebar'
import { GuestBanner } from './GuestBanner'

export function AppShell() {
  const location = useLocation()

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'auto' })
  }, [location.pathname])

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#F7F7F7]">
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
