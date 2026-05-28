import type { ComponentKey } from '../../types'

interface Props {
  componentKey: ComponentKey
  label: string
}

export function ComponentBadge({ label }: Props) {
  return (
    <span className="inline-flex items-center rounded-[4px] border border-[#E4E4E4] bg-[#F5F5F5] px-2 py-0.5 text-[11px] font-medium text-[#374151]">
      {label}
    </span>
  )
}
