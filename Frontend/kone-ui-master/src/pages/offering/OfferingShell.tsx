import { useEffect, Suspense, lazy } from 'react'
import { useParams, Routes, Route, Navigate } from 'react-router-dom'
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
  const { offerings, currentOffering, fetchOfferings, setCurrentOffering } = useOfferingStore()
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

  const crumbs = [
    { label: 'All Projects', to: '/projects' },
    { label: project?.name ?? 'Project', to: `/projects/${projectId}` },
    { label: currentOffering?.name ?? 'New Visualization' },
  ]

  return (
    <div className="flex flex-col min-h-full">
      <TopBar crumbs={crumbs} />
      <div className="mx-auto max-w-4xl w-full px-6 pb-8 pt-6">
        <Suspense fallback={<Skeleton className="h-80 rounded-lg" />}>
          <Routes>
            <Route path="step/1" element={<Step1 />} />
            <Route path="step/2" element={<Step2 />} />
            <Route path="step/3" element={<Step3 />} />
            <Route path="step/4" element={<Step4 />} />
            <Route path="step/5" element={<Step5 />} />
            <Route path="step/6" element={<Step6 />} />
            <Route index element={<Navigate to="step/1" replace />} />
          </Routes>
        </Suspense>
      </div>
    </div>
  )
}
