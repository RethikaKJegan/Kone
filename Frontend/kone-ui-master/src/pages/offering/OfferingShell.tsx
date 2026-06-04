import { useEffect, Suspense, lazy } from 'react'
import { Home } from 'lucide-react'
import { useParams, Routes, Route, Navigate, Link, useLocation, useNavigate } from 'react-router-dom'
import { useOfferingStore } from '../../store/offeringStore'
import { useProjectStore } from '../../store/projectStore'
import { TopBar } from '../../components/layout/TopBar'
import { Skeleton } from '../../components/ui/skeleton'

const Step1 = lazy(() => import('./steps/Step1Upload'))
const Step2 = lazy(() => import('./steps/Step2Components'))
const Step3 = lazy(() => import('./steps/Step3Place'))
const Step4 = lazy(() => import('./steps/Step4Repin'))
const Step5 = lazy(() => import('./steps/Step5Video'))
const Step6 = lazy(() => import('./steps/Step6Download'))

export default function OfferingShell() {
  const { projectId, offeringId } = useParams<{ projectId: string; offeringId: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const { offerings, currentOffering, currentStep, fetchOfferings, setCurrentOffering, goToStep } = useOfferingStore()
  const { projects } = useProjectStore()

  const project = projects.find(p => p.id === projectId)
  const projectOfferings = projectId ? (offerings[projectId] ?? []) : []

  useEffect(() => {
    if (projectId && projectOfferings.length === 0) {
      fetchOfferings(projectId)
    }
  }, [projectId, projectOfferings.length, fetchOfferings])

  useEffect(() => {
    if (!currentOffering && offeringId) {
      const found = projectOfferings.find(o => o.id === offeringId)
      if (found) setCurrentOffering(found)
    }
  }, [currentOffering, offeringId, projectOfferings, setCurrentOffering])

  useEffect(() => {
    const match = location.pathname.match(/\/step\/([1-6])$/)
    const step = match ? Number(match[1]) : null
    const savedStep = currentOffering?.savedStep
    if (step === 1 && savedStep && savedStep > 1 && currentStep === savedStep) {
      navigate(`/projects/${projectId}/offerings/${offeringId}/step/${savedStep}`, { replace: true })
      return
    }
    if (step && step !== currentStep) {
      goToStep(step as 1 | 2 | 3 | 4 | 5 | 6)
    }
  }, [currentOffering?.savedStep, currentStep, goToStep, location.pathname, navigate, offeringId, projectId])

  const crumbs = [
    { label: 'All Projects', to: '/projects' },
    { label: project?.name ?? 'Project', to: `/projects/${projectId}` },
    { label: currentOffering?.name ?? 'New Visualization' },
  ]

  return (
    <div className="flex flex-col min-h-full">
      <TopBar crumbs={crumbs} />
      <div className="mx-auto max-w-4xl w-full px-6 pb-8 pt-6">
        <div className="mb-4 flex justify-end">
          <Link
            to="/projects"
            onClick={() => goToStep(currentStep)}
            className="inline-flex items-center gap-2 rounded-lg border border-[#E4E4E4] bg-white px-3 text-xs font-semibold text-[#374151] transition-colors duration-[120ms] hover:border-[#1450F5]/40 hover:text-[#1450F5]"
            style={{ height: 34 }}
          >
            <Home style={{ width: 13, height: 13 }} />
            Back to Home
          </Link>
        </div>
        <Suspense fallback={<Skeleton className="h-80 rounded-lg" />}>
          <Routes>
            <Route path="step/1" element={<Step1 />} />
            <Route path="step/2" element={<Step2 />} />
            <Route path="step/3" element={<Step3 />} />
            <Route path="step/4" element={<Step4 />} />
            <Route path="step/5" element={<Step5 />} />
            <Route path="step/6" element={<Step6 />} />
            <Route index element={<Navigate to={`step/${currentOffering?.savedStep ?? currentStep ?? 1}`} replace />} />
          </Routes>
        </Suspense>
      </div>
    </div>
  )
}
