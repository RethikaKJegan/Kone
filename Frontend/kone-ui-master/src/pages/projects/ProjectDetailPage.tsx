import { useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Plus } from 'lucide-react'
import { useProjectStore } from '../../store/projectStore'
import { useOfferingStore } from '../../store/offeringStore'
import { StatusBadge } from '../../components/shared/StatusBadge'
import { ComponentBadge } from '../../components/shared/ComponentBadge'
import { Skeleton } from '../../components/ui/skeleton'
import { TopBar } from '../../components/layout/TopBar'
import { KONE_COMPONENTS, ENVIRONMENTS } from '../../lib/constants'
import { formatDate } from '../../lib/utils'
import type { ComponentKey, Environment } from '../../types'

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { projects } = useProjectStore()
  const { offerings, fetchOfferings, createOffering } = useOfferingStore()

  const project = projects.find(p => p.id === projectId)
  const projectOfferings = projectId ? (offerings[projectId] ?? []) : []
  const isLoading = !project && projects.length === 0

  useEffect(() => {
    if (projectId) fetchOfferings(projectId)
  }, [projectId, fetchOfferings])

  const handleNewOffering = async () => {
    if (!projectId) return
    const offering = await createOffering(projectId)
    navigate(`/projects/${projectId}/offerings/${offering.id}/step/1`)
  }

  const componentLabels = Object.fromEntries(
    KONE_COMPONENTS.map(c => [c.key, c.label])
  ) as Record<ComponentKey, string>

  const envLabels = Object.fromEntries(
    ENVIRONMENTS.map(e => [e.key, e.label])
  ) as Record<Environment, string>

  if (isLoading) {
    return (
      <div className="p-8 space-y-4">
        <Skeleton className="h-9 w-56" />
        <Skeleton className="h-4 w-36" />
        <div className="grid gap-5 mt-8" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))' }}>
          {[1, 2].map(n => <Skeleton key={n} className="h-52 rounded-xl" />)}
        </div>
      </div>
    )
  }

  if (!project) return (
    <div className="p-6">
      <p className="text-sm text-[#A3A3A3]">Project not found.{' '}
        <Link to="/projects" className="text-[#0A0A0A] hover:underline">Go back</Link>
      </p>
    </div>
  )

  return (
    <div>
      <TopBar crumbs={[{ label: 'All Projects', to: '/projects' }, { label: project.name }]} />
      <div className="p-8 max-w-7xl mx-auto">
        {/* Back */}
        <Link
          to="/projects"
          className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium transition-colors duration-[120ms]"
          style={{ color: '#9CA3AF' }}
          onMouseEnter={e => (e.currentTarget.style.color = '#1450F5')}
          onMouseLeave={e => (e.currentTarget.style.color = '#9CA3AF')}
        >
          <ArrowLeft style={{ width: 13, height: 13 }} />
          All Projects
        </Link>

        {/* ── Project Identity Card ── */}
        <div
          className="mb-10 flex items-center gap-5 rounded-2xl border bg-white"
          style={{ padding: '24px 28px', borderColor: '#E8EAED' }}
        >
          {/* Monogram avatar */}
          <div style={{
            width: 60, height: 60, borderRadius: 16, background: '#1450F5',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0, fontSize: 22, fontWeight: 700, color: '#FFFFFF',
            letterSpacing: '-0.02em', userSelect: 'none',
          }}>
            {project.name.slice(0, 2).toUpperCase()}
          </div>

          {/* Info */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#1450F5', marginBottom: 5 }}>
              Project
            </p>
            <h1 style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: '#000000', lineHeight: 1.1 }}>
              {project.name}
            </h1>
            {/* Stats row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 13, color: '#9CA3AF' }}>Created {formatDate(project.createdAt)}</span>
              {projectOfferings.length > 0 && (
                <>
                  <span style={{ width: 3, height: 3, borderRadius: '50%', background: '#D1D5DB', flexShrink: 0 }} />
                  <span style={{ fontSize: 13, fontWeight: 500, color: '#6B7280' }}>
                    {projectOfferings.length} visualization{projectOfferings.length !== 1 ? 's' : ''}
                  </span>
                </>
              )}
              {projectOfferings.filter(o => o.status === 'complete').length > 0 && (
                <>
                  <span style={{ width: 3, height: 3, borderRadius: '50%', background: '#D1D5DB', flexShrink: 0 }} />
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#16A34A' }}>
                    {projectOfferings.filter(o => o.status === 'complete').length} complete
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Action */}
          <button
            onClick={handleNewOffering}
            className="flex shrink-0 items-center gap-2 rounded-[6px] px-5 text-sm font-semibold text-white transition-all duration-[150ms] hover:opacity-90 active:scale-[0.98]"
            style={{ height: 40, background: '#1450F5' }}
          >
            <Plus style={{ width: 15, height: 15 }} />
            New Visualization
          </button>
        </div>

        {projectOfferings.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-5 py-28">
            <div className="flex items-center justify-center rounded-xl" style={{ width: 56, height: 56, background: 'rgba(20,80,245,0.08)' }}>
              <Plus style={{ width: 24, height: 24, color: '#1450F5' }} />
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-[#000000]">No visualizations yet</p>
              <p className="mt-1.5 text-base text-[#6B7280]">Create your first visualization to begin the workflow.</p>
            </div>
            <button
              onClick={handleNewOffering}
              className="flex items-center gap-2 rounded-[6px] px-5 text-sm font-semibold text-white transition-all duration-[150ms] hover:opacity-90"
              style={{ height: 40, background: '#1450F5' }}
            >
              <Plus style={{ width: 15, height: 15 }} />
              Create First Visualization
            </button>
          </div>
        ) : (
          <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))' }}>
            {projectOfferings.map(offering => (
              <div
                key={offering.id}
                className="rounded-xl border bg-white transition-all duration-200 hover:shadow-lg hover:shadow-[#1450F5]/[0.07]"
                style={{ padding: '28px 28px 24px', borderColor: '#E8EAED' }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(20,80,245,0.3)')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = '#E8EAED')}
              >
                <div className="mb-4 flex items-start justify-between">
                  <h3 style={{ fontSize: 18, fontWeight: 700, color: '#000000', letterSpacing: '-0.01em', lineHeight: 1.3, paddingRight: 12 }}>
                    {offering.name}
                  </h3>
                  <StatusBadge status={offering.status} />
                </div>

                {offering.environments.length > 0 && (
                  <div className="mb-3 flex flex-wrap gap-1.5">
                    {offering.environments.map(env => (
                      <span key={env} className="rounded-[5px] border px-2.5 py-1 text-xs font-medium"
                        style={{ borderColor: '#E4E4E4', background: '#F8F9FA', color: '#374151' }}>
                        {envLabels[env]}
                      </span>
                    ))}
                  </div>
                )}

                {offering.selectedComponents.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {offering.selectedComponents.map(key => (
                      <ComponentBadge key={key} componentKey={key} label={componentLabels[key]} />
                    ))}
                  </div>
                )}

                <div className="mt-6 flex items-center gap-3">
                  {offering.status === 'complete' ? (
                    <Link
                      to={`/projects/${projectId}/offerings/${offering.id}/brochure`}
                      className="rounded-[6px] px-4 text-sm font-semibold text-white transition-all duration-[120ms] hover:opacity-90"
                      style={{ paddingTop: 8, paddingBottom: 8, background: '#1450F5' }}
                    >
                      Build Brochure
                    </Link>
                  ) : (
                    <Link
                      to={`/projects/${projectId}/offerings/${offering.id}/step/1`}
                      className="text-sm font-semibold transition-colors duration-[120ms] hover:opacity-75"
                      style={{ color: '#1450F5' }}
                    >
                      Continue →
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
