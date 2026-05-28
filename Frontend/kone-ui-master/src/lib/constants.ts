import type { ComponentItem, Environment, OfferingStep, BrochureSection } from '../types'

export const KONE_COMPONENTS: ComponentItem[] = [
  { key: 'ceiling', label: 'Ceiling', description: 'KONE ceiling panel unit' },
  { key: 'lci', label: 'LCI', description: 'Landing Call Indicator' },
  { key: 'door', label: 'Door', description: 'KONE door system' },
  { key: 'cop', label: 'COP', description: 'Car Operating Panel' },
]

export const ENVIRONMENTS: { key: Environment; label: string }[] = [
  { key: 'car', label: 'Car' },
  { key: 'lobby', label: 'Lobby' },
]

export const STEP_LABELS: Record<OfferingStep, string> = {
  1: 'Upload',
  2: 'Components',
  3: 'Preview',
  4: 'Repin',
  5: 'Video',
  6: 'Download',
}

export const OPTIONAL_STEPS: OfferingStep[] = [4]

export const VIDEO_MOTION_STYLES = [
  { value: 'zoom-in', label: 'Zoom In' },
  { value: 'pan-lr', label: 'Pan L–R' },
  { value: 'pan-rl', label: 'Pan R–L' },
] as const

export const VIDEO_SPEEDS = [0.5, 1, 1.5] as const
export const VIDEO_QUALITIES = ['360p', '480p', '720p', '1080p'] as const

export const BROCHURE_SECTIONS: {
  key: BrochureSection
  label: string
  placeholder: string
}[] = [
  {
    key: 'offeringOverview',
    label: 'Visualization Overview',
    placeholder:
      'Describe the elevator solution being proposed — components included, configuration details, and why it suits the customer environment.',
  },
  {
    key: 'competitorComparison',
    label: 'Competitor Comparison',
    placeholder:
      'Summarise how this KONE solution compares to competitor visualizations in terms of quality, service, and lifecycle cost.',
  },
  {
    key: 'uniqueSellingPoints',
    label: 'Unique Selling Points (U.S.P.)',
    placeholder:
      'List what differentiates this KONE solution — technology, reliability, design flexibility, or global service network.',
  },
  {
    key: 'customerBenefits',
    label: 'Customer Benefits (X.Y.Z.)',
    placeholder:
      'Frame benefits as outcomes for the customer: reliability, downtime reduction, warranty coverage, modernisation value.',
  },
  {
    key: 'additionalNotes',
    label: 'Additional Notes (A.B.C.)',
    placeholder:
      'Include any additional commercial terms, project timelines, or post-installation support details.',
  },
]

export const AI_PLACEMENT_DEFAULTS = {
  ceiling: { x: 50, y: 10 },
  lci: { x: 78, y: 40 },
  door: { x: 20, y: 55 },
  cop: { x: 18, y: 52 },
} as const
