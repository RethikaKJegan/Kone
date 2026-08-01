import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Check, Eye, Search } from 'lucide-react'
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

function componentThumbnailFor(key: ComponentKey) {
  if (key === 'ceiling') return '/components/ceiling.jpg'
  if (key === 'door') return '/components/door.jpg'
  return componentByKey(key)?.imageUrl ?? `/components/${key}.png`
}

function defaultAssetFor(key: ComponentKey) {
  return variantsFor(key)[0]?.imageUrl ?? componentThumbnailFor(key)
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
  const [optionQuery, setOptionQuery] = useState('')

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
    setOptionQuery('')
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
  const filteredActiveVariants = activeVariants.filter(variant =>
    variant.label.toLowerCase().includes(optionQuery.trim().toLowerCase())
  )

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

      <div className="overflow-hidden rounded-xl border border-[#E9ECEF] bg-white shadow-sm">
        <div className="flex items-start justify-between border-b border-[#EEF0F3] px-5 py-4 sm:px-6">
          <div>
            <h2 className="text-heading text-[15px] font-semibold text-[#111827]">
              2 &nbsp; Use Case & Components
            </h2>
            <p className="mt-1 text-[12px] text-[#8A9BB5]">Choose a component group, then select the exact option.</p>
          </div>
          <button
            onClick={handleBack}
            className="text-xs font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#6B7280]"
          >
            Back
          </button>
        </div>

        <div className="grid min-h-[620px] lg:grid-cols-[300px_minmax(0,1fr)]">
          <aside className="border-b border-[#EEF0F3] bg-[#FAFBFC] p-4 sm:p-5 lg:border-b-0 lg:border-r">
            <p className="label-caps mb-3">Where will this be used?</p>
            <div className="grid grid-cols-2 gap-2">
              {ENVIRONMENTS.map(env => {
                const isSelected = envs.includes(env.key)
                return (
                  <button
                    key={env.key}
                    onClick={() => toggleEnv(env.key)}
                    aria-pressed={isSelected}
                    className={cn(
                      'inline-flex h-10 items-center justify-center rounded-lg border text-sm font-semibold transition-all duration-[150ms] select-none',
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
            <p className="mt-2 min-h-[32px] text-[12px] leading-4 text-[#8A9BB5]">{envHint}</p>

            <div className="mt-6">
              <p className="label-caps mb-3">Components</p>
              <div className="space-y-2">
                {KONE_COMPONENTS.map(comp => {
                  const isAvailable = selectableComponents.includes(comp.key)
                  const isSelected = comps.includes(comp.key)
                  const isActive = activeComp === comp.key
                  const selectedVariant = selectedVariantFor(comp.key, componentAssets)
                  const cardImage = componentThumbnailFor(comp.key)
                  return (
                    <button
                      key={comp.key}
                      onClick={() => {
                        if (!isAvailable) return
                        toggleComp(comp.key)
                      }}
                      aria-pressed={isSelected}
                      disabled={!isAvailable}
                      className={cn(
                        'flex min-h-[74px] w-full items-center gap-3 rounded-lg border bg-white p-2 text-left transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1450F5] focus-visible:ring-offset-2',
                        !isAvailable
                          ? 'cursor-not-allowed opacity-40'
                          : isActive
                            ? 'border-[#1450F5] shadow-sm shadow-[#1450F5]/10'
                            : 'border-[#E4E7EB] hover:border-[#1450F5]/40',
                        isSelected && !isActive ? 'border-[#BFD0FF]' : ''
                      )}
                    >
                      <span className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-md bg-[#F1F3F6]">
                        {cardImage ? (
                          <img
                            src={cardImage}
                            alt={comp.label}
                            className="h-full w-full object-contain p-1.5"
                            loading="lazy"
                            onError={event => {
                              event.currentTarget.src = componentByKey(comp.key)?.imageUrl ?? `/components/${comp.key}.png`
                            }}
                          />
                        ) : null}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className={cn('block text-[13px] font-semibold leading-4', isSelected ? 'text-[#1450F5]' : 'text-[#111827]')}>
                          {comp.label}
                        </span>
                        <span className="mt-0.5 block truncate text-[11px] text-[#8A9BB5]">
                          {isSelected && selectedVariant ? selectedVariant.label : isAvailable ? comp.description : 'Unavailable'}
                        </span>
                      </span>
                      {isSelected && (
                        <span className="flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full bg-[#1450F5]">
                          <Check style={{ width: 12, height: 12, color: '#fff', strokeWidth: 3 }} />
                        </span>
                      )}
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
          </aside>

          <section className="flex min-w-0 flex-col">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#EEF0F3] px-4 py-4 sm:px-6">
              <div>
                <p className="label-caps">{activeComp ? `${componentByKey(activeComp)?.label} options` : 'Component options'}</p>
                <p className="mt-1 text-[12px] text-[#8A9BB5]">
                  {activeComp ? `${filteredActiveVariants.length} of ${activeVariants.length} available` : 'Select a component group to view options'}
                </p>
              </div>
              {activeComp && activeVariants.length > 1 && (
                <label className="relative order-last w-full sm:order-none sm:ml-auto sm:w-[230px]">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8A9BB5]" />
                  <input
                    value={optionQuery}
                    onChange={event => setOptionQuery(event.target.value)}
                    placeholder="Search options"
                    className="h-9 w-full rounded-lg border border-[#DDE3EA] bg-white pl-9 pr-3 text-[13px] font-medium text-[#111827] outline-none transition-colors duration-150 placeholder:text-[#A7B2C3] focus:border-[#1450F5] focus:ring-2 focus:ring-[#1450F5]/10"
                  />
                </label>
              )}
              {comps.length > 0 && (
                <div className="flex max-w-full flex-wrap gap-2">
                  {KONE_COMPONENTS.filter(c => comps.includes(c.key)).map(c => {
                    const variant = selectedVariantFor(c.key, componentAssets)
                    return (
                      <button
                        key={c.key}
                        onClick={() => {
                          setActiveComp(c.key)
                          setOptionQuery('')
                        }}
                        className={cn(
                          'flex h-8 max-w-[220px] items-center gap-2 rounded-lg border px-2.5 transition-colors duration-[120ms]',
                          activeComp === c.key ? 'border-[#1450F5] bg-[#1450F5]/5' : 'border-[#D7E0FF] bg-white hover:bg-[#1450F5]/5'
                        )}
                      >
                        {variant?.imageUrl && <img src={variant.imageUrl} alt={variant.label} className="h-5 w-5 rounded-sm object-cover" />}
                        <span className="truncate text-[12px] font-semibold text-[#1450F5]">{variant?.label ?? c.label}</span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            {activeComp && activeVariants.length > 0 ? (
              filteredActiveVariants.length > 0 ? (
              <div className={cn(
                'max-h-none overflow-y-auto p-4 sm:p-5 lg:max-h-[560px]',
                activeComp === 'ceiling' ? 'grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3' : activeComp === 'cop' || activeComp === 'door' ? 'grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3' : 'grid grid-cols-3 gap-2 sm:grid-cols-4 xl:grid-cols-5'
              )}>
                {filteredActiveVariants.map(variant => {
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
                        'group flex flex-col overflow-hidden rounded-lg border-2 bg-white text-left transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1450F5] focus-visible:ring-offset-2',
                        activeComp === 'ceiling' ? 'h-[188px]' : activeComp === 'cop' || activeComp === 'door' ? 'h-[232px]' : 'h-[104px]',
                        isSelected ? 'border-[#1450F5] shadow-md shadow-[#1450F5]/10' : 'border-[#E9ECEF] hover:border-[#1450F5]/40 hover:shadow-sm'
                      )}
                    >
                      <div className={cn(
                        'relative flex items-center justify-center overflow-hidden bg-[#F5F6F8]',
                        activeComp === 'ceiling' ? 'h-[158px]' : activeComp === 'cop' || activeComp === 'door' ? 'h-[198px]' : 'h-[78px]'
                      )}>
                        <img src={variant.imageUrl} alt={variant.label} className="max-h-full max-w-full object-contain p-2 transition-transform duration-300 group-hover:scale-[1.03]" loading="lazy" />
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
                      <div className="flex h-6 shrink-0 items-center border-t border-[#E1E6ED] bg-white px-2">
                        <p className={cn('truncate text-[10px] font-semibold leading-3', isSelected ? 'text-[#1450F5]' : 'text-[#111827]')} title={variant.label}>
                          {variant.label}
                        </p>
                      </div>
                    </div>
                  )
                })}
              </div>
              ) : (
                <div className="flex min-h-[360px] items-center justify-center p-8 text-center">
                  <div>
                    <p className="text-heading text-[14px] font-semibold text-[#111827]">No options found</p>
                    <p className="mt-1 text-[12px] text-[#8A9BB5]">Try a different search term.</p>
                  </div>
                </div>
              )
            ) : (
              <div className="flex min-h-[360px] items-center justify-center p-8 text-center">
                <div>
                  <p className="text-heading text-[14px] font-semibold text-[#111827]">No component selected</p>
                  <p className="mt-1 text-[12px] text-[#8A9BB5]">Choose an available component from the left panel.</p>
                </div>
              </div>
            )}
          </section>
        </div>

        <div className="sticky bottom-0 z-10 flex flex-wrap items-center justify-between gap-3 border-t border-[#E9ECEF] bg-white/95 px-5 py-4 backdrop-blur sm:px-6">
          <p className="text-[12px] font-medium text-[#8A9BB5]">
            <span className="font-semibold text-[#111827]">{comps.length}</span> selected
            {comps.length > 0 ? ` for ${envs[0] ?? 'this use case'}` : ''}
          </p>
          <div className="flex items-center gap-3">
            <button
              onClick={handleBack}
              className="h-9 rounded-lg border border-[#E4E4E4] bg-white px-4 text-[13px] font-semibold text-[#374151] transition-colors duration-[120ms] hover:border-[#BFC7D4]"
            >
              Back
            </button>
            <button
              onClick={handleContinue}
              disabled={!canContinue}
              className="h-9 rounded-lg bg-[#1450F5] px-6 text-[13px] font-semibold text-white transition-all duration-[150ms] hover:bg-[#1040D0] hover:shadow-md hover:shadow-[#1450F5]/25 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Continue
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
