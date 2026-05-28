import { NavLink, useNavigate, useMatch, Link } from 'react-router-dom'
import { Layers, LogOut, ArrowLeft } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { useOfferingStore } from '../../store/offeringStore'
import { StepProgress } from '../shared/StepProgress'
import { cn } from '../../lib/utils'
import type { OfferingStep } from '../../types'

export function Sidebar() {
  const { user, isGuest, signOut } = useAuthStore()
  const { currentStep, currentOffering, goToStep } = useOfferingStore()
  const navigate = useNavigate()

  const offeringMatch = useMatch('/projects/:projectId/offerings/:offeringId/*')
  const isOfferingWorkflow = !!offeringMatch
  const projectId = offeringMatch?.params.projectId
  const offeringId = offeringMatch?.params.offeringId

  const handleSignOut = () => {
    signOut()
    navigate('/signin')
  }

  const getCompletedSteps = (): OfferingStep[] => {
    if (!currentOffering) return []
    const completed: OfferingStep[] = []
    if (currentOffering.uploadedFileName) completed.push(1)
    if (currentOffering.environments.length > 0 && currentOffering.selectedComponents.length > 0) completed.push(2)
    if (currentOffering.componentPins.length > 0) completed.push(3)
    if (currentOffering.componentPins.length > 0) completed.push(4)
    if (currentOffering.componentPins.length > 0) completed.push(5)
    if (currentOffering.renderComplete) completed.push(6)
    return completed
  }

  const handleStepClick = (step: OfferingStep) => {
    goToStep(step)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/${step}`)
  }

  const completedSteps = getCompletedSteps()

  return (
    <aside className="flex h-screen w-[300px] shrink-0 flex-col bg-[#0C0C0C] max-xl:w-14" style={{ borderRight: '1px solid rgba(255,255,255,0.07)' }}>
      {/* Branding */}
      <div className="flex h-[60px] items-center gap-2.5 px-5" style={{ borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
        <Link to="/" style={{ fontSize: 16, fontWeight: 900, letterSpacing: '-0.02em', color: '#1450F5', textDecoration: 'none' }}>KONE</Link>
        <div style={{ width: 1, height: 14, background: 'rgba(255,255,255,0.1)', flexShrink: 0 }} className="max-xl:hidden" />
        <span style={{ fontSize: 13, fontWeight: 500, color: 'rgba(255,255,255,0.45)', letterSpacing: '0.01em' }} className="max-xl:hidden">SalesNXT</span>
      </div>

      {isOfferingWorkflow ? (
        /* Offering workflow: show step progress */
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="px-3 pt-3 max-xl:hidden">
            <Link
              to={`/projects/${projectId}`}
              className="flex items-center gap-2 rounded-[6px] px-3 py-2 transition-all duration-150 hover:bg-white/[0.06]"
              style={{ fontSize: 12, fontWeight: 500, color: 'rgba(255,255,255,0.45)' }}
              onMouseEnter={e => (e.currentTarget.style.color = '#1450F5')}
              onMouseLeave={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.45)')}
            >
              <ArrowLeft style={{ width: 13, height: 13 }} />
              Back to Project
            </Link>
          </div>

          <div className="mt-4 px-5 max-xl:hidden">
            <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(20,80,245,0.7)' }}>
              Steps
            </p>
          </div>

          <div className="mt-2 flex-1 overflow-y-auto max-xl:hidden">
            <StepProgress
              currentStep={currentStep}
              completedSteps={completedSteps}
              onStepClick={handleStepClick}
            />
          </div>

          {/* Collapsed view: show step number only */}
          <div className="hidden max-xl:flex max-xl:flex-1 max-xl:flex-col max-xl:items-center max-xl:py-2 max-xl:gap-1">
            {([1, 2, 3, 4, 5, 6] as OfferingStep[]).map(step => {
              const isCompleted = completedSteps.includes(step)
              const isCurrent = step === currentStep
              return (
                <button
                  key={step}
                  onClick={() => (isCompleted || isCurrent) && handleStepClick(step)}
                  className={cn(
                    'flex h-7 w-7 items-center justify-center rounded-full border text-[10px] font-bold transition-all duration-150',
                    isCompleted
                      ? 'border-[#16A34A] bg-[#16A34A] text-white'
                      : isCurrent
                        ? 'border-[#1450F5] bg-[#1450F5] text-white shadow-[0_0_10px_rgba(20,80,245,0.5)]'
                        : 'border-white/20 text-white/30'
                  )}
                >
                  {step}
                </button>
              )
            })}
          </div>
        </div>
      ) : (
        /* Normal nav */
        <nav className="flex-1 space-y-0.5 p-3">
          <NavLink
            to="/projects"
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-[6px] px-3 transition-all duration-150',
                isActive
                  ? 'bg-[#1450F5]/15 text-[#1450F5] font-semibold'
                  : 'text-white/50 hover:bg-white/[0.06] hover:text-white/80'
              )
            }
            style={{ height: 38, fontSize: 14 }}
            aria-label="Projects"
          >
            <Layers className="shrink-0" style={{ width: 15, height: 15 }} />
            <span className="max-xl:hidden">Projects</span>
          </NavLink>
        </nav>
      )}

      {user && (
        <div className="p-4" style={{ borderTop: '1px solid rgba(255,255,255,0.07)' }}>
          <div className="flex items-center gap-2.5">
            <div
              className="flex shrink-0 items-center justify-center rounded-full bg-[#1450F5]/20"
              style={{ width: 32, height: 32, fontSize: 12, fontWeight: 700, color: '#1450F5' }}
              aria-label={`User avatar for ${user.name}`}
            >
              {user.avatarInitials}
            </div>
            <div className="flex-1 min-w-0 max-xl:hidden">
              <p className="truncate font-semibold text-white/85" style={{ fontSize: 13 }}>{user.name}</p>
              <p className="truncate text-white/35" style={{ fontSize: 11, marginTop: 1 }}>
                {isGuest ? 'Guest session' : user.email}
              </p>
            </div>
            <button
              onClick={handleSignOut}
              aria-label="Sign out"
              title="Sign out"
              className="flex shrink-0 items-center justify-center rounded-[5px] text-white/30 hover:bg-white/[0.06] hover:text-[#1450F5] transition-colors duration-150"
              style={{ width: 26, height: 26 }}
            >
              <LogOut style={{ width: 13, height: 13 }} />
            </button>
          </div>
        </div>
      )}
    </aside>
  )
}
