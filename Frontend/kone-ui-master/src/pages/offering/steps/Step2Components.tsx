import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Check, Eye } from 'lucide-react'
import { useOfferingStore } from '../../../store/offeringStore'
import { KONE_COMPONENTS, ENVIRONMENTS } from '../../../lib/constants'
import { cn } from '../../../lib/utils'
import { toast } from '../../../hooks/useToast'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../../../components/ui/dialog'
import type { Environment, ComponentKey, ComponentVariant } from '../../../types'

const ENV_COMPONENTS: Record<Environment, ComponentKey[]> = {
  car: ['cop'],
  lobby: ['lci', 'door', 'ceiling'],
}

type ComponentAssetMap = Partial<Record<ComponentKey, string>>
type PreviewImage = { title: string; subtitle: string; imageUrl: string }

function getAvailableComponents(envs: Environment[]): ComponentKey[] {
  if (envs.length === 0) return []
  return Array.from(new Set(envs.flatMap(e => ENV_COMPONENTS[e])))
}

function normalizeEnvironments(envs: Environment[]): Environment[] {
  return envs.length > 0 ? [envs[0]] : []
}

function withoutDoorCeilingConflict(components: ComponentKey[]): ComponentKey[] {
  return components.includes('door') && components.includes('ceiling')
    ? components.filter(c => c !== 'ceiling')
    : components
}

function componentByKey(key: ComponentKey) {
  return KONE_COMPONENTS.find(component => component.key === key)
}

function variantsFor(key: ComponentKey): ComponentVariant[] {
  const component = componentByKey(key)
  if (component?.variants?.length) return component.variants
  return component?.imageUrl ? [{ id: `${key}-default`, label: component.label, imageUrl: component.imageUrl }] : []
}

function defaultAssetFor(key: ComponentKey) {
  return variantsFor(key)[0]?.imageUrl ?? componentByKey(key)?.imageUrl ?? null
}

function selectedVariantFor(key: ComponentKey, assets: ComponentAssetMap) {
  const variants = variantsFor(key)
  return variants.find(variant => variant.imageUrl === assets[key]) ?? variants[0] ?? null
}

function normalizeAssetMap(components: ComponentKey[], assets: ComponentAssetMap): ComponentAssetMap {
  return Object.fromEntries(
    components
      .map(key => [key, assets[key] ?? defaultAssetFor(key)] as const)
      .filter(([, value]) => Boolean(value))
  ) as ComponentAssetMap
}

