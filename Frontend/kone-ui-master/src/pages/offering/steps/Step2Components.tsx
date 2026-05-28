import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
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
  const sets = envs.map(e => ENV_COMPONENTS[e])
  const union = Array.from(new Set(sets.flat()))
  return union
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

  const pillBase = 'inline-flex h-[34px] items-center gap-2 rounded-[5px] border px-4 text-sm font-medium cursor-pointer transition-colors duration-[120ms] select-none'
  const pillSelected = 'bg-[#0A0A0A] border-[#0A0A0A] text-white'
  const pillUnselected = 'bg-white border-[#E4E4E4] text-[#374151] hover:border-[#C8C8C8]'
  const pillDisabled = 'bg-[#F5F5F5] border-[#E4E4E4] text-[#C8C8C8] cursor-not-allowed opacity-50'

  const selectedCompItems = KONE_COMPONENTS.filter(c => comps.includes(c.key))

  return (
    <div className="rounded-lg border border-[#E4E4E4] bg-white p-8">
      <div className="mb-1 flex items-start justify-between">
        <h2 className="text-base font-semibold text-[#0A0A0A]">2 &nbsp; Use Case & Components</h2>
        <button onClick={handleBack} className="text-xs text-[#A3A3A3] transition-colors duration-[120ms] hover:text-[#525252]">
          Back
        </button>
      </div>

      <div className="mt-6 space-y-8">
        <div>
          <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">
            Where will this be used?
          </p>
          <div className="flex flex-wrap gap-2">
            {ENVIRONMENTS.map(env => (
              <button
                key={env.key}
                onClick={() => toggleEnv(env.key)}
                aria-pressed={envs.includes(env.key)}
                className={cn(pillBase, envs.includes(env.key) ? pillSelected : pillUnselected)}
              >
                {env.label}
              </button>
            ))}
          </div>
          {envs.length === 0 && <p className="mt-2 text-xs text-[#A3A3A3]">Select at least one environment</p>}
          {envs.length > 0 && (
            <p className="mt-2 text-xs text-[#A3A3A3]">
              {envs.includes('car') && envs.includes('lobby')
                ? 'COP, Ceiling, LCI, and Door are available'
                : envs.includes('car')
                  ? 'COP and Ceiling are available for Car'
                  : 'LCI, Door, and Ceiling are available for Lobby'}
            </p>
          )}
        </div>

        <div>
          <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">
            Which components are needed?
          </p>
          <div className="flex flex-wrap gap-2">
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
                    pillBase,
                    !isAvailable ? pillDisabled : isSelected ? pillSelected : pillUnselected
                  )}
                >
                  <span
                    className={cn(
                      'shrink-0 rounded-sm',
                      isSelected ? 'bg-white/30' : 'bg-[#E4E4E4]'
                    )}
                    style={{ width: 12, height: 12 }}
                  />
                  {comp.label}
                </button>
              )
            })}
          </div>
          {envs.length === 0
            ? <p className="mt-2 text-xs text-[#A3A3A3]">Select an environment first</p>
            : comps.length === 0
              ? <p className="mt-2 text-xs text-[#A3A3A3]">Select at least one component</p>
              : null}
        </div>

        {selectedCompItems.length > 0 && (
          <div>
            <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">Selected components</p>
            <div className="flex flex-wrap gap-2">
              {selectedCompItems.map(c => (
                <div
                  key={c.key}
                  className="flex items-center gap-2 rounded-[5px] border border-[#E4E4E4] bg-[#FAFAFA] px-2 py-1.5"
                >
                  <div className="shrink-0 rounded bg-[#E4E4E4]" style={{ width: 18, height: 18 }} aria-hidden="true" />
                  <span className="text-xs font-medium text-[#0A0A0A]">{c.label}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-8 flex justify-end">
        <button
          onClick={handleContinue}
          disabled={!canContinue}
          className="rounded-[5px] bg-[#0A0A0A] px-5 text-sm font-medium text-white transition-colors duration-[120ms] hover:bg-[#262626] disabled:cursor-not-allowed disabled:opacity-40"
          style={{ height: 34 }}
        >
          Continue
        </button>
      </div>
    </div>
  )
}
