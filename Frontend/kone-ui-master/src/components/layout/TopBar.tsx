import { Link } from 'react-router-dom'

interface Crumb {
  label: string
  to?: string
}

interface Props {
  crumbs: Crumb[]
}

export function TopBar({ crumbs }: Props) {
  return (
    <div className="flex items-center border-b border-[#EBEBEB] bg-white px-8" style={{ height: 48 }}>
      <nav aria-label="Breadcrumb" className="flex items-center gap-2">
        {crumbs.map((crumb, idx) => (
          <div key={idx} className="flex items-center gap-2">
            {idx > 0 && (
              <span className="select-none text-sm text-[#D1D5DB]">/</span>
            )}
            {crumb.to ? (
              <Link
                to={crumb.to}
                className="text-[13px] font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#1450F5]"
              >
                {crumb.label}
              </Link>
            ) : (
              <span className="text-[13px] font-semibold text-[#000000]">{crumb.label}</span>
            )}
          </div>
        ))}
      </nav>
    </div>
  )
}
