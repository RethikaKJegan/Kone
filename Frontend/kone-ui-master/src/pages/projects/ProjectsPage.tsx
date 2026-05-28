import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Layers, Plus, X, Check } from 'lucide-react'
import { useProjectStore } from '../../store/projectStore'
import { StatusBadge } from '../../components/shared/StatusBadge'
import { Skeleton } from '../../components/ui/skeleton'
import { TopBar } from '../../components/layout/TopBar'
import { toast } from '../../hooks/useToast'
import { formatDate } from '../../lib/utils'

export default function ProjectsPage() {
  const navigate = useNavigate()
  const { projects, isLoading, fetchProjects, createProject } = useProjectStore()
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [nameError, setNameError] = useState('')
  const [saving, setSaving] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  useEffect(() => {
    if (creating) inputRef.current?.focus()
  }, [creating])

  const handleCreate = async () => {
    const trimmed = newName.trim()
    if (trimmed.length < 2 || trimmed.length > 80) {
      setNameError('Project name must be 2–80 characters')
      return
    }
    setSaving(true)
    try {
      const project = await createProject(trimmed)
      setCreating(false)
      setNewName('')
      setNameError('')
      toast('Project created successfully')
      navigate(`/projects/${project.id}`)
    } finally {
      setSaving(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleCreate()
    if (e.key === 'Escape') { setCreating(false); setNewName(''); setNameError('') }
  }

  return (
    <div>
      <TopBar crumbs={[{ label: 'All Projects' }]} />
      <div className="p-8 max-w-7xl mx-auto">
        <div className="mb-8 flex items-start justify-between">
          <div>
            <h1 style={{ fontSize: 30, fontWeight: 700, letterSpacing: '-0.03em', color: '#000000', lineHeight: 1.1 }}>My Projects</h1>
            <p className="mt-2 text-base text-[#6B7280]">Each project holds your visualisation outputs and generated offerings.</p>
          </div>
          {!creating && (
            <button
              onClick={() => setCreating(true)}
              className="flex items-center gap-2 rounded-[6px] px-5 text-sm font-semibold text-white transition-all duration-[150ms] hover:opacity-90 active:scale-[0.98]"
              style={{ height: 40, background: '#1450F5' }}
            >
              <Plus style={{ width: 15, height: 15 }} />
              New Project
            </button>
          )}
        </div>

        {creating && (
          <div className="mb-8 flex items-start gap-3">
            <div className="flex-1 space-y-1">
              <input
                ref={inputRef}
                value={newName}
                onChange={e => { setNewName(e.target.value); setNameError('') }}
                onKeyDown={handleKeyDown}
                placeholder="Project name"
                className="w-full max-w-sm rounded-[6px] border border-[#E4E4E4] bg-white px-3 text-sm text-[#000000] outline-none transition-colors duration-[120ms] focus:border-[#1450F5] focus:ring-1 focus:ring-[#1450F5]"
                style={{ height: 40 }}
              />
              {nameError && <p className="text-xs text-red-600">{nameError}</p>}
            </div>
            <button
              onClick={handleCreate}
              disabled={saving}
              className="flex items-center gap-1.5 rounded-[6px] px-4 text-sm font-semibold text-white transition-all duration-[120ms] hover:opacity-90 disabled:opacity-50"
              style={{ height: 40, background: '#1450F5' }}
            >
              <Check style={{ width: 14, height: 14 }} />
              Create
            </button>
            <button
              onClick={() => { setCreating(false); setNewName(''); setNameError('') }}
              className="flex items-center justify-center rounded-[6px] border border-[#E4E4E4] text-[#525252] transition-colors duration-[120ms] hover:bg-[#F7F7F7]"
              style={{ height: 40, width: 40 }}
            >
              <X style={{ width: 15, height: 15 }} />
            </button>
          </div>
        )}

        {isLoading ? (
          <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))' }}>
            {[1, 2, 3].map(n => <Skeleton key={n} className="h-52 rounded-xl" />)}
          </div>
        ) : projects.length === 0 && !creating ? (
          <div className="flex flex-col items-center justify-center gap-5 py-28">
            <div className="flex items-center justify-center rounded-xl" style={{ width: 56, height: 56, background: 'rgba(20,80,245,0.08)' }}>
              <Layers style={{ width: 24, height: 24, color: '#1450F5' }} />
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-[#000000]">No projects yet</p>
              <p className="mt-1.5 text-base text-[#6B7280]">Create your first project to start the visualisation workflow.</p>
            </div>
            <button
              onClick={() => setCreating(true)}
              className="flex items-center gap-2 rounded-[6px] px-5 text-sm font-semibold text-white transition-all duration-[150ms] hover:opacity-90"
              style={{ height: 40, background: '#1450F5' }}
            >
              <Plus style={{ width: 15, height: 15 }} />
              Create First Project
            </button>
          </div>
        ) : (
          <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))' }}>
            {projects.map(project => (
              <button
                key={project.id}
                onClick={() => navigate(`/projects/${project.id}`)}
                className="group relative rounded-xl border bg-white text-left transition-all duration-200 hover:shadow-lg hover:shadow-[#1450F5]/[0.08]"
                style={{ padding: '28px 28px 24px', borderColor: '#E8EAED' }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(20,80,245,0.3)')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = '#E8EAED')}
              >
                <div className="absolute right-5 top-5">
                  <StatusBadge status={project.status} />
                </div>
                {/* Icon */}
                <div className="mb-5 flex items-center justify-center rounded-lg" style={{ width: 44, height: 44, background: 'rgba(20,80,245,0.08)' }}>
                  <Layers style={{ width: 20, height: 20, color: '#1450F5' }} />
                </div>
                {/* Title */}
                <h3 style={{ fontSize: 18, fontWeight: 700, color: '#000000', letterSpacing: '-0.01em', paddingRight: 60, lineHeight: 1.3 }}>
                  {project.name}
                </h3>
                {/* Meta */}
                <p className="mt-2 text-sm text-[#9CA3AF]">Created {formatDate(project.createdAt)}</p>
                {project.offeringCount > 0 && (
                  <p className="mt-0.5 text-sm text-[#9CA3AF]">
                    {project.offeringCount} offering{project.offeringCount !== 1 ? 's' : ''}
                  </p>
                )}
                {/* CTA */}
                <p className="mt-5 text-sm font-semibold transition-colors duration-[120ms]"
                  style={{ color: '#1450F5' }}>
                  {project.offeringCount > 0 ? 'View offerings →' : 'Start creating →'}
                </p>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