export default function Step2Components() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, setComponents, goToStep } = useOfferingStore()

  const initialComponents = withoutDoorCeilingConflict(currentOffering?.selectedComponents ?? [])
  const [envs, setEnvs] = useState<Environment[]>(normalizeEnvironments(currentOffering?.environments ?? []))
  const [comps, setComps] = useState<ComponentKey[]>(initialComponents)
  const [componentAssets, setComponentAssets] = useState<ComponentAssetMap>(
    normalizeAssetMap(initialComponents, currentOffering?.selectedComponentAssets ?? {})
  )
  const [activeComp, setActiveComp] = useState<ComponentKey | null>(initialComponents[0] ?? null)
  const [previewImage, setPreviewImage] = useState<PreviewImage | null>(null)

  useEffect(() => {
    if (currentOffering) {
      const nextComponents = withoutDoorCeilingConflict(currentOffering.selectedComponents)
      setEnvs(normalizeEnvironments(currentOffering.environments))
      setComps(nextComponents)
      setComponentAssets(normalizeAssetMap(nextComponents, currentOffering.selectedComponentAssets ?? {}))
      setActiveComp(current => current && nextComponents.includes(current) ? current : nextComponents[0] ?? null)
    }
  }, [currentOffering?.id])

  const availableComponents = getAvailableComponents(envs)
  const selectableComponents = availableComponents.filter(c => {
    if (c === 'door' && comps.includes('ceiling')) return false
    if (c === 'ceiling' && comps.includes('door')) return false
    return true
  })

  const toggleEnv = (k: Environment) => {
    const newEnvs = [k]
    const newAvailable = getAvailableComponents(newEnvs)
    const newComps = withoutDoorCeilingConflict(comps.filter(c => newAvailable.includes(c)))
    setEnvs(newEnvs)
    setComps(newComps)
    setComponentAssets(prev => normalizeAssetMap(newComps, prev))
    setActiveComp(current => current && newComps.includes(current) ? current : newComps[0] ?? null)
  }

  const toggleComp = (k: ComponentKey) => {
    const nextComps = (() => {
      if (comps.includes(k)) return comps.filter(c => c !== k)
      const next = k === 'door'
        ? comps.filter(c => c !== 'ceiling')
        : k === 'ceiling'
          ? comps.filter(c => c !== 'door')
          : comps
      return [...next, k]
    })()
    setComps(nextComps)
    setComponentAssets(prev => normalizeAssetMap(nextComps, prev))
    setActiveComp(nextComps.includes(k) ? k : nextComps[0] ?? null)
  }

  const selectVariant = (componentKey: ComponentKey, variant: ComponentVariant) => {
    const nextComps = comps.includes(componentKey) ? comps : [...comps, componentKey]
    setComps(nextComps)
    setComponentAssets(prev => normalizeAssetMap(nextComps, { ...prev, [componentKey]: variant.imageUrl }))
    setActiveComp(componentKey)
  }

  const canContinue = envs.length > 0 && comps.length > 0

  const handleContinue = async () => {
    const hasInputImage = Boolean(currentOffering?.imageId || currentOffering?.inputImagePath || currentOffering?.uploadedFileUrl)
    if (!currentOffering || currentOffering.id !== offeringId || currentOffering.projectId !== projectId) {
      toast('Visualization state is not ready. Please reopen this visualization.', 'destructive')
      return
    }
    if (!hasInputImage) {
      toast('Upload and validate an input image before selecting components.', 'destructive')
      navigate(`/projects/${projectId}/offerings/${offeringId}/step/1`)
      goToStep(1)
      return
    }
    await setComponents(envs, comps, normalizeAssetMap(comps, componentAssets))
    goToStep(3)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/3`)
  }

  const handleBack = () => {
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/1`)
    goToStep(1)
  }

  const envHint =
    envs.includes('car') && envs.includes('lobby')
      ? 'COP, Elevator Interior, LCI, and Door are available'
      : envs.includes('car')
        ? 'COP is available for Car'
        : envs.includes('lobby')
          ? 'LCI, Door, and Elevator Interior are available for Lobby'
          : 'Select at least one environment'

  const activeVariants = activeComp && comps.includes(activeComp) ? variantsFor(activeComp) : []

  return (
    <>
      <Dialog open={Boolean(previewImage)} onOpenChange={open => !open && setPreviewImage(null)}>
        <DialogContent className="max-w-[min(92vw,920px)] gap-4 p-4 sm:p-5">
          {previewImage && (
            <>
              <DialogHeader className="pr-8">
                <DialogTitle>{previewImage.title}</DialogTitle>
                <DialogDescription>{previewImage.subtitle}</DialogDescription>
              </DialogHeader>
              <div className="flex max-h-[72vh] items-center justify-center overflow-hidden rounded-lg border border-[#E4E4E4] bg-[#F5F6F8] p-3">
                <img src={previewImage.imageUrl} alt={previewImage.title} className="max-h-[68vh] w-full object-contain" />
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

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

        <div>
          <p className="label-caps mb-4">Which components are needed?</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {KONE_COMPONENTS.map(comp => {
              const isAvailable = selectableComponents.includes(comp.key)
              const isSelected = comps.includes(comp.key)
              const selectedVariant = selectedVariantFor(comp.key, componentAssets)
              const cardImage = selectedVariant?.imageUrl ?? comp.imageUrl
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
                  <div className="relative aspect-[4/3] overflow-hidden bg-[#F5F6F8]">
                    {cardImage ? (
                      <img
                        src={cardImage}
                        alt={selectedVariant?.label ?? comp.label}
                        className={cn(
                          'h-full w-full object-cover transition-transform duration-300',
                          !isAvailable ? 'grayscale' : 'group-hover:scale-105'
                        )}
                        loading="lazy"
                      />
                    ) : (
                      <div className="h-full w-full bg-[#E9ECEF]" />
                    )}
                    {isSelected && <div className="absolute inset-0 bg-[#1450F5]/8" />}
                    {isSelected && (
                      <div className="absolute right-2 top-2 flex h-[22px] w-[22px] items-center justify-center rounded-full bg-[#1450F5] shadow-sm">
                        <Check style={{ width: 12, height: 12, color: '#fff', strokeWidth: 3 }} />
                      </div>
                    )}
                  </div>

                  <div className="px-3 py-2.5">
                    <p className={cn('text-heading text-[13px] font-semibold leading-tight', isSelected ? 'text-[#1450F5]' : 'text-[#111827]')}>
                      {comp.label}
                    </p>
                    <p className="mt-0.5 truncate text-[11px] leading-tight text-[#9CA3AF]">
                      {isSelected && selectedVariant ? selectedVariant.label : comp.description}
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

        {activeComp && activeVariants.length > 0 && (
          <div>
            <div className="mb-4 flex items-center justify-between gap-3">
              <p className="label-caps">{componentByKey(activeComp)?.label} options</p>
              <span className="text-[11px] font-medium text-[#9CA3AF]">{activeVariants.length} available</span>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {activeVariants.map(variant => {
                const isSelected = componentAssets[activeComp] === variant.imageUrl
                return (
                  <div
                    key={variant.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => selectVariant(activeComp, variant)}
                    onKeyDown={event => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        selectVariant(activeComp, variant)
                      }
                    }}
                    aria-pressed={isSelected}
                    className={cn(
                      'group overflow-hidden rounded-lg border-2 bg-white text-left transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1450F5] focus-visible:ring-offset-2',
                      isSelected ? 'border-[#1450F5] shadow-md shadow-[#1450F5]/10' : 'border-[#E9ECEF] hover:border-[#1450F5]/40 hover:shadow-sm'
                    )}
                  >
                    <div className="relative aspect-[4/3] bg-[#F5F6F8]">
                      <img src={variant.imageUrl} alt={variant.label} className="h-full w-full object-contain p-2 transition-transform duration-300 group-hover:scale-[1.03]" loading="lazy" />
                      <button
                        type="button"
                        onClick={event => {
                          event.stopPropagation()
                          setPreviewImage({ title: variant.label, subtitle: componentByKey(activeComp)?.label ?? 'Component option', imageUrl: variant.imageUrl })
                        }}
                        className="absolute left-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-black/65 text-white opacity-0 shadow-sm transition-opacity duration-[120ms] hover:bg-black/80 focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-[#1450F5] focus:ring-offset-2 group-hover:opacity-100"
                        aria-label={'Preview ' + variant.label}
                        title={'Preview ' + variant.label}
                      >
                        <Eye style={{ width: 15, height: 15 }} />
                      </button>
                      {isSelected && (
                        <div className="absolute right-2 top-2 flex h-[22px] w-[22px] items-center justify-center rounded-full bg-[#1450F5] shadow-sm">
                          <Check style={{ width: 12, height: 12, color: '#fff', strokeWidth: 3 }} />
                        </div>
                      )}
                    </div>
                    <div className="flex h-[42px] items-center px-3">
                      <p className={cn('line-clamp-2 text-[12px] font-semibold leading-4', isSelected ? 'text-[#1450F5]' : 'text-[#111827]')}>
                        {variant.label}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {comps.length > 0 && (
          <div>
            <p className="label-caps mb-3">Selected</p>
            <div className="flex flex-wrap gap-2">
              {KONE_COMPONENTS.filter(c => comps.includes(c.key)).map(c => {
                const variant = selectedVariantFor(c.key, componentAssets)
                return (
                  <button
                    key={c.key}
                    onClick={() => setActiveComp(c.key)}
                    className={cn(
                      'flex items-center gap-2 rounded-lg border px-3 py-1.5 transition-colors duration-[120ms]',
                      activeComp === c.key ? 'border-[#1450F5] bg-[#1450F5]/5' : 'border-[#1450F5]/20 bg-white hover:bg-[#1450F5]/5'
                    )}
                  >
                    {variant?.imageUrl && <img src={variant.imageUrl} alt={variant.label} className="h-5 w-5 rounded-sm object-cover" />}
                    <span className="text-heading text-[12px] font-semibold text-[#1450F5]">{variant?.label ?? c.label}</span>
                  </button>
                )
              })}
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
    </>
  )
}
