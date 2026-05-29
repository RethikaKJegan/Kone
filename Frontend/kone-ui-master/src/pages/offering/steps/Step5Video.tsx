import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Play } from 'lucide-react'
import apiClient from '../../../api/client'
import { getGuestSessionId, isGuestSession } from '../../../api/guestWorkflow'
import { useOfferingStore } from '../../../store/offeringStore'
import { VIDEO_MOTION_STYLES, VIDEO_QUALITIES } from '../../../lib/constants'
import { cn } from '../../../lib/utils'
import { toast } from '../../../hooks/useToast'
import type { Offering } from '../../../types'

type MotionStyle = Offering['videoMotionStyle']
type Quality = Offering['videoQuality']

export default function Step5Video() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, setVideoSettings, setCurrentOffering, goToStep } = useOfferingStore()

  const [motion, setMotion] = useState<MotionStyle>(currentOffering?.videoMotionStyle ?? 'zoom-in')
  const [quality, setQuality] = useState<Quality>(currentOffering?.videoQuality ?? '1080p')
  const [playing, setPlaying] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)
  const videoReady = !!currentOffering?.outputVideoUrl
    && currentOffering.videoMotionStyle === motion
    && currentOffering.videoQuality === quality
    && !loadFailed

  const selectMotion = (value: MotionStyle) => {
    setMotion(value)
    setLoadFailed(false)
    if (currentOffering?.outputVideoUrl) {
      setCurrentOffering({ ...currentOffering, outputVideoUrl: null })
    }
  }

  const selectQuality = (value: Quality) => {
    setQuality(value)
    setLoadFailed(false)
    if (currentOffering?.outputVideoUrl) {
      setCurrentOffering({ ...currentOffering, outputVideoUrl: null })
    }
  }

  const handlePlay = () => {
    setPlaying(true)
    setTimeout(() => setPlaying(false), 4000)
  }

  const motionLabel = VIDEO_MOTION_STYLES.find(m => m.value === motion)?.label ?? ''
  const isDoorFunctionality = motion === 'door-functionality'
  const videoStyles = VIDEO_MOTION_STYLES.filter(
    s => s.value !== 'door-functionality' || currentOffering?.selectedComponents.includes('door')
  )

  const handleContinue = async () => {
    setVideoSettings({ videoMotionStyle: motion, videoQuality: quality })
    if (isGuestSession() && projectId && currentOffering && !videoReady) {
      setGenerating(true)
      setLoadFailed(false)
      setCurrentOffering({ ...currentOffering, outputVideoUrl: null })
      try {
        const sessionId = await getGuestSessionId()
        await apiClient.post('/guest/video', {
          is_guest: true,
          session_id: sessionId,
          project_id: projectId,
          project_name: currentOffering.name,
          video_options: isDoorFunctionality
            ? { mode: 'door_functionality', duration_seconds: 8, speed: currentOffering.videoSpeed, quality }
            : { motion, speed: currentOffering.videoSpeed, quality },
        })

        for (let attempt = 0; attempt < 120; attempt += 1) {
          const { data } = await apiClient.get('/guest/status', {
            params: { session_id: sessionId, project_id: projectId },
          })

          if (data.status === 'video_ready' && data.video_url) {
            setLoadFailed(false)
            setCurrentOffering({ ...currentOffering, videoMotionStyle: motion, videoQuality: quality, outputVideoUrl: `${data.video_url}?v=${Date.now()}` })
            return
          }

          if (data.status === 'failed') {
            setLoadFailed(true)
            setCurrentOffering({ ...currentOffering, outputVideoUrl: null })
            toast(data.error || 'Video generation failed', 'destructive')
            return
          }

          await new Promise(resolve => setTimeout(resolve, 2000))
        }

        setLoadFailed(true)
        setCurrentOffering({ ...currentOffering, outputVideoUrl: null })
        toast('Video generation timed out. Check the API and logic terminals.', 'destructive')
      } catch (error) {
        setLoadFailed(true)
        setCurrentOffering({ ...currentOffering, outputVideoUrl: null })
        toast(error instanceof Error ? error.message : 'Video generation failed', 'destructive')
      } finally {
        setGenerating(false)
      }
      return
    }
    goToStep(6)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/6`)
  }

  const handleBack = () => {
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/3`)
    goToStep(3)
  }

  const btnBase = 'rounded-lg border text-[13px] font-semibold transition-all duration-[150ms]'
  const btnActive = 'border-[#1450F5] bg-[#1450F5] text-white shadow-sm'
  const btnInactive = 'border-[#E4E4E4] bg-white text-[#374151] hover:border-[#1450F5]/40'

  return (
    <div className="rounded-xl border border-[#E9ECEF] bg-white p-8 shadow-sm">
      <div className="mb-6 flex items-start justify-between">
        <h2 className="text-heading text-[15px] font-semibold text-[#111827]">5 &nbsp; Video Settings</h2>
        <button onClick={handleBack} className="text-xs font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#6B7280]">Back</button>
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
            {videoReady ? (
              <video
                src={currentOffering.outputVideoUrl ?? ''}
                controls
                className="h-full w-full object-contain"
                onError={() => {
                  setLoadFailed(true)
                  setCurrentOffering({ ...currentOffering, outputVideoUrl: null })
                  if (!generating) toast('Video preview failed to load. Generate it again.', 'destructive')
                }}
              />
            ) : generating ? (
              <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-[#1A1A1A] text-white">
                <div className="h-7 w-7 animate-spin rounded-full border-2 border-white/20 border-t-white" />
                <p className="text-sm font-medium">Generating video preview...</p>
              </div>
            ) : (currentOffering?.outputImageUrl ?? currentOffering?.uploadedFileUrl) ? (
              <img
                src={currentOffering.outputImageUrl ?? currentOffering.uploadedFileUrl ?? ''}
                alt="Video preview"
                className="h-full w-full object-contain"
              />
            ) : (
              <div className="h-full w-full bg-[#1A1A1A]" />
            )}
            {!videoReady && !playing && (
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
            <p className="label-caps mb-2">Motion Style</p>
            <div className="flex flex-col gap-1.5">
              {videoStyles.map(s => (
                <button
                  key={s.value}
                  onClick={() => selectMotion(s.value as MotionStyle)}
                  className={cn(btnBase, 'px-3', motion === s.value ? btnActive : btnInactive)}
                  style={{ height: 34 }}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="label-caps mb-2">Quality</p>
            <div className="grid grid-cols-2 gap-1.5">
              {VIDEO_QUALITIES.map(q => (
                <button
                  key={q}
                  onClick={() => selectQuality(q as Quality)}
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
          disabled={generating}
          className="rounded-lg bg-[#1450F5] px-6 text-[13px] font-semibold text-white transition-all duration-[150ms] hover:bg-[#1040D0] hover:shadow-md hover:shadow-[#1450F5]/20 disabled:cursor-not-allowed disabled:opacity-40"
          style={{ height: 38 }}
        >
          {generating ? 'Generating...' : videoReady ? 'Continue' : 'Generate Preview'}
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
