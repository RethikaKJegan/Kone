import { useEffect, useRef, useState } from 'react'

type ActionPopupProps = {
  entityLabel: string
  entityName: string
  onClose: () => void
  onRename: (name: string) => Promise<void>
  onDelete: () => Promise<void>
}

type PopupMode = 'menu' | 'rename' | 'delete-warning' | 'delete-confirm'

export function ActionPopup({ entityLabel, entityName, onClose, onRename, onDelete }: ActionPopupProps) {
  const ref = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [mode, setMode] = useState<PopupMode>('menu')
  const [name, setName] = useState(entityName)
  const [deleteText, setDeleteText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handlePointerDown)
    return () => document.removeEventListener('mousedown', handlePointerDown)
  }, [onClose])

  useEffect(() => {
    if (mode === 'rename') inputRef.current?.focus()
  }, [mode])

  const handleRename = async () => {
    const trimmed = name.trim()
    if (trimmed.length < 2 || trimmed.length > 80) {
      setError(`${entityLabel} name must be 2-80 characters`)
      return
    }
    if (trimmed === entityName) {
      onClose()
      return
    }
    setLoading(true)
    setError('')
    try {
      await onRename(trimmed)
      onClose()
    } catch {
      setError(`Could not rename this ${entityLabel}. Please try again.`)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    if (deleteText !== 'DELETE') return
    setLoading(true)
    setError('')
    try {
      await onDelete()
      onClose()
    } catch {
      setError(`Could not delete this ${entityLabel}. Please try again.`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      ref={ref}
      className="absolute right-0 top-8 z-30 w-72 overflow-hidden rounded-lg border border-[#E5E7EB] bg-white shadow-xl shadow-[#111827]/10"
      onClick={event => event.stopPropagation()}
      role="dialog"
      aria-label={`${entityLabel} actions`}
    >
      {mode === 'menu' && (
        <div className="py-1">
          <button
            type="button"
            onClick={() => {
              setMode('rename')
              setError('')
            }}
            className="block w-full px-4 py-2.5 text-left text-sm font-medium text-[#374151] hover:bg-[#F3F4F6]"
          >
            Rename
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('delete-warning')
              setError('')
            }}
            className="block w-full px-4 py-2.5 text-left text-sm font-semibold text-red-600 hover:bg-red-50"
          >
            Delete
          </button>
        </div>
      )}

      {mode === 'rename' && (
        <div className="space-y-3 p-4">
          <div>
            <p className="text-sm font-semibold text-[#111827]">Rename {entityLabel}</p>
            <p className="mt-1 text-xs text-[#6B7280]">Update this {entityLabel} name only.</p>
          </div>
          <input
            ref={inputRef}
            value={name}
            onChange={event => {
              setName(event.target.value)
              setError('')
            }}
            onKeyDown={event => {
              if (event.key === 'Enter') handleRename()
              if (event.key === 'Escape') onClose()
            }}
            className="w-full rounded-md border border-[#D1D5DB] px-3 text-sm text-[#111827] outline-none transition-colors focus:border-[#1450F5] focus:ring-1 focus:ring-[#1450F5]"
            style={{ height: 36 }}
          />
          {error && <p className="rounded-md bg-red-50 px-3 py-2 text-xs font-medium text-red-700">{error}</p>}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="rounded-md border border-[#E5E7EB] bg-white px-3 text-xs font-semibold text-[#374151] hover:bg-[#F9FAFB] disabled:opacity-50"
              style={{ height: 32 }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleRename}
              disabled={loading}
              className="rounded-md bg-[#1450F5] px-3 text-xs font-semibold text-white hover:bg-[#1040D0] disabled:opacity-50"
              style={{ height: 32 }}
            >
              {loading ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
      )}

      {mode === 'delete-warning' && (
        <div className="space-y-3 p-4">
          <div>
            <p className="text-sm font-semibold text-[#111827]">Delete {entityLabel}?</p>
            <p className="mt-1 text-xs leading-relaxed text-[#6B7280]">
              This will remove "{entityName}" and its saved data. Continue to final confirmation.
            </p>
          </div>
          {error && <p className="rounded-md bg-red-50 px-3 py-2 text-xs font-medium text-red-700">{error}</p>}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="rounded-md border border-[#E5E7EB] bg-white px-3 text-xs font-semibold text-[#374151] hover:bg-[#F9FAFB] disabled:opacity-50"
              style={{ height: 32 }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => setMode('delete-confirm')}
              disabled={loading}
              className="rounded-md border border-red-200 bg-red-50 px-3 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50"
              style={{ height: 32 }}
            >
              Continue
            </button>
          </div>
        </div>
      )}

      {mode === 'delete-confirm' && (
        <div className="space-y-3 p-4">
          <div>
            <p className="text-sm font-semibold text-red-700">Final confirmation</p>
            <p className="mt-1 text-xs leading-relaxed text-[#6B7280]">
              Type <span className="font-bold text-[#111827]">DELETE</span> to permanently delete this {entityLabel}.
            </p>
          </div>
          <input
            value={deleteText}
            onChange={event => {
              setDeleteText(event.target.value)
              setError('')
            }}
            className="w-full rounded-md border border-red-200 px-3 text-sm text-[#111827] outline-none transition-colors focus:border-red-500 focus:ring-1 focus:ring-red-500"
            style={{ height: 36 }}
            placeholder="DELETE"
          />
          {error && <p className="rounded-md bg-red-50 px-3 py-2 text-xs font-medium text-red-700">{error}</p>}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="rounded-md border border-[#E5E7EB] bg-white px-3 text-xs font-semibold text-[#374151] hover:bg-[#F9FAFB] disabled:opacity-50"
              style={{ height: 32 }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleDelete}
              disabled={loading || deleteText !== 'DELETE'}
              className="rounded-md bg-red-600 px-3 text-xs font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-40"
              style={{ height: 32 }}
            >
              {loading ? 'Deleting...' : 'Delete'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
