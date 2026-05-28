import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Eye, EyeOff } from 'lucide-react'
import { useOfferingStore } from '../../../store/offeringStore'
import { AnnotatedPreview } from '../../../components/shared/AnnotatedPreview'
import { KONE_COMPONENTS } from '../../../lib/constants'
import { cn } from '../../../lib/utils'
import type { ComponentKey } from '../../../types'

const COMP_LABELS = Object.fromEntries(KONE_COMPONENTS.map(c => [c.key, c.label])) as Record<ComponentKey, string>

export default function Step4Preview() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, setAnnotationState, goToStep } = useOfferingStore()

  const offering = currentOffering
  const components = offering?.selectedComponents ?? []
  const pins = offering?.componentPins ?? []

  const [annotationsOn, setAnnotationsOn] = useState(offering?.annotationsEnabled ?? true)
  const [activeFilters, setActiveFilters] = useState<ComponentKey[]>(
    offering?.activeAnnotationFilters?.length ? offering.activeAnnotationFilters : components
  )

  useEffect(() => {
    setAnnotationState(annotationsOn, activeFilters)
  }, [annotationsOn, activeFilters])

  const toggleFilter = (k: ComponentKey) =>
    setActiveFilters(prev => prev.includes(k) ? prev.filter(f => f !== k) : [...prev, k])

  const appliedCount = annotationsOn ? pins.filter(p => activeFilters.includes(p.componentKey)).length : 0

  const handleContinue = () => {
    goToStep(5)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/5`)
  }

  const handleBack = () => {
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/3`)
    goToStep(3)
  }

  return (
    <div className="rounded-xl border border-[#E9ECEF] bg-white p-8 shadow-sm">
      <div className="mb-6 flex items-start justify-between">
        <h2 className="text-heading text-[15px] font-semibold text-[#111827]">4 &nbsp; Preview with Annotations</h2>
        <button onClick={handleBack} className="text-xs font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#6B7280]">Back</button>
      </div>

      {/* Filter bar */}
      <div className="mb-4 flex items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2">
          {components.map(k => (
            <button
              key={k}
              onClick={() => toggleFilter(k)}
              aria-pressed={activeFilters.includes(k)}
              disabled={!annotationsOn}
              className={cn(
                'rounded-[5px] px-3 text-xs font-medium transition-colors duration-[120ms] disabled:opacity-50',
                activeFilters.includes(k) && annotationsOn
                  ? 'bg-[#0A0A0A] text-white'
                  : 'border border-[#E4E4E4] bg-white text-[#525252] hover:bg-[#F7F7F7]'
              )}
              style={{ height: 30 }}
            >
              {COMP_LABELS[k]}
            </button>
          ))}
        </div>
        <button
          onClick={() => setAnnotationsOn(v => !v)}
          className="flex shrink-0 items-center gap-1.5 rounded-[5px] border border-[#E4E4E4] bg-white px-3 text-xs font-medium text-[#525252] transition-colors duration-[120ms] hover:bg-[#F7F7F7]"
          style={{ height: 30 }}
          aria-label={annotationsOn ? 'Turn annotations off' : 'Turn annotations on'}
        >
          {annotationsOn
            ? <Eye style={{ width: 13, height: 13 }} />
            : <EyeOff style={{ width: 13, height: 13 }} />}
          Annotations {annotationsOn ? 'on' : 'off'}
        </button>
      </div>

      <AnnotatedPreview
        imageUrl={offering?.uploadedFileUrl ?? null}
        pins={pins}
        annotationsEnabled={annotationsOn}
        activeFilters={activeFilters}
        labels={COMP_LABELS}
      />

      <p className="mt-3 text-xs text-[#A3A3A3]">{appliedCount} annotation{appliedCount !== 1 ? 's' : ''} applied</p>

      <div className="mt-6 flex justify-end">
        <button
          onClick={handleContinue}
          className="rounded-[5px] bg-[#0A0A0A] px-5 text-sm font-medium text-white transition-colors duration-[120ms] hover:bg-[#262626]"
          style={{ height: 34 }}
        >
          Continue
        </button>
      </div>
    </div>
  )
}
