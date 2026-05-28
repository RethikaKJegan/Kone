import { cn } from '../../lib/utils'
import type { ProjectStatus, OfferingStatus } from '../../types'

interface Props {
  status: ProjectStatus | OfferingStatus
}

const map: Record<string, string> = {
  draft: 'bg-[#F5F5F5] text-[#525252] border border-[#E4E4E4]',
  active: 'bg-[#F5F5F5] text-[#0A0A0A] border border-[#E4E4E4]',
  complete: 'bg-[#F0FDF4] text-[#16A34A] border border-[#DCFCE7]',
}

export function StatusBadge({ status }: Props) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-[4px] px-2 py-0.5 text-[11px] font-medium capitalize',
        map[status] ?? 'bg-[#F5F5F5] text-[#525252] border border-[#E4E4E4]'
      )}
    >
      {status}
    </span>
  )
}
