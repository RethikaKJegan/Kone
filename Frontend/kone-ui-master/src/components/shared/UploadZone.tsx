import { useRef, useState, useCallback } from 'react'
import { Upload } from 'lucide-react'
import { cn } from '../../lib/utils'

interface Props {
  onFile: (file: File) => void
  accept?: string
  className?: string
}

export function UploadZone({ onFile, accept = '.jpg,.jpeg,.png,image/jpeg,image/png', className }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) onFile(file)
    },
    [onFile]
  )

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) onFile(file)
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Upload image — drag and drop or click to browse"
      onClick={() => inputRef.current?.click()}
      onKeyDown={e => e.key === 'Enter' && inputRef.current?.click()}
      onDragOver={e => { e.preventDefault(); setIsDragging(true) }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      className={cn(
        'flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-12 text-center cursor-pointer transition-all duration-[120ms]',
        isDragging
          ? 'border-[#0A0A0A] bg-[#FAFAFA] scale-[1.01]'
          : 'border-[#E4E4E4] bg-white hover:border-[#0A0A0A] hover:bg-[#FAFAFA]',
        className
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleChange}
        className="sr-only"
        aria-hidden="true"
      />
      <div className="flex flex-col items-center gap-3">
        <Upload className="text-[#A3A3A3]" style={{ width: 28, height: 28 }} />
        <div>
          <p className="text-sm font-medium text-[#374151]">Upload a clear picture</p>
          <p className="mt-1 text-xs text-[#A3A3A3]">Drag & drop or click to browse</p>
        </div>
        <div className="mt-2 w-full max-w-xs rounded-lg border border-[#E4E4E4] bg-[#F5F5F5] px-4 py-3 text-left text-xs text-[#525252]">
          <p className="mb-1.5 font-medium text-[#374151]">Supported formats</p>
          <ul className="space-y-1">
            <li>· JPEG and PNG are only supported</li>
            <li>· 4:3 aspect ratio recommended</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
