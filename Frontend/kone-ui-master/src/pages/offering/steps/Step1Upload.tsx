import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import apiClient from '../../../api/client'
import { getGuestSessionId, isGuestSession } from '../../../api/guestWorkflow'
import { useOfferingStore } from '../../../store/offeringStore'
import { UploadZone } from '../../../components/shared/UploadZone'
import { toast } from '../../../hooks/useToast'

export default function Step1Upload() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, setUpload, goToStep } = useOfferingStore()
  const [checkStatus, setCheckStatus] = useState<'idle' | 'checking' | 'passed' | 'failed'>('idle')
  const [precheckReason, setPrecheckReason] = useState<string | null>(null)

  const hasFile = !!currentOffering?.uploadedFileName

  const handleFile = async (file: File) => {
    const isImage = file.type.match(/^image\/(jpeg|png)$/) || /\.(jpe?g|png)$/i.test(file.name)
    if (!isImage) {
      toast('Please upload a JPG or PNG image', 'destructive')
      return
    }
    setCheckStatus('idle')
    setPrecheckReason(null)
    try {
      await setUpload(file)
    } catch {
      toast('Upload failed. Check that API is running on port 4000 and UI mock API is disabled.', 'destructive')
    }
  }

  const handleCheck = async () => {
    if (!projectId || !currentOffering) return
    if (!isGuestSession()) {
      setCheckStatus('passed')
      return
    }
    setCheckStatus('checking')
    setPrecheckReason(null)
    const sessionId = await getGuestSessionId()
    const { data } = await apiClient.post('/guest/precheck', {
      is_guest: true,
      session_id: sessionId,
      project_id: projectId,
      project_name: currentOffering.name,
    })
    setCheckStatus(data.ok ? 'passed' : 'failed')
    setPrecheckReason(data.ok ? null : data.reason ?? 'Image failed precheck')
  }

  const handleContinue = () => {
    goToStep(2)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/2`)
  }

  return (
    <div className="kone-enter rounded-xl border border-[#E9ECEF] bg-white p-8 shadow-sm">
      <h2 className="text-heading mb-7 text-[15px] font-semibold text-[#111827]">
        1 &nbsp; Upload picture / video
      </h2>

      {hasFile && currentOffering?.uploadedFileUrl ? (
        <div className="space-y-3">
          <div
            className="relative cursor-pointer overflow-hidden rounded-xl bg-[#F5F6F8] ring-2 ring-transparent transition-all duration-200 hover:ring-[#1450F5]/30"
            style={{ aspectRatio: '4/3', maxHeight: 340 }}
            onClick={() => {
              const input = document.createElement('input')
              input.type = 'file'
              input.accept = '.jpg,.jpeg,.png,image/jpeg,image/png'
              input.onchange = e => {
                const f = (e.target as HTMLInputElement).files?.[0]
                if (f) handleFile(f)
              }
              input.click()
            }}
            role="button"
            tabIndex={0}
            aria-label="Click to replace uploaded file"
          >
            <img
              src={currentOffering.uploadedFileUrl}
              alt={currentOffering.uploadedFileName ?? 'Uploaded image'}
              className="h-full w-full object-cover transition-transform duration-300 hover:scale-[1.01]"
            />
          </div>
          <div className="flex items-center justify-between">
            <p className="text-[13px] font-medium text-[#374151]">{currentOffering.uploadedFileName}</p>
            <p className="text-[12px] text-[#9CA3AF]">Click image to replace</p>
          </div>
        </div>
      ) : (
        <UploadZone onFile={handleFile} />
      )}

      <div className="mt-7 flex justify-end gap-3">
        {precheckReason && <p className="mr-auto text-[12px] font-medium text-red-600">{precheckReason}</p>}
        {checkStatus === 'passed' ? (
          <button
            onClick={handleContinue}
            className="rounded-lg bg-[#1450F5] px-6 text-[13px] font-semibold text-white transition-all duration-[150ms] hover:bg-[#1040D0] hover:shadow-md hover:shadow-[#1450F5]/20"
            style={{ height: 38 }}
          >
            Continue
          </button>
        ) : checkStatus === 'failed' ? (
          <button
            onClick={() => setCheckStatus('idle')}
            className="rounded-lg bg-[#1450F5] px-6 text-[13px] font-semibold text-white transition-all duration-[150ms] hover:bg-[#1040D0] hover:shadow-md hover:shadow-[#1450F5]/20"
            style={{ height: 38 }}
          >
            Re-upload
          </button>
        ) : (
          <button
            onClick={handleCheck}
            disabled={!hasFile || checkStatus === 'checking'}
            className="rounded-lg bg-[#1450F5] px-6 text-[13px] font-semibold text-white transition-all duration-[150ms] hover:bg-[#1040D0] hover:shadow-md hover:shadow-[#1450F5]/20 disabled:cursor-not-allowed disabled:opacity-40"
            style={{ height: 38 }}
          >
            {checkStatus === 'checking' ? 'Checking...' : 'Check'}
          </button>
        )}
      </div>
    </div>
  )
}
