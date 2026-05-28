import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Play } from 'lucide-react'
import { useOfferingStore } from '../../../store/offeringStore'
import { VIDEO_MOTION_STYLES, VIDEO_QUALITIES } from '../../../lib/constants'
import { cn } from '../../../lib/utils'
import type { Offering } from '../../../types'

type MotionStyle = Offering['videoMotionStyle']
type Quality = Offering['videoQuality']

export default function Step5Video() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, setVideoSettings, goToStep } = useOfferingStore()

  const [motion, setMotion] = useState<MotionStyle>(currentOffering?.videoMotionStyle ?? 'zoom-in')
  const [quality, setQuality] = useState<Quality>(currentOffering?.videoQuality ?? '1080p')
  const [playing, setPlaying] = useState(false)

  const handlePlay = () => {
    setPlaying(true)
    setTimeout(() => setPlaying(false), 4000)
  }

  const motionLabel = VIDEO_MOTION_STYLES.find(m => m.value === motion)?.label ?? ''

  const getAnimStyle = (): React.CSSProperties => {
    if (!playing) return {}
    if (motion === 'zoom-in') return { animation: 'salesnxt-zoom 4s ease-in-out forwards' }
    if (motion === 'pan-lr') return { animation: 'salesnxt-pan-lr 4s ease-in-out forwards' }
    if (motion === 'pan-rl') return { animation: 'salesnxt-pan-rl 4s ease-in-out forwards' }
    return {}
  }

  const handleContinue = async () => {
    await setVideoSettings({ videoMotionStyle: motion, videoQuality: quality })
    goToStep(6)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/6`)
  }

  const handleBack = () => {
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/4`)
    goToStep(4)
  }

  const btnBase = 'rounded-[5px] border text-sm font-medium transition-colors duration-[120ms]'
  const btnActive = 'border-[#0A0A0A] bg-[#0A0A0A] text-white'
  const btnInactive = 'border-[#E4E4E4] bg-white text-[#374151] hover:border-[#C8C8C8]'

  return (
    <div className="rounded-lg border border-[#E4E4E4] bg-white p-8">
      <div className="mb-6 flex items-start justify-between">
        <h2 className="text-base font-semibold text-[#0A0A0A]">5 &nbsp; Video Settings</h2>
        <button onClick={handleBack} className="text-xs text-[#A3A3A3] transition-colors duration-[120ms] hover:text-[#525252]">Back</button>
      </div>

      <div className="flex gap-8">
        {/* Preview */}
        <div className="flex-1">
          <div
            className="relative cursor-pointer overflow-hidden rounded-lg bg-[#0A0A0A]"
            style={{ aspectRatio: '16/9' }}
            onClick={handlePlay}
            role="button"
            aria-label="Play video preview"
          >
            {currentOffering?.uploadedFileUrl ? (
              <img
                src={currentOffering.uploadedFileUrl}
                alt="Video preview"
                className="w-full h-full object-cover"
                style={getAnimStyle()}
              />
            ) : (
              <div className="w-full h-full bg-[#1A1A1A]" style={getAnimStyle()} />
            )}
            {!playing && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="flex items-center justify-center rounded-full bg-white/20 transition-colors duration-[120ms] hover:bg-white/30" style={{ width: 48, height: 48 }}>
                  <Play className="ml-0.5 text-white" style={{ width: 18, height: 18 }} />
                </div>
              </div>
            )}
          </div>
          <p className="mt-2 text-center text-xs text-[#A3A3A3]">{motionLabel}</p>
        </div>

        {/* Controls */}
        <div className="w-56 shrink-0 space-y-6">
          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">Motion Style</p>
            <div className="flex flex-col gap-1.5">
              {VIDEO_MOTION_STYLES.map(s => (
                <button
                  key={s.value}
                  onClick={() => setMotion(s.value as MotionStyle)}
                  className={cn(btnBase, 'px-3', motion === s.value ? btnActive : btnInactive)}
                  style={{ height: 34 }}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">Quality</p>
            <div className="grid grid-cols-2 gap-1.5">
              {VIDEO_QUALITIES.map(q => (
                <button
                  key={q}
                  onClick={() => setQuality(q as Quality)}
                  className={cn(btnBase, 'text-xs', quality === q ? btnActive : btnInactive)}
                  style={{ height: 34 }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-8 flex justify-end">
        <button
          onClick={handleContinue}
          className="rounded-[5px] bg-[#0A0A0A] px-5 text-sm font-medium text-white transition-colors duration-[120ms] hover:bg-[#262626]"
          style={{ height: 34 }}
        >
          Continue
        </button>
      </div>

      <style>{`
        @keyframes salesnxt-zoom { from { transform: scale(1); } to { transform: scale(1.3); } }
        @keyframes salesnxt-pan-lr { from { transform: translateX(-10%); } to { transform: translateX(10%); } }
        @keyframes salesnxt-pan-rl { from { transform: translateX(10%); } to { transform: translateX(-10%); } }
      `}</style>
    </div>
  )
}
