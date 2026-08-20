import { AlertTriangle } from 'lucide-react'
import { SAFE_SYSTEM_ERROR_MESSAGE } from '../../lib/safeErrors'

type SystemIssueProps = {
  title?: string
  message?: string
}

export function SystemIssue({
  title = 'We are working on it',
  message = SAFE_SYSTEM_ERROR_MESSAGE,
}: SystemIssueProps) {
  return (
    <div className="rounded-lg border border-[#E4E4E4] bg-white p-6">
      <div className="flex items-start gap-4">
        <div className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#EFF6FF]">
          <span className="absolute h-12 w-12 animate-ping rounded-full bg-[#1450F5]/15" />
          <span className="absolute h-9 w-9 animate-pulse rounded-full bg-[#1450F5]/10" />
          <AlertTriangle className="relative text-[#1450F5]" style={{ width: 20, height: 20 }} />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[#111827]">{title}</p>
          <p className="mt-2 text-sm leading-5 text-[#6B7280]">{message}</p>
          <div className="mt-4 h-1.5 w-44 overflow-hidden rounded-full bg-[#E5E7EB]">
            <div className="h-full w-full animate-pulse rounded-full bg-[#1450F5]" />
          </div>
        </div>
      </div>
    </div>
  )
}
