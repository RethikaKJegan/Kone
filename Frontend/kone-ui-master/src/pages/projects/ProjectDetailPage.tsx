import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, RefreshCw } from 'lucide-react'
import { TopBar } from '../../components/layout/TopBar'
import { Skeleton } from '../../components/ui/skeleton'
import { useProjectStore } from '../../store/projectStore'
import { useOfferingStore } from '../../store/offeringStore'
import { toast } from '../../hooks/useToast'

const PREPARE_TIMEOUT_MS = 15000

type PrepareState = 'loading' | 'error'

function withTimeout<T>(promise: Promise<T>, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error(message)), PREPARE_TIMEOUT_MS)
    promise
      .then(resolve)
      .catch(reject)
      .finally(() => window.clearTimeout(timeout))
  })
}

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { projects, fetchProjects } = useProjectStore()
  const { fetchOfferings, createOffering } = useOfferingStore()
  const [prepareState, setPrepareState] = useState<PrepareState>('loading')
  const [prepareError, setPrepareError] = useState('')
  const [retryNonce, setRetryNonce] = useState(0)

  const project = projects.find(p => p.id === projectId)

  useEffect(() => {
    let cancelled = false

    async function openSingleProjectWorkflow() {
      if (!projectId) return
      setPrepareState('loading')
      setPrepareError('')

      try {
        if (useProjectStore.getState().projects.length === 0) {
          await withTimeout(fetchProjects(), 'Loading projects took too long.')
        }
        if (cancelled) return

        const latestProject = useProjectStore.getState().projects.find(p => p.id === projectId)
        if (!latestProject) {
          throw new Error('Project not found.')
        }

        await withTimeout(fetchOfferings(projectId), 'Loading this project workflow took too long.')
        if (cancelled) return

        const projectOfferings = useOfferingStore.getState().offerings[projectId] ?? []
        const offering = projectOfferings[0] ?? await withTimeout(
          createOffering(projectId),
          'Creating this project workflow took too long.'
        )
        if (cancelled) return

        navigate(`/projects/${projectId}/offerings/${offering.id}/step/${offering.savedStep ?? 1}`, { replace: true })
      } catch (error) {
        if (cancelled) return
        const message = error instanceof Error ? error.message : 'Could not open this project workflow.'
        setPrepareState('error')
        setPrepareError(message)
        toast(message, 'destructive')
      }
    }

    openSingleProjectWorkflow()
    return () => {
      cancelled = true
    }
  }, [createOffering, fetchOfferings, fetchProjects, navigate, projectId, retryNonce])

  const crumbs = [{ label: 'All Projects', to: '/projects' }, { label: project?.name ?? 'Project' }]

  if (prepareState === 'error') {
    return (
      <div>
        <TopBar crumbs={crumbs} />
        <div className="mx-auto max-w-4xl p-8">
          <Link
            to="/projects"
            className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#1450F5]"
          >
            <ArrowLeft style={{ width: 13, height: 13 }} />
            All Projects
          </Link>
          <div className="rounded-lg border border-[#E4E4E4] bg-white p-6">
            <p className="text-sm font-semibold text-[#111827]">Could not open this project.</p>
            <p className="mt-2 text-sm text-[#6B7280]">{prepareError || 'Please retry the page load.'}</p>
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
      </div>
    )
  }

  return (
    <div>
      <TopBar crumbs={crumbs} />
      <div className="mx-auto max-w-4xl p-8">
        <Link
          to="/projects"
          className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#1450F5]"
        >
          <ArrowLeft style={{ width: 13, height: 13 }} />
          All Projects
        </Link>
        <Skeleton className="h-80 rounded-lg" />
      </div>
    </div>
  )
}
