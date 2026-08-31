import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Check, Eye, Search, X } from 'lucide-react'
import { useOfferingStore } from '../../../store/offeringStore'
import { KDS_INSTANCE_KEYS, componentByKey, componentDefaultAsset, componentDisplayLabel, componentVariantsFor, isKdsInstanceKey, semanticComponentKey, variantForAsset } from '../../../lib/constants'
import { cn } from '../../../lib/utils'
import { toast } from '../../../hooks/useToast'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../../../components/ui/dialog'
import type { Environment, ComponentKey, ComponentInstanceSelection, ComponentVariant, SemanticComponentKey } from '../../../types'

type CatalogGroupKind = 'structure' | 'kds' | 'single'
type CatalogGroup = {
  id: string
  label: string
  componentType: SemanticComponentKey
  variantGroup: string
  kind: CatalogGroupKind
}

const STEP2_GROUPS: CatalogGroup[] = [
  { id: 'interior-india', label: 'Elevator Interior - India', componentType: 'ceiling', variantGroup: 'Elevator Interior - India', kind: 'structure' },
  { id: 'interior-indonesia-singapore', label: 'Elevator Interior - Indonesia/Singapore', componentType: 'ceiling', variantGroup: 'Elevator Interior - Indonesia/Singapore', kind: 'structure' },
  { id: 'kds90', label: 'KDS90', componentType: 'kds', variantGroup: 'KDS90', kind: 'kds' },
  { id: 'kds330-93', label: 'KDS330/93', componentType: 'kds', variantGroup: 'KDS330/93', kind: 'kds' },
  { id: 'dcs1020', label: 'DCS1020', componentType: 'dcs1020', variantGroup: 'DCS1020', kind: 'single' },
  { id: 'door', label: 'Door', componentType: 'door', variantGroup: 'Door', kind: 'structure' },
]

const STRUCTURE_KEYS: ComponentKey[] = ['ceiling', 'door']
const MAX_SELECTED_COMPONENTS = 5

type ComponentAssetMap = Partial<Record<ComponentKey, string>>
type PreviewImage = { title: string; subtitle: string; imageUrl: string }
function displayImageUrl(imageUrl: string | null | undefined, version: string) {
  if (!imageUrl) return undefined
  return imageUrl.startsWith('/components/') ? imageUrl + '?v=' + version : imageUrl
}

function normalizeEnvironments(): Environment[] {
  return ['lobby']
}

function groupVariants(group: CatalogGroup): ComponentVariant[] {
  return componentVariantsFor(group.componentType).filter(variant => variant.group === group.variantGroup)
}

function selectedKdsKeys(components: ComponentKey[]) {
  return KDS_INSTANCE_KEYS.filter(key => components.includes(key)) as ComponentKey[]
}

function selectedGroupAsset(group: CatalogGroup, components: ComponentKey[], assets: ComponentAssetMap) {
  if (group.kind === 'kds') {
    return selectedKdsKeys(components)
      .map(key => assets[key])
      .find(asset => asset && variantForAsset('kds', asset)?.group === group.variantGroup) ?? null
  }
  const key = group.componentType as ComponentKey
  const asset = components.includes(key) ? assets[key] ?? null : null
  return asset && groupVariants(group).some(variant => variant.imageUrl === asset) ? asset : null
}

function groupForComponent(component: ComponentKey, assets: ComponentAssetMap) {
  const variantGroup = variantForAsset(component, assets[component])?.group
  return STEP2_GROUPS.find(group => group.componentType === semanticComponentKey(component) && group.variantGroup === variantGroup)
    ?? STEP2_GROUPS.find(group => group.componentType === semanticComponentKey(component))
    ?? STEP2_GROUPS[0]
}

function firstFreeKdsKey(components: ComponentKey[]): ComponentKey | null {
  return (KDS_INSTANCE_KEYS.find(key => !components.includes(key)) ?? null) as ComponentKey | null
}

function normalizeSelectedComponents(components: ComponentKey[] = [], selections: ComponentInstanceSelection[] = []): ComponentKey[] {
  const next: ComponentKey[] = []
  const push = (key: ComponentKey) => {
    if (!next.includes(key)) next.push(key)
  }

  const sourceComponents = components.length
    ? components
    : selections.map(selection => selection.id as ComponentKey)

  sourceComponents.forEach(component => {
    if (component === 'lci') push('kds')
    else if (component === 'ceiling' || component === 'door' || component === 'dcs1020' || isKdsInstanceKey(component)) push(component)
  })

  const structures = next.filter(component => STRUCTURE_KEYS.includes(component))
  const nonStructures = next.filter(component => !STRUCTURE_KEYS.includes(component))
  return [...nonStructures, ...(structures.length ? [structures[structures.length - 1]] : [])].slice(0, MAX_SELECTED_COMPONENTS)
}

