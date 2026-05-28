import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Loader2, Image as ImageIcon, Layers, Video, Download, Eye, EyeOff } from 'lucide-react'
import { useOfferingStore } from '../../../store/offeringStore'
import { AnnotatedPreview } from '../../../components/shared/AnnotatedPreview'
import { KONE_COMPONENTS } from '../../../lib/constants'
import { toast } from '../../../hooks/useToast'
import { cn } from '../../../lib/utils'
import type { ComponentKey } from '../../../types'

const COMP_LABELS = Object.fromEntries(KONE_COMPONENTS.map(c => [c.key, c.label])) as Record<ComponentKey, string>

function downloadFromUrl(url: string, filename: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
}

export default function Step6Download() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, triggerRender, completeOffering, goToStep } = useOfferingStore()
  const [rendered, setRendered] = useState(currentOffering?.renderComplete ?? false)
  const [annotationsOn, setAnnotationsOn] = useState(true)
  const [activeFilters, setActiveFilters] = useState<ComponentKey[]>(
    currentOffering?.selectedComponents ?? []
  )

  useEffect(() => {
    if (!currentOffering?.renderComplete) {
      triggerRender().then(() => {
        setRendered(true)
        toast('Your outputs are ready to download')
      })
    } else {
      setRendered(true)
    }
  }, [])

  useEffect(() => {
    if (currentOffering?.selectedComponents) {
      setActiveFilters(currentOffering.selectedComponents)
    }
  }, [currentOffering?.id])

  const handleDownload = (url: string | null, filename: string) => {
    if (!url) {
      toast('Output file not available yet')
      return
    }
    toast(`Downloading ${filename}...`)
    downloadFromUrl(url, filename)
  }

  const handleSave = async () => {
    await completeOffering()
    toast('Visualization saved to project')
    navigate(`/projects/${projectId}`)
  }

  const handleBack = () => {
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/5`)
    goToStep(5)
  }

  const toggleFilter = (k: ComponentKey) =>
    setActiveFilters(prev => prev.includes(k) ? prev.filter(f => f !== k) : [...prev, k])

  const pins = currentOffering?.componentPins ?? []
  const offering = currentOffering

  if (!rendered) {
    return (
      <div className="flex min-h-[320px] flex-col items-center justify-center gap-4 rounded-lg border border-[#E4E4E4] bg-white p-8">
        <Loader2 className="animate-spin text-[#0A0A0A]" style={{ width: 28, height: 28 }} />
        <p className="text-sm font-medium text-[#0A0A0A]">Rendering your outputs...</p>
        <p className="text-xs text-[#A3A3A3]">This usually takes a few seconds</p>
      </div>
    )
  }

  const downloads = [
    {
      icon: ImageIcon,
      title: 'Rendered Image',
      subtitle: 'High-quality composite render',
      url: offering?.outputImageUrl ?? null,
      file: 'final_output.png',
      highlight: false,
    },
    {
      icon: Layers,
      title: 'Image with Callouts',
      subtitle: 'Render with annotation overlay',
      url: offering?.outputImageUrl ?? null,
      file: 'salesnxt-callouts.png',
      highlight: true,
    },
    {
      icon: Video,
      title: 'Video',
      subtitle: `${offering?.videoQuality} · ${offering?.videoMotionStyle === 'zoom-in' ? 'Zoom In' : offering?.videoMotionStyle === 'pan-lr' ? 'Pan L–R' : 'Pan R–L'}`,
      url: offering?.outputVideoUrl ?? null,
      file: 'elevator_animation.mp4',
      highlight: false,
    },
  ]

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-[#E4E4E4] bg-white p-8">
        <div className="mb-6 flex items-start justify-between">
          <h2 className="text-base font-semibold text-[#0A0A0A]">6 &nbsp; Render & Download</h2>
          <button onClick={handleBack} className="text-xs text-[#A3A3A3] transition-colors duration-[120ms] hover:text-[#525252]">Back</button>
        </div>

        {/* Download cards */}
        <div className="mb-8 grid grid-cols-3 gap-4">
          {downloads.map(d => (
            <div
              key={d.file}
              className={cn(
                'flex flex-col gap-3 rounded-lg border p-5',
                d.highlight ? 'border-[#0A0A0A] bg-[#FAFAFA]' : 'border-[#E4E4E4] bg-white'
              )}
            >
              <d.icon
                className={d.highlight ? 'text-[#0A0A0A]' : 'text-[#A3A3A3]'}
                style={{ width: 20, height: 20 }}
              />
              <div>
                <p className="text-sm font-semibold text-[#0A0A0A]">{d.title}</p>
                <p className="mt-0.5 text-xs text-[#A3A3A3]">{d.subtitle}</p>
              </div>
              <button
                onClick={() => handleDownload(d.url, d.file)}
                className={cn(
                  'mt-auto flex items-center gap-1.5 rounded-[5px] px-3 text-xs font-medium transition-colors duration-[120ms]',
                  d.highlight
                    ? 'bg-[#0A0A0A] text-white hover:bg-[#262626]'
                    : 'border border-[#E4E4E4] text-[#525252] hover:bg-[#F7F7F7]'
                )}
                style={{ height: 30 }}
              >
                <Download style={{ width: 12, height: 12 }} />
                Download
              </button>
            </div>
          ))}
        </div>

        {/* Zoomed component views */}
        {pins.length > 0 && (
          <div className="mb-8">
            <p className="mb-1 text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">Zoomed Component Views in Environment</p>
            <p className="mb-4 text-xs text-[#A3A3A3]">Each image is a zoomed-in crop of your environment photo, centred on where the component is placed.</p>
            <div className="flex flex-wrap gap-3">
              {pins.map(pin => (
                <div key={pin.componentKey} className="w-44 overflow-hidden rounded-lg border border-[#E4E4E4] bg-white">
                  <div
                    className="relative overflow-hidden bg-[#F5F5F5]"
                    style={{ aspectRatio: '1', height: 120 }}
                  >
                    {offering?.uploadedFileUrl ? (
                      <img
                        src={offering.uploadedFileUrl}
                        alt={`${COMP_LABELS[pin.componentKey]} zoomed view`}
                        className="absolute w-full h-full object-cover"
                        style={{
                          objectPosition: `${pin.x}% ${pin.y}%`,
                          transform: 'scale(2)',
                          transformOrigin: `${pin.x}% ${pin.y}%`,
                        }}
                      />
                    ) : (
                      <div className="w-full h-full bg-[#E4E4E4]" />
                    )}
                  </div>
                  <div className="p-2">
                    <div className="mb-2 flex items-center gap-1.5">
                      <span className="text-xs font-medium text-[#0A0A0A]">{COMP_LABELS[pin.componentKey]}</span>
                      <span className="rounded-[4px] bg-[#F5F5F5] px-1 py-0.5 text-[10px] text-[#A3A3A3]">zoomed</span>
                    </div>
                    <button
                      onClick={() => handleDownload(null, `salesnxt-${pin.componentKey}-zoom.png`)}
                      className="flex w-full items-center justify-center gap-1 rounded-[4px] border border-[#E4E4E4] py-1 text-[11px] font-medium text-[#525252] transition-colors duration-[120ms] hover:bg-[#F7F7F7]"
                    >
                      <Download style={{ width: 11, height: 11 }} />
                      Download
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Final outputs preview */}
        {(offering?.outputImageUrl || offering?.outputVideoUrl) && (
          <div className="mb-8 grid grid-cols-2 gap-4">
            {offering.outputImageUrl && (
              <div>
                <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">Final Image</p>
                <img
                  src={offering.outputImageUrl}
                  alt="Final rendered output"
                  className="w-full rounded-lg border border-[#E4E4E4] object-cover"
                  style={{ maxHeight: 240 }}
                />
              </div>
            )}
            {offering.outputVideoUrl && (
              <div>
                <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">Final Video</p>
                <video
                  src={offering.outputVideoUrl}
                  controls
                  className="w-full rounded-lg border border-[#E4E4E4]"
                  style={{ maxHeight: 240 }}
                />
              </div>
            )}
          </div>
        )}

        {/* Preview section */}
        <div>
          <div className="mb-3 flex items-center justify-between">
            <p className="text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">Preview</p>
            <div className="flex items-center gap-2">
              {(offering?.selectedComponents ?? []).map(k => (
                <button
                  key={k}
                  onClick={() => toggleFilter(k)}
                  aria-pressed={activeFilters.includes(k)}
                  disabled={!annotationsOn}
                  className={cn(
                    'rounded-[5px] px-2.5 text-xs font-medium transition-colors duration-[120ms] disabled:opacity-40',
                    activeFilters.includes(k) && annotationsOn
                      ? 'bg-[#0A0A0A] text-white'
                      : 'border border-[#E4E4E4] bg-white text-[#525252] hover:bg-[#F7F7F7]'
                  )}
                  style={{ height: 28 }}
                >
                  {COMP_LABELS[k]}
                </button>
              ))}
              <button
                onClick={() => setAnnotationsOn(v => !v)}
                className="flex items-center gap-1.5 rounded-[5px] border border-[#E4E4E4] bg-white px-2.5 text-xs font-medium text-[#525252] transition-colors duration-[120ms] hover:bg-[#F7F7F7]"
                style={{ height: 28 }}
                aria-label={annotationsOn ? 'Turn annotations off' : 'Turn annotations on'}
              >
                {annotationsOn
                  ? <Eye style={{ width: 12, height: 12 }} />
                  : <EyeOff style={{ width: 12, height: 12 }} />}
                {annotationsOn ? 'Annotations on' : 'Annotations off'}
              </button>
            </div>
          </div>
          <AnnotatedPreview
            imageUrl={offering?.uploadedFileUrl ?? null}
            pins={pins}
            annotationsEnabled={annotationsOn}
            activeFilters={activeFilters}
            labels={COMP_LABELS}
          />
        </div>
      </div>

      {/* Complete banner */}
      <div className="rounded-lg bg-[#0A0A0A] p-6 text-white">
        <h3 className="text-base font-semibold">Visualization complete</h3>
        <p className="mt-1 text-sm text-white/60">
          Save this visualization to your project. You'll then be able to build a Sales Brochure from the project screen.
        </p>
        {offering && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {offering.environments.map(e => (
              <span key={e} className="rounded-[4px] bg-white/10 px-2 py-0.5 text-xs capitalize">{e}</span>
            ))}
            {offering.selectedComponents.map(k => (
              <span key={k} className="rounded-[4px] bg-white/10 px-2 py-0.5 text-xs">{COMP_LABELS[k]}</span>
            ))}
          </div>
        )}
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={handleSave}
            className="rounded-[5px] bg-white px-4 text-sm font-medium text-[#0A0A0A] transition-colors duration-[120ms] hover:bg-white/90"
            style={{ paddingTop: 8, paddingBottom: 8 }}
          >
            Save & Return to Project
          </button>
        </div>
      </div>
    </div>
  )
}
