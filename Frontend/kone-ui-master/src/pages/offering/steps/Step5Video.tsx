import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Loader2, Play } from 'lucide-react'
import apiClient from '../../../api/client'
import { getGuestSessionId, isGuestSession } from '../../../api/guestWorkflow'
import { useOfferingStore } from '../../../store/offeringStore'
import { VIDEO_MOTION_STYLES, VIDEO_QUALITIES } from '../../../lib/constants'
import { cn } from '../../../lib/utils'
import { toast } from '../../../hooks/useToast'
import type { Offering } from '../../../types'

type MotionStyle = Offering['videoMotionStyle']
type Quality = Offering['videoQuality']

function availableMotionStyle(value: string | undefined): MotionStyle {
  if (value === 'pan-lr' || value === 'pan-rl') return 'pan'
  if (value === 'pan' || value === 'door-functionality' || value === 'zoom-in') return value
  return 'zoom-in'
}

function imageIdFromOffering(offering: Offering | null) {
  if (!offering) return null
  if (offering.imageId) return offering.imageId
  const fromInput = offering.inputImagePath?.match(/\/uploads\/([^/]+)\/input\.jpg(?:\?.*)?$/)
  if (fromInput?.[1]) return fromInput[1]
  const fromOutput = (offering.outputImageUrl || offering.uploadedFileUrl || '').match(/\/output\/([^/?]+)\/final_output\.png(?:\?.*)?$/)
  return fromOutput?.[1] ?? null
}

