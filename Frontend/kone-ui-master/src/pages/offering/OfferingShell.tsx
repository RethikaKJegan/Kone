import { useEffect, useMemo, useRef, useState } from 'react'
import { Home, RefreshCw } from 'lucide-react'
import { cn } from '../../lib/utils'
import { useParams, Routes, Route, Navigate, Link, useLocation, useNavigate } from 'react-router-dom'
import apiClient from '../../api/client'
import { useOfferingStore } from '../../store/offeringStore'
import { useProjectStore } from '../../store/projectStore'
import { TopBar } from '../../components/layout/TopBar'
import { Skeleton } from '../../components/ui/skeleton'
import { SystemIssue } from '../../components/shared/SystemIssue'
import { toast } from '../../hooks/useToast'
import { safeSystemErrorMessage } from '../../lib/safeErrors'
import type { Offering, OfferingStep } from '../../types'
import Step1 from './steps/Step1Upload'
import Step2 from './steps/Step2Components'
import Step3 from './steps/Step3Place'
import Step4 from './steps/Step4Repin'
import Step5 from './steps/Step5Video'
import Step6 from './steps/Step6Download'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

const LOAD_TIMEOUT_MS = 15000

function stepFromPath(pathname: string): OfferingStep | null {
  const step = Number(pathname.split('/step/').pop())
  return step >= 1 && step <= 6 ? (step as OfferingStep) : null
}

function withTimeout<T>(promise: Promise<T>, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error(message)), LOAD_TIMEOUT_MS)
    promise
      .then(resolve)
      .catch(reject)
      .finally(() => window.clearTimeout(timeout))
  })
}

