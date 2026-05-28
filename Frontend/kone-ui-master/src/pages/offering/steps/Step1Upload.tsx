import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useOfferingStore } from '../../../store/offeringStore'
import { UploadZone } from '../../../components/shared/UploadZone'
import { toast } from '../../../hooks/useToast'

export default function Step1Upload() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, setUpload, goToStep } = useOfferingStore()
  const [checked, setChecked] = useState(false)

  const hasFile = !!currentOffering?.uploadedFileName

  const handleFile = async (file: File) => {
    if (!file.type.match(/^image\/(jpeg|png)$/)) {
      toast('Upload a JPEG or PNG image')
      return
    }
    setChecked(false)
    await setUpload(file)
  }

  const handleCheck = () => setChecked(true)

  const handleContinue = () => {
    goToStep(2)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/2`)
  }

  return (
    <div className="kone-enter rounded-lg border border-[#E4E4E4] bg-white p-8">
      <h2 className="mb-6 text-base font-semibold text-[#0A0A0A]">1 &nbsp; Upload picture</h2>

      {hasFile && currentOffering?.uploadedFileUrl ? (
        <div className="space-y-3">
          <div
            className="relative cursor-pointer overflow-hidden rounded-lg bg-[#F5F5F5] ring-2 ring-transparent transition-all duration-200 hover:ring-[#1450F5]/30"
            style={{ aspectRatio: '4/3', maxHeight: 320 }}
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
              className="w-full h-full object-cover transition-transform duration-300 hover:scale-[1.01]"
            />
          </div>
          <p className="text-sm font-medium text-[#374151]">{currentOffering.uploadedFileName}</p>
          <p className="text-xs text-[#A3A3A3]">Click to replace</p>
        </div>
      ) : (
        <UploadZone onFile={handleFile} />
      )}

      <div className="mt-6 flex justify-end gap-3">
        {!checked ? (
          <button
            onClick={handleCheck}
            disabled={!hasFile}
            className="rounded-[5px] bg-[#0A0A0A] px-5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
            style={{ height: 34 }}
          >
            Check
          </button>
        ) : (
          <button
            onClick={handleContinue}
            className="rounded-[5px] bg-[#0A0A0A] px-5 text-sm font-medium text-white"
            style={{ height: 34 }}
          >
            Continue →
          </button>
        )}
      </div>
    </div>
  )
}