function formatDuration(seconds: number) {
  const safeSeconds = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(safeSeconds / 60)
  const remainingSeconds = safeSeconds % 60
  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`
}

export default function Step5Video() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const {
    currentOffering,
    setCurrentOffering,
    goToStep,
    videoGenerations,
    startVideoGeneration,
    finishVideoGeneration,
  } = useOfferingStore()

  const [motion, setMotion] = useState<MotionStyle>(availableMotionStyle(currentOffering?.videoMotionStyle))
  const [quality, setQuality] = useState<Quality>(currentOffering?.videoQuality ?? '1080p')
  const [playing, setPlaying] = useState(false)
  const activeVideoGeneration = currentOffering ? videoGenerations[currentOffering.id] : undefined
  const resumePollingRef = useRef(false)
  const [loadFailed, setLoadFailed] = useState(false)
  const [progressNow, setProgressNow] = useState(Date.now())
  const persistedGenerating = Boolean(currentOffering?.pipelineStatus === 'processing' && currentOffering?.savedStep === 5 && !currentOffering?.outputVideoUrl)
  const generating = Boolean(activeVideoGeneration || persistedGenerating)
  const generationStartedAt = activeVideoGeneration?.startedAt ?? null
  const selectedVideoMatchesOffering = currentOffering?.videoMotionStyle === motion
    && currentOffering?.videoQuality === quality
  const videoReady = !!currentOffering?.outputVideoUrl
    && selectedVideoMatchesOffering
    && !loadFailed

  const clearStaleVideoForSelection = (nextMotion: MotionStyle, nextQuality: Quality) => {
    if (!currentOffering) return
    setCurrentOffering({
      ...currentOffering,
      videoMotionStyle: nextMotion,
      videoQuality: nextQuality,
      outputVideoUrl: null,
      outputVideoPath: null,
      videoGenerated: false,
      downloadUrl: null,
      pipelineStatus: currentOffering.outputImageUrl ? 'preview_ready' : currentOffering.pipelineStatus,
    })
    if (!isGuestSession()) {
      apiClient.patch(`/offerings/${currentOffering.id}`, {
        videoMotionStyle: nextMotion,
        videoQuality: nextQuality,
        outputVideoUrl: null,
        outputVideoPath: null,
        downloadUrl: null,
        pipelineStatus: currentOffering.outputImageUrl ? 'preview_ready' : currentOffering.pipelineStatus,
        lastError: null,
      }).catch(() => {})
    }
  }

  const selectMotion = (value: MotionStyle) => {
    if (generating) return
    setMotion(value)
    setLoadFailed(false)
    if (value !== motion) clearStaleVideoForSelection(value, quality)
  }

  const selectQuality = (value: Quality) => {
    if (generating) return
    setQuality(value)
    setLoadFailed(false)
    if (value !== quality) clearStaleVideoForSelection(motion, value)
  }

  const handlePlay = () => {
    if (generating) return
    setPlaying(true)
    setTimeout(() => setPlaying(false), 4000)
  }

  const motionLabel = VIDEO_MOTION_STYLES.find(m => m.value === motion)?.label ?? ''
  const isDoorFunctionality = motion === 'door-functionality'
  const videoStyles = VIDEO_MOTION_STYLES
  const effectiveImageId = imageIdFromOffering(currentOffering)
  const elapsedSeconds = generationStartedAt ? (progressNow - generationStartedAt) / 1000 : 0

  useEffect(() => {
    if (!activeVideoGeneration) return
    setMotion(activeVideoGeneration.motion)
    setQuality(activeVideoGeneration.quality)
    setProgressNow(Date.now())
  }, [activeVideoGeneration?.startedAt, activeVideoGeneration?.motion, activeVideoGeneration?.quality])


  useEffect(() => {
    if (!generating) return undefined
    const interval = window.setInterval(() => setProgressNow(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [generating])

  useEffect(() => {
    if (!currentOffering || generating || isGuestSession()) return
    let cancelled = false

    const validateStoredVideo = async () => {
      if (!currentOffering.outputVideoUrl) return
      try {
        const { data } = await apiClient.post<Offering>(`/offerings/${currentOffering.id}/render`)
        if (cancelled) return
        if (!data.outputVideoUrl) {
          setCurrentOffering({
            ...data,
            outputVideoUrl: null,
            outputVideoPath: null,
            videoGenerated: false,
            downloadUrl: null,
          })
        }
      } catch {
        // Leave the current page usable; generate will replace stale state.
      }
    }

    validateStoredVideo()
    return () => {
      cancelled = true
    }
  }, [currentOffering?.id, currentOffering?.outputVideoUrl, generating, setCurrentOffering])

  useEffect(() => {
    if (!currentOffering || !persistedGenerating || activeVideoGeneration) return
    startVideoGeneration(currentOffering.id, {
      startedAt: Date.now(),
      motion: currentOffering.videoMotionStyle,
      quality: currentOffering.videoQuality,
    })
  }, [activeVideoGeneration, currentOffering, persistedGenerating, startVideoGeneration])

  useEffect(() => {
    if (!currentOffering || !generating || isGuestSession()) return undefined
    let cancelled = false

    const pollExistingVideo = async () => {
      if (resumePollingRef.current) return
      resumePollingRef.current = true
      try {
        const { data } = await apiClient.post<Offering>(`/offerings/${currentOffering.id}/render`)
        if (cancelled) return
        if (data.outputVideoUrl) {
          setLoadFailed(false)
          finishVideoGeneration(currentOffering.id)
          setCurrentOffering({
            ...data,
            outputVideoUrl: `${data.outputVideoUrl}${data.outputVideoUrl.includes('?') ? '&' : '?'}v=${Date.now()}`,
            videoGenerated: true,
            pipelineStatus: 'video_ready',
          })
        } else if (data.pipelineStatus === 'failed') {
          finishVideoGeneration(currentOffering.id)
          setLoadFailed(true)
          setCurrentOffering(data)
          toast(data.lastError || 'Video generation failed', 'destructive')
        }
      } catch {
        // Keep polling; the long-running generation may still be active.
      } finally {
        resumePollingRef.current = false
      }
    }

    pollExistingVideo()
    const interval = window.setInterval(pollExistingVideo, 3000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [currentOffering, finishVideoGeneration, generating, setCurrentOffering])

  useEffect(() => {
    if (!currentOffering || !generating || !isGuestSession() || !projectId) return undefined
    let cancelled = false

    const pollGuestVideo = async () => {
      try {
        const sessionId = await getGuestSessionId()
        const { data } = await apiClient.get('/guest/status', {
          params: { session_id: sessionId, project_id: projectId },
        })
        if (cancelled) return
        if (data.status === 'video_ready' && data.video_url) {
          setLoadFailed(false)
          finishVideoGeneration(currentOffering.id)
          setCurrentOffering({
            ...currentOffering,
            outputVideoUrl: `${data.video_url}?v=${Date.now()}`,
            videoGenerated: true,
            pipelineStatus: 'video_ready',
          })
        } else if (data.status === 'failed') {
          finishVideoGeneration(currentOffering.id)
          setLoadFailed(true)
          toast(data.error || 'Video generation failed', 'destructive')
        }
      } catch {
        // Keep polling; refresh recovery is best-effort for guest sessions.
      }
    }

    pollGuestVideo()
    const interval = window.setInterval(pollGuestVideo, 3000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [currentOffering, finishVideoGeneration, generating, projectId, setCurrentOffering])

  const startGenerationTimer = (startedAt = Date.now()) => {
    setProgressNow(startedAt)
    if (currentOffering) {
      startVideoGeneration(currentOffering.id, { startedAt, motion, quality })
    }
  }

  const handleGeneratePreview = async () => {
    if (generating) return
    const videoOptions = isDoorFunctionality
      ? { engine: 'wan2.2', mode: 'door_functionality', duration_seconds: 8, speed: currentOffering?.videoSpeed, quality }
      : { engine: 'wan2.2', motion, speed: currentOffering?.videoSpeed, quality }

    if (isGuestSession() && projectId && currentOffering) {
      startGenerationTimer()
      setLoadFailed(false)
      try {
        const sessionId = await getGuestSessionId()
        await apiClient.post('/guest/video', {
          is_guest: true,
          session_id: sessionId,
          project_id: projectId,
          project_name: currentOffering.name,
          video_options: videoOptions,
        })

        for (let attempt = 0; attempt < 120; attempt += 1) {
          const { data } = await apiClient.get('/guest/status', {
            params: { session_id: sessionId, project_id: projectId },
          })

          if (data.status === 'video_ready' && data.video_url) {
            setLoadFailed(false)
            setCurrentOffering({ ...currentOffering, videoMotionStyle: motion, videoQuality: quality, outputVideoUrl: `${data.video_url}?v=${Date.now()}`, videoGenerated: true })
            return
          }

          if (data.status === 'failed') {
            setLoadFailed(true)
            toast(data.error || 'Video generation failed', 'destructive')
            return
          }

          await new Promise(resolve => setTimeout(resolve, 2000))
        }

        setLoadFailed(true)
        toast('Video generation timed out. Check the API and logic terminals.', 'destructive')
      } catch (error) {
        setLoadFailed(true)
        toast(error instanceof Error ? error.message : 'Video generation failed', 'destructive')
      } finally {
        finishVideoGeneration(currentOffering.id)
      }
      return
    }

    if (!isGuestSession() && currentOffering) {
      if (!effectiveImageId) {
        toast('Upload an image before generating the video preview.', 'destructive')
        return
      }
      if (!currentOffering.outputImagePath && !currentOffering.outputImageUrl) {
        toast('Generate the image preview before generating the video.', 'destructive')
        return
      }

      startGenerationTimer()
      setLoadFailed(false)
      setCurrentOffering({
        ...currentOffering,
        videoMotionStyle: motion,
        videoQuality: quality,
        outputVideoUrl: null,
        outputVideoPath: null,
        videoGenerated: false,
        downloadUrl: null,
        pipelineStatus: 'processing',
        savedStep: 5,
      })

      try {
        await apiClient.patch(`/offerings/${currentOffering.id}`, {
          videoMotionStyle: motion,
          videoQuality: quality,
          outputVideoUrl: null,
          outputVideoPath: null,
          downloadUrl: null,
          pipelineStatus: 'processing',
          savedStep: 5,
          lastError: null,
        })

        await apiClient.post('/video/generate', {
          imageId: effectiveImageId,
          offeringId: currentOffering.id,
          sourceImageUrl:
            currentOffering.previewImagePath
            ?? currentOffering.outputImageUrl
            ?? currentOffering.outputImagePath,
          videoOptions,
          }, { timeout: 0 })

        setLoadFailed(false)
        setCurrentOffering({
          ...currentOffering,
          videoMotionStyle: motion,
          videoQuality: quality,
          outputVideoUrl: null,
          outputVideoPath: null,
          videoGenerated: false,
          downloadUrl: null,
          pipelineStatus: 'processing',
          savedStep: 5,
          lastError: null,
        })
      } catch (error) {
        setLoadFailed(true)
        const responseMessage = typeof error === 'object' && error !== null && 'response' in error
          ? (error as { response?: { data?: { message?: string; error?: string } } }).response?.data?.message
            ?? (error as { response?: { data?: { message?: string; error?: string } } }).response?.data?.error
          : null
        const message = summarizeVideoError(responseMessage || (error instanceof Error ? error.message : 'Video generation failed'))
        setCurrentOffering({
          ...currentOffering,
          videoMotionStyle: motion,
          videoQuality: quality,
          pipelineStatus: 'failed',
          lastError: message,
        })
        await apiClient.patch(`/offerings/${currentOffering.id}`, {
          pipelineStatus: 'failed',
          lastError: message,
        }).catch(() => {})
        finishVideoGeneration(currentOffering.id)
        toast(message, 'destructive')
      }
      return
    }
  }

  const handleSkipVideoGeneration = () => {
    if (generating) return
    if (!currentOffering?.outputImageUrl) {
      toast("Generate the image preview before skipping video generation.", "destructive")
      return
    }
    setLoadFailed(false)
    setCurrentOffering({
      ...currentOffering,
      outputVideoUrl: null,
      videoGenerated: false,
      downloadUrl: null,
      renderComplete: true,
      pipelineStatus: "preview_ready",
    })
    goToStep(6)
    navigate("/projects/" + projectId + "/offerings/" + offeringId + "/step/6")
  }

  const handleContinue = () => {
    if (!videoReady) {
      toast('Generate the video preview before opening Downloads.', 'destructive')
      return
    }
    goToStep(6)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/6`)
  }

  const handleBack = () => {
    if (generating) return
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
        <button
          onClick={handleBack}
          disabled={generating}
          className="text-xs font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#6B7280] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-[#9CA3AF]"
        >
          Back
        </button>
      </div>
      <p className="mb-5 text-sm font-medium text-[#374151]">
        Select your required motion style and quality, then click Generate Preview to see the video.
      </p>

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
                key={currentOffering.outputVideoUrl}
                src={currentOffering.outputVideoUrl ?? ''}
                controls
                className="h-full w-full object-contain"
                onError={() => {
                  setLoadFailed(true)
                  setCurrentOffering({ ...currentOffering, outputVideoUrl: null })
                  if (!generating) toast('Video preview failed to load. Generate it again.', 'destructive')
                }}
              />
            ) : (currentOffering?.outputImageUrl ?? currentOffering?.uploadedFileUrl) ? (
              <img
                src={currentOffering.outputImageUrl ?? currentOffering.uploadedFileUrl ?? ''}
                alt="Video preview"
                className="h-full w-full object-contain"
              />
            ) : (
              <div className="h-full w-full bg-[#1A1A1A]" />
            )}
            {!videoReady && !playing && !generating && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="flex items-center justify-center rounded-full bg-white/20 transition-colors duration-[120ms] hover:bg-white/30" style={{ width: 48, height: 48 }}>
                  <Play className="ml-0.5 text-white" style={{ width: 18, height: 18 }} />
                </div>
              </div>
            )}
            {generating && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/55 px-8 text-white backdrop-blur-[1px]">
                <div className="w-full max-w-sm">
                  <div className="mb-4 flex items-center justify-between gap-4">
                    <div className="flex min-w-0 items-center gap-2">
                      <Loader2 className="shrink-0 animate-spin text-white" style={{ width: 18, height: 18 }} />
                      <div className="min-w-0">
                        <p className="text-sm font-semibold">Generating video</p>
                        <p className="text-xs text-white/70">{formatDuration(elapsedSeconds)} elapsed</p>
                      </div>
                    </div>
                  </div>
                  <div className="mb-2 h-2 overflow-hidden rounded-full bg-white/20">
                    <div className="h-full w-full animate-pulse rounded-full bg-[#1450F5]" />
                  </div>
                  <p className="text-xs text-white/80">Live elapsed time updates while generation is running.</p>
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
                  className={cn(
                    btnBase,
                    'px-3',
                    motion === s.value ? btnActive : btnInactive,
                    generating && 'cursor-not-allowed opacity-50 hover:border-[#E4E4E4]'
                  )}
                  disabled={generating}
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
                  className={cn(btnBase, 'text-xs', quality === q ? btnActive : btnInactive, generating && 'cursor-not-allowed opacity-50 hover:border-[#E4E4E4]')}
                  disabled={generating}
                  style={{ height: 34 }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-8 flex justify-end gap-3">
        <button
          onClick={handleSkipVideoGeneration}
          disabled={generating || !currentOffering?.outputImageUrl}
          className="rounded-lg border border-[#D7E0FF] bg-white px-6 text-[13px] font-semibold text-[#1450F5] transition-all duration-[150ms] hover:bg-[#F5F8FF] disabled:cursor-not-allowed disabled:opacity-40"
          style={{ height: 38 }}
        >
          Skip video generation
        </button>
        <button
          onClick={handleGeneratePreview}
          disabled={generating}
          className="rounded-lg bg-[#1450F5] px-6 text-[13px] font-semibold text-white transition-all duration-[150ms] hover:bg-[#1040D0] hover:shadow-md hover:shadow-[#1450F5]/20 disabled:cursor-not-allowed disabled:opacity-40"
          style={{ height: 38 }}
        >
          {generating ? 'Generating...' : 'Generate Preview'}
        </button>
        <button
          onClick={handleContinue}
          disabled={!videoReady || generating}
          className="rounded-lg bg-[#0A0A0A] px-6 text-[13px] font-semibold text-white transition-all duration-[150ms] hover:bg-[#262626] disabled:cursor-not-allowed disabled:opacity-40"
          style={{ height: 38 }}
        >
          Continue
        </button>
      </div>

      <style>{`
        @keyframes salesnxt-zoom { from { transform: scale(1); } to { transform: scale(1.3); } }
      `}</style>
    </div>
  )
}

function summarizeVideoError(message: string) {
  if (message.includes('No CUDA GPUs are available') || message.includes('sees no GPU')) {
    return 'Wan2.2 needs CUDA, but the Wan Python environment cannot see a GPU. Check the Python logic terminal.'
  }
  const missingModule = message.match(/No module named ['"]([^'"]+)['"]/)
  if (missingModule?.[1]) {
    return `Wan2.2 is missing Python dependency: ${missingModule[1]}`
  }
  const firstLine = message.split('\n').find(line => line.trim())?.trim() || message
  return firstLine.length > 240 ? `${firstLine.slice(0, 237)}...` : firstLine
}
