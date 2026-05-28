import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Check } from 'lucide-react'
import { useOfferingStore } from '../../../store/offeringStore'
import { KONE_COMPONENTS, ENVIRONMENTS } from '../../../lib/constants'
import { cn } from '../../../lib/utils'
import type { Environment, ComponentKey } from '../../../types'

const ENV_COMPONENTS: Record<Environment, ComponentKey[]> = {
  car: ['cop', 'ceiling'],
  lobby: ['lci', 'door', 'ceiling'],
}

function getAvailableComponents(envs: Environment[]): ComponentKey[] {
  if (envs.length === 0) return []
  return Array.from(new Set(envs.flatMap(e => ENV_COMPONENTS[e])))
}

export default function Step2Components() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, setComponents, goToStep } = useOfferingStore()

  const [envs, setEnvs] = useState<Environment[]>(currentOffering?.environments ?? [])
  const [comps, setComps] = useState<ComponentKey[]>(currentOffering?.selectedComponents ?? [])

  useEffect(() => {
    if (currentOffering) {
      setEnvs(currentOffering.environments)
      setComps(currentOffering.selectedComponents)
    }
  }, [currentOffering?.id])

  const availableComponents = getAvailableComponents(envs)

  const toggleEnv = (k: Environment) => {
    const newEnvs = envs.includes(k) ? envs.filter(e => e !== k) : [...envs, k]
    setEnvs(newEnvs)
    const newAvailable = getAvailableComponents(newEnvs)
    setComps(prev => prev.filter(c => newAvailable.includes(c)))
  }

  const toggleComp = (k: ComponentKey) =>
    setComps(prev => prev.includes(k) ? prev.filter(c => c !== k) : [...prev, k])

  const canContinue = envs.length > 0 && comps.length > 0

  const handleContinue = async () => {
    await setComponents(envs, comps)
    goToStep(3)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/3`)
  }

  const handleBack = () => {
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/1`)
    goToStep(1)
  }

  const envHint =
    envs.includes('car') && envs.includes('lobby')
      ? 'COP, Ceiling, LCI, and Door are available'
      : envs.includes('car')
        ? 'COP and Ceiling are available for Car'
        : envs.includes('lobby')
          ? 'LCI, Door, and Ceiling are available for Lobby'
          : 'Select at least one environment'

  return (
    <div className="rounded-xl border border-[#E9ECEF] bg-white p-8 shadow-sm">
      <div className="mb-1 flex items-start justify-between">
        <h2 className="text-heading text-[15px] font-semibold text-[#111827]">
          2 &nbsp; Use Case & Components
        </h2>
        <button
          onClick={handleBack}
          className="text-xs font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#6B7280]"
        >
          Back
        </button>
      </div>

      <div className="mt-7 space-y-9">

        {/* Environment selection */}
        <div>
          <p className="label-caps mb-3">Where will this be used?</p>
          <div className="flex flex-wrap gap-2">
            {ENVIRONMENTS.map(env => {
              const isSelected = envs.includes(env.key)
              return (
                <button
                  key={env.key}
                  onClick={() => toggleEnv(env.key)}
                  aria-pressed={isSelected}
                  className={cn(
                    'inline-flex h-9 items-center gap-2 rounded-lg border px-5 text-sm font-semibold transition-all duration-[150ms] select-none',
                    isSelected
                      ? 'border-[#1450F5] bg-[#1450F5] text-white shadow-sm'
                      : 'border-[#E4E4E4] bg-white text-[#374151] hover:border-[#1450F5]/40 hover:text-[#1450F5]'
                  )}
                >
                  {env.label}
                </button>
              )
            })}
          </div>
          <p className="mt-2 text-[12px] text-[#9CA3AF]">{envHint}</p>
        </div>

        {/* Component selection — image cards */}
        <div>
          <p className="label-caps mb-4">Which components are needed?</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {KONE_COMPONENTS.map(comp => {
              const isAvailable = availableComponents.includes(comp.key)
              const isSelected = comps.includes(comp.key)
              return (
                <button
                  key={comp.key}
                  onClick={() => isAvailable && toggleComp(comp.key)}
                  aria-pressed={isSelected}
                  disabled={!isAvailable}
                  className={cn(
                    'group relative overflow-hidden rounded-xl border-2 text-left transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1450F5] focus-visible:ring-offset-2',
                    !isAvailable
                      ? 'cursor-not-allowed border-[#E9ECEF] opacity-35'
                      : isSelected
                        ? 'border-[#1450F5] shadow-md shadow-[#1450F5]/10'
                        : 'border-[#E9ECEF] hover:border-[#1450F5]/40 hover:shadow-sm'
                  )}
                >
                  {/* Component image */}
                  <div className="relative aspect-[4/3] overflow-hidden bg-[#F5F6F8]">
                    {comp.imageUrl ? (
                      <img
                        src={comp.imageUrl}
                        alt={comp.label}
                        className={cn(
                          'h-full w-full object-cover transition-transform duration-300',
                          !isAvailable ? 'grayscale' : 'group-hover:scale-105'
                        )}
                        loading="lazy"
                      />
                    ) : (
                      <div className="h-full w-full bg-[#E9ECEF]" />
                    )}

                    {/* Selected tint */}
                    {isSelected && (
                      <div className="absolute inset-0 bg-[#1450F5]/8" />
                    )}

                    {/* Checkmark badge */}
                    {isSelected && (
                      <div className="absolute right-2 top-2 flex h-[22px] w-[22px] items-center justify-center rounded-full bg-[#1450F5] shadow-sm">
                        <Check style={{ width: 12, height: 12, color: '#fff', strokeWidth: 3 }} />
                      </div>
                    )}
                  </div>

                  {/* Label area */}
                  <div className="px-3 py-2.5">
                    <p
                      className={cn(
                        'text-heading text-[13px] font-semibold leading-tight',
                        isSelected ? 'text-[#1450F5]' : 'text-[#111827]'
                      )}
                    >
                      {comp.label}
                    </p>
                    <p className="mt-0.5 text-[11px] leading-tight text-[#9CA3AF]">
                      {comp.description}
                    </p>
                  </div>
                </button>
              )
            })}
          </div>
          {envs.length === 0 ? (
            <p className="mt-3 text-[12px] text-[#9CA3AF]">Select an environment first to unlock components</p>
          ) : comps.length === 0 ? (
            <p className="mt-3 text-[12px] text-[#9CA3AF]">Select at least one component to continue</p>
          ) : null}
        </div>

        {/* Selected summary chips */}
        {comps.length > 0 && (
          <div>
            <p className="label-caps mb-3">Selected</p>
            <div className="flex flex-wrap gap-2">
              {KONE_COMPONENTS.filter(c => comps.includes(c.key)).map(c => (
                <div
                  key={c.key}
                  className="flex items-center gap-2 rounded-lg border border-[#1450F5]/20 bg-[#1450F5]/5 px-3 py-1.5"
                >
                  {c.imageUrl && (
                    <img
                      src={c.imageUrl}
                      alt={c.label}
                      className="h-5 w-5 rounded-sm object-cover"
                    />
                  )}
                  <span className="text-heading text-[12px] font-semibold text-[#1450F5]">{c.label}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-9 flex justify-end">
        <button
          onClick={handleContinue}
          disabled={!canContinue}
          className="rounded-lg bg-[#1450F5] px-6 text-[13px] font-semibold text-white transition-all duration-[150ms] hover:bg-[#1040D0] hover:shadow-md hover:shadow-[#1450F5]/25 disabled:cursor-not-allowed disabled:opacity-40"
          style={{ height: 38 }}
        >
          Continue
        </button>
      </div>
    </div>
  )
}