function normalizeAssetMap(components: ComponentKey[], assets: ComponentAssetMap = {}, selections: ComponentInstanceSelection[] = []): ComponentAssetMap {
  const instanceAssets = Object.fromEntries(selections.map(selection => [selection.id, selection.assetUrl])) as ComponentAssetMap
  return Object.fromEntries(
    components
      .map(key => [key, assets[key] ?? instanceAssets[key] ?? assets[semanticComponentKey(key)] ?? componentDefaultAsset(key)] as const)
      .filter(([, value]) => Boolean(value))
  ) as ComponentAssetMap
}

function normalizeKdsSelections(components: ComponentKey[], assets: ComponentAssetMap = {}, selections: ComponentInstanceSelection[] = []): ComponentInstanceSelection[] {
  const variants = componentVariantsFor('kds')
  const seenVariants = new Set<string>()
  return selectedKdsKeys(components).flatMap(key => {
    const existing = selections.find(selection => selection.id === key && selection.componentType === 'kds')
    const variant = variants.find(item => item.imageUrl === assets[key])
      ?? variants.find(item => item.id === existing?.variantId)
      ?? variants.find(item => item.imageUrl === existing?.assetUrl)
      ?? variants[0]
    if (!variant || seenVariants.has(variant.id)) return []
    seenVariants.add(variant.id)
    return [{ id: key, componentType: 'kds' as const, variantId: variant.id, assetUrl: variant.imageUrl }]
  })
}

function selectedVariantFor(key: ComponentKey, assets: ComponentAssetMap) {
  return variantForAsset(key, assets[key])
}


