import { useEffect, Suspense, lazy, useState } from 'react'
import { Home } from 'lucide-react'
import { useParams, Routes, Route, Navigate, Link, useLocation, useNavigate } from 'react-router-dom'
import apiClient from '../../api/client'
import { useOfferingStore } from '../../store/offeringStore'
import { useProjectStore } from '../../store/projectStore'
import { TopBar } from '../../components/layout/TopBar'
import { Skeleton } from '../../components/ui/skeleton'
import { toast } from '../../hooks/useToast'
import type { Offering, OfferingStep } from '../../types'

const Step1 = lazy(() => import('./steps/Step1Upload'))
const Step2 = lazy(() => import('./steps/Step2Components'))
const Step3 = lazy(() => import('./steps/Step3Place'))
const Step4 = lazy(() => import('./steps/Step4Repin'))
const Step5 = lazy(() => import('./steps/Step5Video'))
const Step6 = lazy(() => import('./steps/Step6Download'))

function stepFromPath(pathname: string): OfferingStep | null {
  const step = Number(pathname.split('/step/').pop())
  return step >= 1 && step <= 6 ? (step as OfferingStep) : null
}

export default function OfferingShell() {
  const { projectId, offeringId } = useParams<{ projectId: string; offeringId: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const { offerings, currentOffering, currentStep, fetchOfferings, setCurrentOffering, goToStep } = useOfferingStore()
  const requestedStep = stepFromPath(location.pathname)
  const { projects } = useProjectStore()
  const [loadingOffering, setLoadingOffering] = useState(false)

  const project = projects.find(p => p.id === projectId)
  const projectOfferings = projectId ? (offerings[projectId] ?? []) : []
  const activeOffering = currentOffering && currentOffering.id === offeringId && currentOffering.projectId === projectId
    ? currentOffering
    : null

  useEffect(() => {
    if (projectId && projectOfferings.length === 0) {
      fetchOfferings(projectId)
    }
  }, [projectId, projectOfferings.length, fetchOfferings])

  useEffect(() => {
    let cancelled = false
    async function loadOffering() {
      if (!projectId || !offeringId) return
      if (currentOffering?.id === offeringId && currentOffering.projectId === projectId) return

      const found = projectOfferings.find(o => o.id === offeringId)
      if (found) {
        setCurrentOffering({ ...found, savedStep: requestedStep ?? found.savedStep ?? 1 })
        return
      }

      setLoadingOffering(true)
      try {
        const { data } = await apiClient.get<Offering>(`/offerings/${offeringId}`)
        if (cancelled) return
        if (data.projectId !== projectId) {
          toast('This visualization does not belong to the selected project.', 'destructive')
          navigate(`/projects/${projectId}`, { replace: true })
          return
        }
        setCurrentOffering({ ...data, savedStep: requestedStep ?? data.savedStep ?? 1 })
      } catch {
        if (!cancelled) {
          toast('Visualization not found.', 'destructive')
          navigate(`/projects/${projectId}`, { replace: true })
        }
      } finally {
        if (!cancelled) setLoadingOffering(false)
      }
    }
    loadOffering()
    return () => {
      cancelled = true
    }
  }, [currentOffering?.id, currentOffering?.projectId, offeringId, projectId, projectOfferings, requestedStep, setCurrentOffering, navigate])

  useEffect(() => {
    const step = requestedStep
    if (!activeOffering) return
    const savedStep = activeOffering.savedStep
    if (step === 1 && savedStep && savedStep > 1 && currentStep === savedStep) {
      navigate(`/projects/${projectId}/offerings/${offeringId}/step/${savedStep}`, { replace: true })
      return
    }
    if (step && step !== currentStep) {
      goToStep(step as 1 | 2 | 3 | 4 | 5 | 6)
    }
  }, [activeOffering, currentStep, goToStep, requestedStep, navigate, offeringId, projectId])

  const crumbs = [
    { label: 'All Projects', to: '/projects' },
    { label: project?.name ?? 'Project', to: `/projects/${projectId}` },
    { label: activeOffering?.name ?? 'New Visualization' },
  ]

  if (!activeOffering || loadingOffering) {
    return (
      <div className="flex flex-col min-h-full">
        <TopBar crumbs={crumbs} />
        <div className="mx-auto max-w-4xl w-full px-6 pb-8 pt-6">
          <Skeleton className="h-80 rounded-lg" />
        </div>
      </div>
    )
  }

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
            <Route index element={<Navigate to={`step/${activeOffering.savedStep ?? currentStep ?? 1}`} replace />} />
          </Routes>
        </Suspense>
      </div>
    </div>
  )
}
