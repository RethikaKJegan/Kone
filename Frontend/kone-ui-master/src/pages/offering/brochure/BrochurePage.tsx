import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ChevronDown, ChevronUp, Check, Pencil, Printer, Download, FileText } from 'lucide-react'
import { useOfferingStore } from '../../../store/offeringStore'
import { useProjectStore } from '../../../store/projectStore'
import { ComponentBadge } from '../../../components/shared/ComponentBadge'
import { UploadZone } from '../../../components/shared/UploadZone'
import { TopBar } from '../../../components/layout/TopBar'
import { Skeleton } from '../../../components/ui/skeleton'
import { BROCHURE_SECTIONS, KONE_COMPONENTS } from '../../../lib/constants'
import { toast } from '../../../hooks/useToast'
import apiClient from '../../../api/client'
import type { Brochure, BrochureSection, ComponentKey } from '../../../types'

const COMP_LABELS = Object.fromEntries(KONE_COMPONENTS.map(c => [c.key, c.label])) as Record<ComponentKey, string>

export default function BrochurePage() {
  const { projectId, offeringId } = useParams()
  const { currentOffering, offerings } = useOfferingStore()
  const { projects } = useProjectStore()

  const offering =
    currentOffering ??
    (projectId && offeringId
      ? (offerings[projectId] ?? []).find(o => o.id === offeringId)
      : null)

  const project = projects.find(p => p.id === projectId)

  const [brochure, setBrochure] = useState<Brochure | null>(null)
  const [loading, setLoading] = useState(true)
  const [openSection, setOpenSection] = useState<BrochureSection | null>(null)
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!offeringId) return
    apiClient
      .get<Brochure>(`/offerings/${offeringId}/brochure`)
      .then(r => setBrochure(r.data))
      .catch(async () => {
        if (!offeringId || !projectId) return
        const r = await apiClient.post<Brochure>(`/offerings/${offeringId}/brochure`, { projectId })
        setBrochure(r.data)
      })
      .finally(() => setLoading(false))
  }, [offeringId, projectId])

  const handleSectionSave = async (key: BrochureSection) => {
    if (!offeringId || !brochure) return
    const value = drafts[key] ?? brochure.content[key]
    const r = await apiClient.patch<Brochure>(`/offerings/${offeringId}/brochure`, {
      content: { [key]: value },
    })
    setBrochure(r.data)
    setOpenSection(null)
    toast('Section saved')
  }

  const handleExport = (type: 'PDF' | 'PPT') => {
    toast('Generating brochure... your download will start shortly')
    setTimeout(() => {
      const a = document.createElement('a')
      a.href = 'data:text/plain;base64,SGVsbG8='
      a.download = `salesnxt-brochure.${type.toLowerCase()}`
      a.click()
    }, 1500)
  }

  const crumbs = [
    { label: 'All Projects', to: '/projects' },
    { label: project?.name ?? 'Project', to: `/projects/${projectId}` },
    { label: offering?.name ?? 'Offering', to: `/projects/${projectId}/offerings/${offeringId}/step/1` },
    { label: 'Sales Brochure' },
  ]

  if (loading) return (
    <div>
      <TopBar crumbs={crumbs} />
      <div className="mx-auto max-w-6xl space-y-4 p-6">
        <Skeleton className="h-8 w-64" />
        <div className="mt-6 grid grid-cols-2 gap-6">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      </div>
    </div>
  )

  const sectionsComplete = brochure?.sectionsComplete ?? 0
  const total = BROCHURE_SECTIONS.length

  return (
    <div>
      <TopBar crumbs={crumbs} />
      <div className="mx-auto max-w-6xl p-6">
        <div className="mb-6">
          <Link to={`/projects/${projectId}`} className="text-xs text-[#A3A3A3] transition-colors duration-[120ms] hover:text-[#525252]">
            â† Back to project
          </Link>
          <h1 className="mt-2 text-[22px] font-semibold tracking-[-0.02em] text-[#0A0A0A]">Sales Brochure</h1>
          <p className="mt-1 text-sm text-[#A3A3A3]">Customise each section below, then download your client-ready brochure.</p>
        </div>

        {/* Progress */}
        <div className="mb-6 space-y-2">
          <p className="text-xs text-[#A3A3A3]">{sectionsComplete}/{total} sections complete</p>
          <div className="h-1 w-full overflow-hidden rounded-full bg-[#E4E4E4]">
            <div
              className="h-full rounded-full bg-[#0A0A0A] transition-all duration-300"
              style={{ width: `${(sectionsComplete / total) * 100}%` }}
            />
          </div>
        </div>

        {offering && (
          <div className="mb-6 flex flex-wrap gap-1.5">
            {offering.selectedComponents.map(k => (
              <ComponentBadge key={k} componentKey={k} label={COMP_LABELS[k]} />
            ))}
          </div>
        )}

        <div className="grid grid-cols-2 gap-6">
          {/* Left: tender PDF */}
          <div>
            <UploadZone
              onFile={() => toast('PDF uploaded')}
              accept=".pdf"
              className="mb-4"
            />
            <div className="rounded-lg border border-[#E4E4E4] bg-white">
              <div className="flex items-center border-b border-[#E4E4E4] px-4 py-3">
                <p className="text-xs font-semibold text-[#374151]">Standard Tender Preview</p>
                <span className="ml-2 rounded-[4px] bg-[#F5F5F5] px-2 py-0.5 text-[11px] text-[#A3A3A3]">Read-only</span>
                <div className="ml-auto flex gap-1.5">
                  <button aria-label="Print" onClick={() => toast('Print is not available in preview')} className="text-[#C8C8C8] transition-colors duration-[120ms] hover:text-[#A3A3A3]">
                    <Printer style={{ width: 15, height: 15 }} />
                  </button>
                  <button aria-label="Download tender" onClick={() => toast('Download is not available in preview')} className="text-[#C8C8C8] transition-colors duration-[120ms] hover:text-[#A3A3A3]">
                    <Download style={{ width: 15, height: 15 }} />
                  </button>
                </div>
              </div>
              <div className="space-y-4 p-6">
                <p className="text-base font-bold text-[#1450F5]">KONE</p>
                <div className="w-full rounded bg-[#F5F5F5]" style={{ height: 200 }} aria-label="Product image placeholder" />
                <p className="text-sm text-[#A3A3A3]">Proposal for</p>
                <div className="space-y-2">
                  {[80, 60, 72, 50].map((w, i) => (
                    <div key={i} className="h-2 rounded bg-[#E4E4E4]" style={{ width: `${w}%` }} />
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Right: sections */}
          <div className="space-y-2">
            {BROCHURE_SECTIONS.map(section => {
              const isOpen = openSection === section.key
              const value = brochure?.content[section.key] ?? ''
              const isDone = value.trim().length > 0
              const draft = drafts[section.key] ?? value

              return (
                <div key={section.key} className="overflow-hidden rounded-lg border border-[#E4E4E4] bg-white">
                  <button
                    onClick={() => setOpenSection(prev => prev === section.key ? null : section.key)}
                    className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors duration-[120ms] hover:bg-[#F7F7F7]"
                    aria-expanded={isOpen}
                  >
                    <div className="flex items-center gap-2">
                      {isDone
                        ? <Check className="shrink-0 text-[#16A34A]" style={{ width: 14, height: 14 }} />
                        : <Pencil className="shrink-0 text-[#C8C8C8]" style={{ width: 13, height: 13 }} />}
                      <span className="text-sm font-medium text-[#0A0A0A]">{section.label}</span>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      {!isOpen && !isDone && <span className="text-xs text-[#C8C8C8]">Click to add content...</span>}
                      {!isOpen && isDone && <span className="text-xs text-[#A3A3A3]">{value.length} chars</span>}
                      {isOpen
                        ? <ChevronUp className="text-[#A3A3A3]" style={{ width: 14, height: 14 }} />
                        : <ChevronDown className="text-[#A3A3A3]" style={{ width: 14, height: 14 }} />}
                    </div>
                  </button>

                  {isOpen && (
                    <div className="border-t border-[#E4E4E4] px-4 pb-4 pt-3">
                      <textarea
                        value={draft}
                        onChange={e => setDrafts(prev => ({ ...prev, [section.key]: e.target.value }))}
                        placeholder={section.placeholder}
                        rows={5}
                        className="w-full resize-none rounded-[5px] border border-[#E4E4E4] px-3 py-2 text-sm text-[#374151] outline-none transition-colors duration-[120ms] focus:border-[#0A0A0A] focus:ring-1 focus:ring-[#0A0A0A]"
                        aria-label={section.label}
                      />
                      <div className="mt-2 flex items-center justify-between">
                        <span className="text-[11px] text-[#A3A3A3]">{draft.length} characters</span>
                        <button
                          onClick={() => handleSectionSave(section.key)}
                          className="text-xs font-medium text-[#0A0A0A] transition-colors duration-[120ms] hover:text-[#525252]"
                        >
                          Done
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        <div className="mt-8 flex items-center gap-3">
          <button
            onClick={() => handleExport('PDF')}
            className="flex items-center gap-1.5 rounded-[5px] bg-[#0A0A0A] px-5 text-sm font-medium text-white transition-colors duration-[120ms] hover:bg-[#262626]"
            style={{ height: 34 }}
          >
            <Download style={{ width: 14, height: 14 }} />
            Download as PDF
          </button>
          <button
            onClick={() => handleExport('PPT')}
            className="flex items-center gap-1.5 rounded-[5px] border border-[#E4E4E4] px-5 text-sm font-medium text-[#525252] transition-colors duration-[120ms] hover:bg-[#F7F7F7]"
            style={{ height: 34 }}
          >
            <FileText style={{ width: 14, height: 14 }} />
            Export as PPT
          </button>
        </div>
      </div>
    </div>
  )
}
