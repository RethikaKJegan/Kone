import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Plus, MoreVertical, Image as ImageIcon, X, ZoomIn, ZoomOut, ExternalLink } from 'lucide-react'
import { useProjectStore } from '../../store/projectStore'
import { useOfferingStore } from '../../store/offeringStore'
import { StatusBadge } from '../../components/shared/StatusBadge'
import { ComponentBadge } from '../../components/shared/ComponentBadge'
import { Skeleton } from '../../components/ui/skeleton'
import { TopBar } from '../../components/layout/TopBar'
import { ActionPopup } from '../../components/shared/ActionPopup'
import { KONE_COMPONENTS, ENVIRONMENTS } from '../../lib/constants'
import { formatDate } from '../../lib/utils'
import type { ComponentKey, Environment, Offering } from '../../types'

function inputImageUrl(offering: Offering) {
  if (offering.inputImagePath) return offering.inputImagePath
  if (offering.imageId) return `/uploads/${offering.imageId}/input.jpg`
  if (offering.uploadedFileUrl && !offering.uploadedFileUrl.includes('/output/')) return offering.uploadedFileUrl
  return null
}

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { projects, updateProject, deleteProject } = useProjectStore()
  const { offerings, fetchOfferings, createOffering, updateOfferingName, deleteOffering } = useOfferingStore()
  const [openProjectMenu, setOpenProjectMenu] = useState(false)
  const [openOfferingMenuId, setOpenOfferingMenuId] = useState<string | null>(null)
  const [brokenImages, setBrokenImages] = useState<Record<string, boolean>>({})
  const [previewImage, setPreviewImage] = useState<{ offeringId: string; name: string; url: string } | null>(null)
  const [zoom, setZoom] = useState(1)

  const project = projects.find(p => p.id === projectId)
  const projectOfferings = projectId ? (offerings[projectId] ?? []) : []
  const isLoading = !project && projects.length === 0

  useEffect(() => {
    if (projectId) fetchOfferings(projectId)
  }, [projectId, fetchOfferings])

  useEffect(() => {
    setPreviewImage(null)
    setZoom(1)
  }, [projectId])

  useEffect(() => {
    if (!previewImage) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPreviewImage(null)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [previewImage])

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
          <div className="relative flex shrink-0 items-center gap-2">
            <button
              onClick={handleNewOffering}
              className="flex items-center gap-2 rounded-[6px] px-5 text-sm font-semibold text-white transition-all duration-[150ms] hover:opacity-90 active:scale-[0.98]"
              style={{ height: 40, background: '#1450F5' }}
            >
              <Plus style={{ width: 15, height: 15 }} />
              New Visualization
            </button>
            <button
              type="button"
              onClick={() => setOpenProjectMenu(v => !v)}
              className="flex h-10 w-10 items-center justify-center rounded-[6px] border border-[#E4E4E4] bg-white text-[#6B7280] transition-colors hover:bg-[#F3F4F6] hover:text-[#111827]"
              aria-label="Project menu"
            >
              <MoreVertical style={{ width: 16, height: 16 }} />
            </button>
            {openProjectMenu && (
              <ActionPopup
                entityLabel="project"
                entityName={project.name}
                onClose={() => setOpenProjectMenu(false)}
                onRename={name => updateProject(project.id, name).then(() => undefined)}
                onDelete={async () => {
                  await deleteProject(project.id)
                  navigate('/projects')
                }}
              />
            )}
          </div>
        </div>

        {projectOfferings.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-28">
            <div className="text-center">
              <p className="text-lg font-bold text-[#000000]">No visualizations yet</p>
              <p className="mt-1.5 text-base text-[#6B7280]">Create your first visualization to begin the workflow.</p>
            </div>
          </div>
        ) : (
          <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))' }}>
            {projectOfferings.map(offering => {
              const imageUrl = inputImageUrl(offering)
              const imageKey = projectId && imageUrl ? `${projectId}:${offering.id}:${imageUrl}` : null
              const hasImage = Boolean(imageUrl && imageKey && !brokenImages[imageKey])
              return (
                <div
                  key={offering.id}
                  className="rounded-xl border bg-white transition-all duration-200 hover:shadow-lg hover:shadow-[#1450F5]/[0.07]"
                  style={{ padding: '22px 22px 20px', borderColor: '#E8EAED' }}
                  onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(20,80,245,0.3)')}
                  onMouseLeave={e => (e.currentTarget.style.borderColor = '#E8EAED')}
                >
                  <div className="flex gap-4">
                    <div className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-[#E5E7EB] bg-[#F8FAFF]">
                      {hasImage ? (
                        <img
                          src={imageUrl ?? ''}
                          alt={`${offering.name} input`}
                          className="h-full w-full object-cover"
                          onError={() => {
                            if (imageKey) setBrokenImages(prev => ({ ...prev, [imageKey]: true }))
                          }}
                        />
                      ) : (
                        <div className="flex flex-col items-center gap-1 px-2 text-center">
                          <ImageIcon style={{ width: 18, height: 18 }} className="text-[#9CA3AF]" />
                          <span className="text-[10px] font-medium leading-tight text-[#9CA3AF]">No image uploaded</span>
                        </div>
                      )}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <h3 style={{ fontSize: 18, fontWeight: 700, color: '#000000', letterSpacing: '-0.01em', lineHeight: 1.3, paddingRight: 12 }}>
                          {offering.name}
                        </h3>
                        <div className="relative flex items-center gap-2">
                          <StatusBadge status={offering.status} />
                          <button
                            type="button"
                            onClick={() => setOpenOfferingMenuId(openOfferingMenuId === offering.id ? null : offering.id)}
                            className="flex h-7 w-7 items-center justify-center rounded-md text-[#6B7280] transition-colors hover:bg-[#F3F4F6] hover:text-[#111827]"
                            aria-label="Visualization menu"
                          >
                            <MoreVertical style={{ width: 15, height: 15 }} />
                          </button>
                          {openOfferingMenuId === offering.id && (
                            <ActionPopup
                              entityLabel="visualization"
                              entityName={offering.name}
                              onClose={() => setOpenOfferingMenuId(null)}
                              onRename={name => updateOfferingName(project.id, offering.id, name).then(() => undefined)}
                              onDelete={() => deleteOffering(project.id, offering.id)}
                            />
                          )}
                        </div>
                      </div>

                      {offering.environments.length > 0 && (
                        <div className="mb-2 flex flex-wrap gap-1.5">
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

                      <div className="mt-5 flex flex-wrap items-center gap-3">
                        <Link
                          to={`/projects/${projectId}/offerings/${offering.id}/step/${offering.savedStep ?? 1}`}
                          className="text-sm font-semibold transition-colors duration-[120ms] hover:opacity-75"
                          style={{ color: '#1450F5' }}
                        >
                          Continue →
                        </Link>
                        {hasImage ? (
                          <button
                            type="button"
                            onClick={() => {
                              setZoom(1)
                              setPreviewImage({ offeringId: offering.id, name: offering.name, url: imageUrl ?? '' })
                            }}
                            className="inline-flex h-8 items-center rounded-[6px] text-sm font-semibold text-[#6B7280] transition-colors hover:text-[#1450F5]"
                          >
                            Preview Input Image
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled
                            title="No image uploaded"
                            className="inline-flex h-8 cursor-not-allowed items-center rounded-[6px] text-sm font-semibold text-[#A3A3A3]"
                          >
                            Preview Input Image
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
      {previewImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 px-6 py-8"
          onClick={() => setPreviewImage(null)}
          role="dialog"
          aria-modal="true"
          aria-label="Input image preview"
        >
          <div
            className="flex max-h-full w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-[#E5E7EB] bg-white shadow-2xl"
            onClick={event => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-4 border-b border-[#EEF2F7] px-5 py-4">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[#111827]">{previewImage.name}</p>
                <p className="mt-0.5 text-xs text-[#6B7280]">Input image preview</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => setZoom(value => Math.max(0.5, value - 0.25))}
                  className="flex h-8 w-8 items-center justify-center rounded-md border border-[#E5E7EB] text-[#4B5563] hover:bg-[#F9FAFB]"
                  aria-label="Zoom out"
                >
                  <ZoomOut style={{ width: 15, height: 15 }} />
                </button>
                <button
                  type="button"
                  onClick={() => setZoom(value => Math.min(2, value + 0.25))}
                  className="flex h-8 w-8 items-center justify-center rounded-md border border-[#E5E7EB] text-[#4B5563] hover:bg-[#F9FAFB]"
                  aria-label="Zoom in"
                >
                  <ZoomIn style={{ width: 15, height: 15 }} />
                </button>
                <a
                  href={previewImage.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex h-8 items-center gap-1.5 rounded-md border border-[#E5E7EB] px-3 text-xs font-semibold text-[#4B5563] hover:bg-[#F9FAFB]"
                >
                  <ExternalLink style={{ width: 13, height: 13 }} />
                  Open full size
                </a>
                <button
                  type="button"
                  onClick={() => setPreviewImage(null)}
                  className="flex h-8 w-8 items-center justify-center rounded-md border border-[#E5E7EB] text-[#4B5563] hover:bg-[#F9FAFB]"
                  aria-label="Close preview"
                >
                  <X style={{ width: 15, height: 15 }} />
                </button>
              </div>
            </div>
            <div className="flex min-h-[360px] items-center justify-center overflow-auto bg-[#F8FAFC] p-5">
              <img
                src={previewImage.url}
                alt={`${previewImage.name} input preview`}
                className="max-h-[70vh] max-w-full rounded-lg object-contain shadow-sm transition-transform"
                style={{ transform: `scale(${zoom})` }}
                onError={() => {
                  if (projectId) {
                    setBrokenImages(prev => ({ ...prev, [`${projectId}:${previewImage.offeringId}:${previewImage.url}`]: true }))
                  }
                  setPreviewImage(null)
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