export default function OfferingShell() {
  const { projectId, offeringId } = useParams<{ projectId: string; offeringId: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const { offerings, currentOffering, currentStep, fetchOfferings, setCurrentOffering, goToStep, videoGenerations } = useOfferingStore()
  const { projects, isLoading: projectsLoading, fetchProjects } = useProjectStore()
  const requestedStep = stepFromPath(location.pathname)
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [loadError, setLoadError] = useState('')
  const [retryNonce, setRetryNonce] = useState(0)
  const fetchedOfferingsForProject = useRef<string | null>(null)

  const project = projects.find(p => p.id === projectId)
  const projectOfferings = useMemo(() => (projectId ? (offerings[projectId] ?? []) : []), [offerings, projectId])
  const cachedOffering = useMemo(
    () => projectOfferings.find(o => o.id === offeringId) ?? null,
    [offeringId, projectOfferings]
  )
  const activeOffering = currentOffering && currentOffering.id === offeringId && currentOffering.projectId === projectId
    ? currentOffering
    : null
  const videoGenerationLocked = Boolean(
    activeOffering &&
    (videoGenerations[activeOffering.id] || (activeOffering.pipelineStatus === 'processing' && activeOffering.savedStep === 5 && !activeOffering.outputVideoUrl))
  )

  useEffect(() => {
    if (!projectId || projects.length > 0 || projectsLoading) return
    fetchProjects().catch(() => {})
  }, [fetchProjects, projectId, projects.length, projectsLoading])

  useEffect(() => {
    if (!projectId) return
    if (projectOfferings.length > 0 || fetchedOfferingsForProject.current === projectId) return

    fetchedOfferingsForProject.current = projectId
    fetchOfferings(projectId).catch(() => {
      fetchedOfferingsForProject.current = null
    })
  }, [fetchOfferings, projectId, projectOfferings.length])

  useEffect(() => {
    let cancelled = false

    async function loadOffering() {
      if (!projectId || !offeringId) return
      setLoadError('')

      if (currentOffering?.id === offeringId && currentOffering.projectId === projectId) {
        setLoadState('ready')
        return
      }

      if (cachedOffering) {
        setCurrentOffering({ ...cachedOffering, savedStep: requestedStep ?? cachedOffering.savedStep ?? 1 })
        setLoadState('ready')
        return
      }

      setLoadState('loading')
      try {
        const { data } = await withTimeout(
          apiClient.get<Offering>(`/offerings/${offeringId}`),
          'Loading this workflow took too long.'
        )
        if (cancelled) return
        if (data.projectId !== projectId) {
          setLoadState('error')
          setLoadError('This workflow does not belong to the selected project.')
          return
        }
        setCurrentOffering({ ...data, savedStep: requestedStep ?? data.savedStep ?? 1 })
        setLoadState('ready')
      } catch (error) {
        if (cancelled) return
        console.error('[OfferingShell] Could not load workflow', error)
        const message = safeSystemErrorMessage()
        setLoadState('error')
        setLoadError(message)
        toast(message, 'destructive')
      }
    }

    loadOffering()
    return () => {
      cancelled = true
    }
  }, [cachedOffering, currentOffering?.id, currentOffering?.projectId, offeringId, projectId, requestedStep, retryNonce, setCurrentOffering])

  useEffect(() => {
    const step = requestedStep
    if (!activeOffering) return
    if (videoGenerationLocked && step && step !== 5) {
      navigate(`/projects/${projectId}/offerings/${offeringId}/step/5`, { replace: true })
      if (currentStep !== 5) goToStep(5)
      return
    }
    const savedStep = activeOffering.savedStep
    if (step === 1 && savedStep && savedStep > 1 && currentStep === savedStep) {
      navigate(`/projects/${projectId}/offerings/${offeringId}/step/${savedStep}`, { replace: true })
      return
    }
    if (step && step !== currentStep) {
      goToStep(step as 1 | 2 | 3 | 4 | 5 | 6)
    }
  }, [activeOffering, currentStep, goToStep, requestedStep, navigate, offeringId, projectId, videoGenerationLocked])

  const crumbs = [
    { label: 'All Projects', to: '/projects' },
    { label: project?.name ?? 'Project', to: `/projects/${projectId}` },
    { label: activeOffering?.name ?? cachedOffering?.name ?? 'Project Workflow' },
  ]

  if (loadState === 'error' && !activeOffering) {
    return (
      <div className="flex min-h-full flex-col">
        <TopBar crumbs={crumbs} />
        <div className="mx-auto w-full max-w-4xl px-6 pb-8 pt-6">
          <SystemIssue title="Could not open this workflow." message={loadError || safeSystemErrorMessage()} />
          <div className="mt-5 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => setRetryNonce(value => value + 1)}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#1450F5] px-4 text-sm font-semibold text-white transition-colors duration-[120ms] hover:bg-[#0f3fd1]"
            >
              <RefreshCw style={{ width: 15, height: 15 }} />
              Retry
            </button>
            <Link
              to="/projects"
              className="inline-flex h-10 items-center rounded-lg border border-[#E4E4E4] bg-white px-4 text-sm font-semibold text-[#374151] transition-colors duration-[120ms] hover:border-[#1450F5]/40 hover:text-[#1450F5]"
            >
              Back to Projects
            </Link>
          </div>
        </div>
      </div>
    )
  }

  if (!activeOffering) {
    return (
      <div className="flex min-h-full flex-col">
        <TopBar crumbs={crumbs} />
        <div className="mx-auto w-full max-w-4xl px-6 pb-8 pt-6">
          <Skeleton className="h-80 rounded-lg" />
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-full flex-col">
      <TopBar crumbs={crumbs} />
      <div className="mx-auto w-full max-w-4xl px-6 pb-8 pt-6">
        <div className="mb-4 flex justify-end">
          <Link
            to="/projects"
            onClick={event => {
              if (videoGenerationLocked) {
                event.preventDefault()
                return
              }
              goToStep(currentStep)
            }}
            className={cn(
              'inline-flex items-center gap-2 rounded-lg border border-[#E4E4E4] bg-white px-3 text-xs font-semibold text-[#374151] transition-colors duration-[120ms] hover:border-[#1450F5]/40 hover:text-[#1450F5]',
              videoGenerationLocked && 'cursor-not-allowed opacity-40 hover:border-[#E4E4E4] hover:text-[#374151]'
            )}
            style={{ height: 34 }}
          >
            <Home style={{ width: 13, height: 13 }} />
            Back to Home
          </Link>
        </div>
        <Routes>
          <Route path="step/1" element={<Step1 />} />
          <Route path="step/2" element={<Step2 />} />
          <Route path="step/3" element={<Step3 />} />
          <Route path="step/4" element={<Step4 />} />
          <Route path="step/5" element={<Step5 />} />
          <Route path="step/6" element={<Step6 />} />
          <Route index element={<Navigate to={`step/${activeOffering.savedStep ?? currentStep ?? 1}`} replace />} />
        </Routes>
      </div>
    </div>
  )
}