export default function Step2Components() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, setComponents, goToStep } = useOfferingStore()

  const initialComponents = normalizeSelectedComponents(currentOffering?.selectedComponents ?? [], currentOffering?.componentInstances ?? [])
  const initialAssets = normalizeAssetMap(initialComponents, currentOffering?.selectedComponentAssets ?? {}, currentOffering?.componentInstances ?? [])
  const initialKdsSelections = normalizeKdsSelections(initialComponents, initialAssets, currentOffering?.componentInstances ?? [])
  const [envs, setEnvs] = useState<Environment[]>(normalizeEnvironments())
  const [comps, setComps] = useState<ComponentKey[]>(initialComponents)
  const [componentAssets, setComponentAssets] = useState<ComponentAssetMap>(initialAssets)
  const [activeCatalogGroupId, setActiveCatalogGroupId] = useState<string>(
    initialComponents[0] ? groupForComponent(initialComponents[0], initialAssets).id : STEP2_GROUPS[0].id
  )
  const [editingInstanceKey, setEditingInstanceKey] = useState<ComponentKey | null>(null)
  const [kdsSelections, setKdsSelections] = useState<ComponentInstanceSelection[]>(initialKdsSelections)
  const [previewImage, setPreviewImage] = useState<PreviewImage | null>(null)
  const [optionQuery, setOptionQuery] = useState('')
  const [componentImageVersion] = useState(() => String(Date.now()))

  useEffect(() => {
    if (currentOffering) {
      const nextComponents = normalizeSelectedComponents(currentOffering.selectedComponents, currentOffering.componentInstances ?? [])
      const nextAssets = normalizeAssetMap(nextComponents, currentOffering.selectedComponentAssets ?? {}, currentOffering.componentInstances ?? [])
      setEnvs(normalizeEnvironments())
      setComps(nextComponents)
      setComponentAssets(nextAssets)
      setActiveCatalogGroupId(current => STEP2_GROUPS.some(group => group.id === current) ? current : (nextComponents[0] ? groupForComponent(nextComponents[0], nextAssets).id : STEP2_GROUPS[0].id))
      setEditingInstanceKey(current => current && nextComponents.includes(current) ? current : null)
      setKdsSelections(normalizeKdsSelections(nextComponents, nextAssets, currentOffering.componentInstances ?? []))
    }
  }, [currentOffering?.id])

  const activeGroup = STEP2_GROUPS.find(group => group.id === activeCatalogGroupId) ?? STEP2_GROUPS[0]
  const activeComp = activeGroup.componentType as ComponentKey
  const activeVariants = groupVariants(activeGroup)
  const filteredActiveVariants = activeVariants.filter(variant =>
    variant.label.toLowerCase().includes(optionQuery.trim().toLowerCase())
  )
  const activeVariantGroups = [{ group: activeGroup.label, variants: filteredActiveVariants }]
  const canContinue = envs.length > 0 && comps.length > 0

  const activateGroup = (group: CatalogGroup) => {
    setActiveCatalogGroupId(group.id)
    setEditingInstanceKey(current =>
      group.kind === 'kds' && current && isKdsInstanceKey(current)
        ? current
        : null
    )
    setOptionQuery('')
  }

  const handleSelectedClick = (component: ComponentKey) => {
    const group = groupForComponent(component, componentAssets)
    setActiveCatalogGroupId(group.id)
    setEditingInstanceKey(isKdsInstanceKey(component) ? component : null)
    setOptionQuery('')
  }

  const handleRemoveSelected = (component: ComponentKey) => {
    const nextComps = comps.filter(item => item !== component)
    const nextAssets = { ...componentAssets }
    delete nextAssets[component]
    const nextKdsSelections = isKdsInstanceKey(component)
      ? normalizeKdsSelections(nextComps, nextAssets, kdsSelections.filter(selection => selection.id !== component))
      : kdsSelections

    setComps(nextComps)
    setComponentAssets(nextAssets)
    setKdsSelections(nextKdsSelections)
    setEditingInstanceKey(current => current === component ? null : current)
  }

  const selectVariant = (_componentKey: ComponentKey, variant: ComponentVariant) => {
    if (activeGroup.kind === 'kds') {
      if (editingInstanceKey && isKdsInstanceKey(editingInstanceKey)) {
        const duplicate = selectedKdsKeys(comps).some(key => key !== editingInstanceKey && selectedVariantFor(key, componentAssets)?.id === variant.id)
        if (duplicate) {
          toast('This KDS component is already selected.', 'destructive')
          return
        }
        const nextComps = comps.includes(editingInstanceKey) ? comps : [...comps, editingInstanceKey]
        const nextAssets = normalizeAssetMap(nextComps, { ...componentAssets, [editingInstanceKey]: variant.imageUrl })
        setComps(nextComps)
        setComponentAssets(nextAssets)
        setKdsSelections(normalizeKdsSelections(nextComps, nextAssets, kdsSelections))
        return
      }
      if (selectedKdsKeys(comps).some(key => selectedVariantFor(key, componentAssets)?.id === variant.id)) {
        toast('This KDS component is already selected.', 'destructive')
        return
      }
      if (selectedKdsKeys(comps).length >= KDS_INSTANCE_KEYS.length) {
        toast('Select an existing KDS unit to replace it.', 'destructive')
        return
      }
      if (comps.length >= MAX_SELECTED_COMPONENTS) {
        toast('You can select up to 5 components total.', 'destructive')
        return
      }
      const nextKey = firstFreeKdsKey(comps)
      if (!nextKey) return
      const nextComps = [...comps, nextKey]
      const nextAssets = normalizeAssetMap(nextComps, { ...componentAssets, [nextKey]: variant.imageUrl })
      setComps(nextComps)
      setComponentAssets(nextAssets)
      setKdsSelections(normalizeKdsSelections(nextComps, nextAssets, kdsSelections))
      setEditingInstanceKey(null)
      return
    }

    const componentKey = activeGroup.componentType as ComponentKey
    if (!comps.includes(componentKey) && comps.length >= MAX_SELECTED_COMPONENTS && activeGroup.kind !== 'structure') {
      toast('You can select up to 5 components total.', 'destructive')
      return
    }
    const nextComps = activeGroup.kind === 'structure'
      ? [...comps.filter(component => !STRUCTURE_KEYS.includes(component)), componentKey]
      : comps.includes(componentKey)
        ? comps
        : [...comps, componentKey]
    const nextAssets = normalizeAssetMap(nextComps, { ...componentAssets, [componentKey]: variant.imageUrl })
    setComps(nextComps)
    setComponentAssets(nextAssets)
    setEditingInstanceKey(null)
  }

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
    await setComponents(envs, comps, normalizeAssetMap(comps, componentAssets), kdsSelections)
    goToStep(3)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/3`)
  }

  const handleBack = () => {
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/1`)
    goToStep(1)
  }

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
                <img src={displayImageUrl(previewImage.imageUrl, componentImageVersion)} alt={previewImage.title} className="max-h-[68vh] w-full object-contain" />
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
            <p className="mt-1 text-[12px] text-[#8A9BB5]">Choose up to 5 components: 1 structure, 1 DCS1020, and up to 3 KDS units.</p>
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
            <div>
              <p className="label-caps mb-3">Components</p>
              <div className="space-y-2">
                {STEP2_GROUPS.map(group => {
                  const groupAsset = selectedGroupAsset(group, comps, componentAssets)
                  const isSelected = Boolean(groupAsset)
                  const isActive = activeGroup.id === group.id
                  const cardImage = groupAsset ?? groupVariants(group)[0]?.imageUrl ?? componentDefaultAsset(group.componentType)
                  return (
                    <button
                      key={group.id}
                      onClick={() => activateGroup(group)}
                      aria-pressed={isSelected}
                      className={cn(
                        'flex min-h-[74px] w-full items-center gap-3 rounded-lg border bg-white p-2 text-left transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1450F5] focus-visible:ring-offset-2',
                        isActive ? 'border-[#1450F5] shadow-sm shadow-[#1450F5]/10' : 'border-[#E4E7EB] hover:border-[#1450F5]/40',
                        isSelected && !isActive ? 'border-[#BFD0FF]' : ''
                      )}
                    >
                      <span className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-md bg-[#F1F3F6]">
                        {cardImage ? (
                          <img
                            src={displayImageUrl(cardImage, componentImageVersion)}
                            alt={group.label}
                            className="h-full w-full object-contain p-1.5"
                            loading="lazy"
                          />
                        ) : null}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className={cn('block text-[13px] font-semibold leading-4', isSelected ? 'text-[#1450F5]' : 'text-[#111827]')}>
                          {group.label}
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
                <p className="label-caps">{activeGroup.label + ' options'}</p>
                <p className="mt-1 text-[12px] text-[#8A9BB5]">
                  {filteredActiveVariants.length + ' of ' + activeVariants.length + ' available' + (editingInstanceKey ? ' - editing ' + componentDisplayLabel(editingInstanceKey, componentAssets[editingInstanceKey]) : '')}
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
                  {comps.map(component => {
                    const variant = selectedVariantFor(component, componentAssets)
                    return (
                      <div
                        key={component}
                        className={cn(
                          'flex h-8 max-w-[240px] items-center gap-1 rounded-lg border bg-white pl-2.5 pr-1 transition-colors duration-[120ms]',
                          editingInstanceKey === component ? 'border-[#1450F5] bg-[#1450F5]/5' : 'border-[#D7E0FF] bg-white hover:bg-[#1450F5]/5'
                        )}
                      >
                        <button
                          type="button"
                          onClick={() => handleSelectedClick(component)}
                          className="flex min-w-0 flex-1 items-center gap-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-[#1450F5] focus-visible:ring-offset-1"
                          aria-label={'Edit ' + componentDisplayLabel(component, componentAssets[component])}
                        >
                          {variant?.imageUrl && <img src={displayImageUrl(variant.imageUrl, componentImageVersion)} alt="" className="h-5 w-5 shrink-0 rounded-sm object-cover" />}
                          <span className="truncate text-[12px] font-semibold text-[#1450F5]">{componentDisplayLabel(component, componentAssets[component])}</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRemoveSelected(component)}
                          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[#8A9BB5] transition-colors duration-[120ms] hover:bg-[#FEECEC] hover:text-[#DC2626] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1450F5]"
                          aria-label={'Remove ' + componentDisplayLabel(component, componentAssets[component])}
                          title="Remove component"
                        >
                          <X className="h-3.5 w-3.5" strokeWidth={2.5} />
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {activeComp && activeVariants.length > 0 ? (
              filteredActiveVariants.length > 0 ? (
              <div className="max-h-none overflow-y-auto p-4 sm:p-5 lg:max-h-[560px]">
                {activeVariantGroups.map(({ group, variants }) => (
                  <section key={group ?? 'ungrouped'} className="mb-5 last:mb-0">
                    {group && <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.12em] text-[#475569]">{group}</p>}
                    <div className={cn(
                      activeComp === 'ceiling' ? 'grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3' : activeComp === 'cop' || activeComp === 'door' ? 'grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3' : 'grid grid-cols-3 gap-2 sm:grid-cols-4 xl:grid-cols-5'
                    )}>
                      {variants.map(variant => {
                        const isSelected = activeComp === 'kds'
                          ? kdsSelections.some(selection => selection.variantId === variant.id)
                          : componentAssets[activeComp] === variant.imageUrl
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
                              <img src={displayImageUrl(variant.imageUrl, componentImageVersion)} alt={variant.label} className="max-h-full max-w-full object-contain p-2 transition-transform duration-300 group-hover:scale-[1.03]" loading="lazy" />
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
                  </section>
                ))}
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
            <span className="font-semibold text-[#111827]">{comps.length}/{MAX_SELECTED_COMPONENTS} selected</span>
            {kdsSelections.length > 0 ? ` - ${kdsSelections.length} KDS` : ''}
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
